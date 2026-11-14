import Foundation
import ProbeCore
import os

// Swift Testing / XCTest don't run under Command Line Tools 26.6, so checks live here.
nonisolated(unsafe) var failures = 0

func check(_ condition: Bool, _ name: String) {
    if condition {
        print("PASS \(name)")
    } else {
        failures += 1
        print("FAIL \(name)")
    }
}

/// Virtual time. Timers fire as time passes them, wherever the time is spent: in the sampler's
/// sleep or inside a slow launcher read.
final class FakeClock: ProbeClock {
    private(set) var now = 0
    private var timers: [(at: Int, fire: () -> Void)] = []
    func nowMs() -> Int { now }
    func sleep(untilMs t: Int) {
        while let i = timers.indices.filter({ timers[$0].at <= max(t, now) })
            .min(by: { timers[$0].at < timers[$1].at }) {
            let timer = timers.remove(at: i)
            now = max(now, timer.at)
            timer.fire()
        }
        now = max(now, t)
    }
    func spend(_ ms: Int) { sleep(untilMs: now + ms) }
    func schedule(at: Int, _ fire: @escaping () -> Void) { timers.append((at, fire)) }
}

final class FakeKeys: KeyPoster {
    var posted: [(Int, String)] = []
    let clock: FakeClock
    let onKey: (String) -> Void
    init(clock: FakeClock, onKey: @escaping (String) -> Void) {
        self.clock = clock
        self.onKey = onKey
    }
    func type(_ character: String) {
        posted.append((clock.now, character))
        onKey(character)
    }
}

/// Posts each key when virtual time reaches its due time plus `lateByMs[index]`.
final class FakePacer: KeyPacer {
    let clock: FakeClock
    let keys: FakeKeys
    var lateByMs: [Int: Int] = [:]
    var log: [KeyPostDTO] = []
    init(clock: FakeClock, keys: FakeKeys) {
        self.clock = clock
        self.keys = keys
    }
    func begin(_ characters: [String], startMs: Int, intervalMs: Int) {
        for (i, character) in characters.enumerated() {
            let planned = i * intervalMs
            clock.schedule(at: startMs + planned + (lateByMs[i] ?? 0)) { [self] in
                let actual = clock.now - startMs
                keys.type(character)
                log.append(KeyPostDTO(plannedMs: planned, actualMs: actual))
            }
        }
    }
    func posted() -> [KeyPostDTO] { log }
}

/// Launcher whose field echoes typed text after `echoDelayMs`, showing `rows` once the field
/// holds the whole query.
final class FakeLauncher: LauncherAdapter {
    var ready = true
    var typed = ""
    var echoedAt: [Int: String] = [:]
    let clock: FakeClock
    let echoDelayMs: Int
    let rowsForQuery: [RowDTO]
    var stalePreviousRows: [RowDTO] = []
    var dropFirstKey = false
    var readRowsTakesMs = 0

    init(clock: FakeClock, echoDelayMs: Int = 0, rows: [RowDTO]) {
        self.clock = clock
        self.echoDelayMs = echoDelayMs
        self.rowsForQuery = rows
    }
    func isReady() -> Bool { ready }
    func fieldText() -> String? {
        let visible = echoedAt.filter { $0.key + echoDelayMs <= clock.now }.max { $0.key < $1.key }
        return visible?.value ?? ""
    }
    /// Rows follow whatever the field currently shows; before the field shows any of the new
    /// query, the previous query's rows are still on screen.
    func readRows() throws -> [RowDTO] {
        let f = fieldText() ?? ""
        clock.spend(readRowsTakesMs)
        return !f.isEmpty && typed.hasPrefix(f) ? rowsForQuery : stalePreviousRows
    }
    func keyTyped(_ c: String) {
        typed += c
        echoedAt[clock.now] = dropFirstKey ? String(typed.dropFirst()) : typed
    }
}

let calc = RowDTO(title: "Calculator", kind: "app", source: "local", folder: nil, paneId: nil,
                  selected: true)

/// Launcher that also shows an Enter action label, like Raycast's action bar.
final class LabelledLauncher: LauncherAdapter {
    var typed = ""
    func isReady() -> Bool { true }
    func fieldText() -> String? { typed }
    func readRows() throws -> [RowDTO] { [calc] }
    func primaryAction() -> String? { "Open Application" }
}

/// Keys typed from the pacing thread, readable from the sampling thread.
final class TypedText: KeyPoster, Sendable {
    let text = OSAllocatedUnfairLock(initialState: "")
    func type(_ character: String) { text.withLock { $0 += character } }
}

/// Launcher on the real clock whose row read blocks the calling thread for 150 ms.
final class SlowLauncher: LauncherAdapter {
    let typed: TypedText
    init(typed: TypedText) { self.typed = typed }
    func isReady() -> Bool { true }
    func fieldText() -> String? { typed.text.withLock { $0 } }
    func readRows() throws -> [RowDTO] {
        usleep(150_000)
        return [calc]
    }
}

func makeSampler(_ launcher: FakeLauncher, _ clock: FakeClock,
                 lateByMs: [Int: Int] = [:]) -> (Sampler, FakeKeys) {
    let keys = FakeKeys(clock: clock) { launcher.keyTyped($0) }
    let pacer = FakePacer(clock: clock, keys: keys)
    pacer.lateByMs = lateByMs
    return (Sampler(adapter: launcher, pacer: pacer, clock: clock), keys)
}

// 1. Full window, no early stop.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    let last = s.snapshots.last?.readStartMs ?? -1
    check(s.error == nil, "completed sample has no error")
    check(s.finalKeyPostMs == 240, "4 keys at 80 ms: final key posted at 240 ms")
    check(last >= s.finalKeyPostMs + 3000 - 50, "samples continue to the end of the 3 s window")
    check(s.snapshots.count >= 60, "about every 50 ms (got \(s.snapshots.count))")
}

// 2. Not ready: error and no keys.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.ready = false
    let (sampler, keys) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s.error == "not_ready", "unready launcher gives error not_ready")
    check(keys.posted.isEmpty, "no keys are sent when not ready")
}

// 3. Stale rows from a previous query are discarded until the field shows the typed text.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, echoDelayMs: 120, rows: [calc])
    launcher.stalePreviousRows = [RowDTO(title: "Chess", kind: "app", source: "local",
                                         folder: nil, paneId: nil, selected: nil)]
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    let sawChess = s.snapshots.contains { $0.rows.contains { $0.title == "Chess" } }
    check(!sawChess, "rows from the previous query (field not yet showing new text) are discarded")
    let blank = s.snapshots.filter { $0.fieldText.isEmpty }
    check(!blank.isEmpty && blank.allSatisfy { $0.rows.isEmpty },
          "while the field is still empty after typing began, a 'nothing selectable' snapshot is kept")
    let lagging = s.snapshots.contains { $0.fieldText == "cal" }
    check(lagging, "rows are kept while the field shows a prefix of what was typed (what Enter would open)")
    check(s.fieldShowsMs == 400, "field-shows-text time = first 50 ms sample at/after 360 (got \(s.fieldShowsMs ?? -1))")
}

// 3b. A field that never shows the typed text is a harness error, not a result.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, echoDelayMs: 100_000, rows: [calc])
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s.error == "field_never_matched", "field never showing text -> error field_never_matched")
}

// 4. Stepped mode waits 1000 ms after each key.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    let (sampler, keys) = makeSampler(launcher, clock)
    _ = sampler.run(text: "cal", mode: .stepped, windowMs: 3000)
    check(keys.posted.map { $0.0 } == [0, 1000, 2000], "stepped keys at 0/1000/2000 ms")
}

// 5. Continuous mode types at 80 ms with no pauses.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    let (sampler, keys) = makeSampler(launcher, clock)
    _ = sampler.run(text: "calc", mode: .continuous, windowMs: 3000)
    check(keys.posted.map { $0.0 } == [0, 80, 160, 240], "continuous keys every 80 ms")
}

// 6. Spotlight cell identifiers map to row kinds.
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:0,Row:0,Bundle:com.apple.applications") == "app", "applications bundle -> app")
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:1,Row:0,Bundle:com.apple.documents") == "file", "documents bundle -> file")
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:1,Row:1,Bundle:com.apple.systempreferences") == "settings_pane", "systempreferences -> settings_pane")
check(SpotlightParsing.source(forIdentifier: "Identifier:ResultCell,Section:2,Row:0,Bundle:com.apple.spotlight.related_search") == "web", "related_search -> web")
check(SpotlightParsing.folder(fromSubtitle: "text · 5 bytes · Today, 1:17 PM · \u{FFFC} AbcProjects") == "AbcProjects", "parent folder name parsed from subtitle")

check(SpotlightParsing.source(forIdentifier: "Identifier:ResultCell,Section:1,Row:2,Bundle:com.apple.parsec.web_index") == "web", "parsec web_index -> web")
check(SpotlightParsing.source(forIdentifier: "Identifier:ResultCell,Section:1,Row:2,Bundle:com.apple.parsec.kg") == "web", "parsec knowledge -> web")
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:0,Row:0,Bundle:com.apple.directories") == "folder", "directories -> folder")
// File groups seen in macOS 26.4.1 dumps: .pdf, .py, .svg files on disk.
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:1,Row:0,Bundle:com.apple.pdfs") == "file", "pdfs -> file")
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:1,Row:0,Bundle:com.apple.developer") == "file", "developer -> file")
check(SpotlightParsing.kind(forIdentifier: "Identifier:ResultCell,Section:1,Row:0,Bundle:com.apple.photos") == "file", "photos -> file")
check(SpotlightParsing.paneId(title: "Wi\u{2011}Fi", subtitle: nil) == "Wi\u{2011}Fi", "top-level pane identity is its title")
check(SpotlightParsing.paneId(title: "Wi-Fi MAC address", subtitle: "Network") == "Network", "sub-item pane identity is its breadcrumb")

// 7. Every query character maps to a real US-keyboard key code.
for ch in "abcdefghijklmnopqrstuvwxyz0123456789 .-_" {
    check(USKeyboard.keyCode(for: ch) != nil, "key code for '\(ch)'")
}
check(USKeyboard.keyCode(for: "a")?.code == 0 && USKeyboard.keyCode(for: "a")?.shift == false, "a -> 0")
check(USKeyboard.keyCode(for: "A")?.code == 0 && USKeyboard.keyCode(for: "A")?.shift == true, "A -> shift+0")
check(USKeyboard.keyCode(for: "_")?.shift == true, "_ needs shift")
check(USKeyboard.keyCode(for: "\u{200E}") == nil, "no key code for an invisible character")

// 8. Raycast rows, from token sequences observed in Raycast 2.12.1.0's accessibility tree.
do {
    typealias T = RaycastToken
    let home = "/Users/bench"
    let dirs: Set<String> = ["/Users/bench/Documents/zorvexa"]
    let files: Set<String> = ["/Users/bench/Documents/zorvexa/quelbrant-notes.txt"]
    func isDir(_ p: String) -> Bool? { dirs.contains(p) ? true : files.contains(p) ? false : nil }
    func parse(_ t: [T]) -> [RowDTO] { RaycastParsing.rows(from: t, home: home, isDirectory: isDir) }
    let fallback: [T] = [.header("Use “x” with…"), .text("Quick AI"), .text("Raycast AI"),
                         .text("Pro"), .text("Command"), .rowEnd]

    let app = parse([.header("Results"), .text("Calculator"), .text("Application"), .rowEnd,
                     .text("Calculator History"), .text("Calculator"), .text("Command"), .rowEnd]
                    + fallback)
    check(app.count == 3, "raycast: one row per row-end hint (got \(app.count))")
    check(app.first == RowDTO(title: "Calculator", kind: "app", source: "local", folder: nil,
                              paneId: nil, selected: nil, category: "raycast:Results:Application"),
          "raycast: Application row -> local app, highlight unknown")
    check(app[1].kind == "other" && app[1].source == "local", "raycast: Command row -> other")
    check(app[2].source == "web" && app[2].kind == "other" && app[2].title == "Quick AI",
          "raycast: 'Use … with…' fallback rows -> web, Pro badge ignored")

    let setting = parse([.header("Results"), .text("Bluetooth"), .text("System Settings"),
                         .text("System Setting"), .rowEnd])
    check(setting.first?.kind == "settings_pane" && setting.first?.paneId == "Bluetooth",
          "raycast: System Setting row -> settings pane identified by its title")

    let file = parse([.header("Files"), .text("quelbrant-notes.txt"),
                      .text("~/Documents/zorvexa"), .rowEnd])
    check(file.first?.kind == "file" && file.first?.folder == "/Users/bench/Documents/zorvexa",
          "raycast: Files row resolving to a file -> file with its full parent path")
    let folder = parse([.header("Files"), .text("zorvexa"), .text("~/Documents"), .rowEnd])
    check(folder.first?.kind == "folder" && folder.first?.folder == "/Users/bench/Documents",
          "raycast: Files row resolving to a directory -> folder")
    let gone = parse([.header("Files"), .text("deleted.txt"), .text("~/Documents"), .rowEnd])
    check(gone.first?.kind == "other" && gone.first?.category == "raycast:Files:unresolved",
          "raycast: Files row whose path doesn't exist -> other, labeled unresolved")

    let calcRow = parse([.header("Calculator"), .text("12"), .text("×"), .text("3"),
                         .text("Product"), .text("36"), .text("Thirty-Six"), .rowEnd])
    check(calcRow.first?.source == "instant" && calcRow.first?.kind == "other",
          "raycast: Calculator section -> instant")
}

// 9. Snapshots carry the launcher's Enter action label when it exposes one.
do {
    let clock = FakeClock()
    let launcher = LabelledLauncher()
    let keys = FakeKeys(clock: clock) { launcher.typed += $0 }
    let s = Sampler(adapter: launcher, pacer: FakePacer(clock: clock, keys: keys), clock: clock)
        .run(text: "ca", mode: .completed, windowMs: 200)
    check(s.snapshots.allSatisfy { $0.primaryAction == "Open Application" },
          "snapshots record the Enter action label")
    let plain = FakeLauncher(clock: FakeClock(), rows: [calc])
    check(plain.primaryAction() == nil, "launchers without an action label report none")
}

// 10. A slow accessibility read neither delays keys nor is credited to the moment it began.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.readRowsTakesMs = 150
    let (sampler, keys) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .continuous, windowMs: 1000)
    check(keys.posted.map { $0.0 } == [0, 80, 160, 240],
          "keys stay on the 80 ms schedule while each read takes 150 ms (got \(keys.posted.map { $0.0 }))")
    check(s.keyPosts == [0, 80, 160, 240].map { KeyPostDTO(plannedMs: $0, actualMs: $0) },
          "each key's planned and actual post time is recorded")
    check(s.maxKeyLatenessMs == 0 && s.error == nil, "on-time keys: zero lateness, no error")
    let first = s.snapshots.first
    check(first?.readStartMs == 0 && first?.readEndMs == 150,
          "a read begun at 0 that takes 150 ms is known at 150, with its start kept "
          + "(got \(first?.readStartMs ?? -1)..\(first?.readEndMs ?? -1))")
    check(s.snapshots.allSatisfy { $0.readEndMs - $0.readStartMs == 150 },
          "every snapshot carries its own read duration")
    check(zip(s.snapshots, s.snapshots.dropFirst()).allSatisfy { $0.readEndMs <= $1.readStartMs },
          "a read never starts before the previous one finished")
    check(s.snapshots.contains { $0.readStartMs >= s.finalKeyPostMs + 1000 - 150 },
          "slow reads still cover the whole window")
}

// 11. Timing is anchored to when the final key was really posted, and lateness is flagged.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    let (sampler, _) = makeSampler(launcher, clock, lateByMs: [3: 30])
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s.finalKeyPostMs == 270, "final key due at 240 but posted at 270 is reported as 270 (got \(s.finalKeyPostMs))")
    check(s.keyPosts.last == KeyPostDTO(plannedMs: 240, actualMs: 270), "the late key keeps its planned time")
    check(s.maxKeyLatenessMs == 30, "worst key lateness is exposed (got \(s.maxKeyLatenessMs))")
    check(s.error == "key_post_late", "lateness over \(Sampler.maxKeyLatenessMs) ms is a harness error")
    check((s.snapshots.last?.readStartMs ?? -1) >= 270 + 3000 - 50,
          "the window runs from the actual final key post")
    check(s.snapshots.count >= 60, "a late sample keeps its snapshots for audit")

    let clock2 = FakeClock()
    let launcher2 = FakeLauncher(clock: clock2, rows: [calc])
    let (sampler2, _) = makeSampler(launcher2, clock2, lateByMs: [1: Sampler.maxKeyLatenessMs])
    let s2 = sampler2.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s2.error == nil && s2.maxKeyLatenessMs == Sampler.maxKeyLatenessMs,
          "lateness at the threshold is recorded but not an error")
}

// 12. Keys that are never posted are a harness error, not an endless wait.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    let (sampler, _) = makeSampler(launcher, clock, lateByMs: [3: 1_000_000])
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s.error == "keys_not_posted", "a key still unposted when the window ends -> keys_not_posted")
}

// 13. Real thread, real clock: keys keep their pace while the reading thread is blocked.
do {
    let typed = TypedText()
    let clock = MonotonicClock()
    let s = Sampler(adapter: SlowLauncher(typed: typed), pacer: ThreadKeyPacer(keys: typed, clock: clock),
                    clock: clock).run(text: "calc", mode: .continuous, windowMs: 300)
    check(typed.text.withLock { $0 } == "calc", "the pacing thread posts every key in order")
    check(s.keyPosts.count == 4 && s.maxKeyLatenessMs <= Sampler.maxKeyLatenessMs && s.error == nil,
          "150 ms reads on the sampling thread do not delay keys (worst lateness \(s.maxKeyLatenessMs) ms)")
    check(s.snapshots.contains { $0.readEndMs - $0.readStartMs >= 150 },
          "real snapshots carry the read duration")
}

// 10. Tree search is bounded: a launcher's accessibility tree can loop back on itself (seen
// while Raycast restarts), which must not recurse forever.
do {
    let loop: [Int: [Int]] = [0: [1], 1: [2], 2: [0]]
    check(TreeSearch.first(from: 0, children: { loop[$0] ?? [] }, where: { $0 == 9 }) == nil,
          "search of a cyclic tree ends without a match")
    let tree: [Int: [Int]] = [0: [1, 2], 2: [3]]
    check(TreeSearch.first(from: 0, children: { tree[$0] ?? [] }, where: { $0 == 3 }) == 3,
          "search finds a nested match depth-first")
    let chain = Dictionary(uniqueKeysWithValues: (0..<500).map { ($0, [$0 + 1]) })
    check(TreeSearch.first(from: 0, children: { chain[$0] ?? [] }, where: { $0 == 499 }) == nil,
          "search stops at the depth limit (\(TreeSearch.maxDepth))")
}

// 11. Field readings that don't match what was typed (e.g. a first key lost while a launcher
// restarts) are kept as flagged evidence, never silently dropped, and never count as matches.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.dropFirstKey = true
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "notes", mode: .completed, windowMs: 300)
    let flagged = s.snapshots.filter { $0.fieldMismatch }
    check(!flagged.isEmpty && flagged.allSatisfy { $0.rows.isEmpty }
              && flagged.contains { $0.fieldText == "otes" },
          "mismatched field readings are recorded with the text the field showed, without rows")
    check(s.error == "field_never_matched", "only mismatched readings -> field_never_matched")
}

// 12. A locked screen is detected from the session dictionary (keys go to the lock screen).
check(Session.isScreenLocked(["CGSSessionScreenIsLocked": true]), "session reporting a lock -> locked")
check(!Session.isScreenLocked(["kCGSSessionOnConsoleKey": true]), "no lock key -> not locked")
check(!Session.isScreenLocked(["CGSSessionScreenIsLocked": false]), "lock key false -> not locked")

print(failures == 0 ? "ALL PASSED" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
