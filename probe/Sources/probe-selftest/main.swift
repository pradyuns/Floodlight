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
    /// From this time on, reading the field fails (e.g. an accessibility error).
    var fieldUnreadableFromMs: Int?
    var rowsFail = false
    /// Row reads made of this many accessibility calls, each taking readRowsTakesMs / calls and
    /// each asking the read budget for time first, as the real accessibility layer does.
    var rowCalls = 1

    init(clock: FakeClock, echoDelayMs: Int = 0, rows: [RowDTO]) {
        self.clock = clock
        self.echoDelayMs = echoDelayMs
        self.rowsForQuery = rows
    }
    func isReady() -> Bool { ready }
    func fieldText() -> FieldRead {
        if let t = fieldUnreadableFromMs, clock.now >= t { return .unreadable("ax_error_-25204") }
        let visible = echoedAt.filter { $0.key + echoDelayMs <= clock.now }.max { $0.key < $1.key }
        return .text(visible?.value ?? "")
    }
    /// Rows follow whatever the field currently shows; before the field shows any of the new
    /// query, the previous query's rows are still on screen.
    func readRows() throws -> [RowDTO] {
        if rowsFail { throw ProbeError.noWindow }
        guard case .text(let f) = fieldText() else { throw ProbeError.noWindow }
        for _ in 0..<rowCalls {
            guard ReadBudget.shared.nextCallTimeout(cap: 0.5) != nil else { return [] }
            clock.spend(readRowsTakesMs / rowCalls)
        }
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
    func fieldText() -> FieldRead { .text(typed) }
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
    func fieldText() -> FieldRead { .text(typed.text.withLock { $0 }) }
    func readRows() throws -> [RowDTO] {
        usleep(100_000)
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
    check(!blank.isEmpty && blank.allSatisfy { $0.rows.isEmpty && $0.unreadable == nil },
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
          "100 ms reads on the sampling thread do not delay keys (worst lateness \(s.maxKeyLatenessMs) ms)")
    check(s.snapshots.contains { $0.readEndMs - $0.readStartMs >= 100 },
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

// System Settings sidebar: row titles of the first outline, in order; text elsewhere ignored.
do {
    struct Node { let role: String; var value: String? = nil; var kids: [Node] = [] }
    func row(_ title: String) -> Node {
        Node(role: "AXRow", kids: [Node(role: "AXCell", kids: [Node(role: "AXImage"), Node(role: "AXStaticText", value: title)])])
    }
    let window = Node(role: "AXWindow", kids: [
        Node(role: "AXStaticText", value: "Search"),
        Node(role: "AXScrollArea", kids: [Node(role: "AXOutline", kids: [
            row("Wi‑Fi"), Node(role: "AXRow", kids: [Node(role: "AXCell")]), row("Bluetooth"), Node(role: "AXColumn"),
        ])]),
        Node(role: "AXGroup", kids: [Node(role: "AXStaticText", value: "Pane body")]),
    ])
    let titles = SettingsSidebar.titles(root: window, children: { $0.kids }, role: { $0.role }, value: { $0.value })
    check(titles == ["Wi‑Fi", "Bluetooth"], "sidebar titles come from outline rows only, in order")
    check(SettingsSidebar.titles(root: Node(role: "AXWindow"), children: { $0.kids }, role: { $0.role }, value: { $0.value }) == nil,
          "no outline -> nil, not an empty sidebar")
}

// A failed field read is recorded as unreadable, never as an empty field.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.fieldUnreadableFromMs = 0
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "home", mode: .completed, windowMs: 3000)
    let afterTyping = s.snapshots.filter { $0.readStartMs > 0 }
    check(!afterTyping.isEmpty && afterTyping.allSatisfy { $0.unreadable == "field:ax_error_-25204" },
          "failed field reads are kept as unreadable snapshots with their reason")
    check(afterTyping.allSatisfy { $0.rows.isEmpty }, "unreadable snapshots carry no rows")
    check(s.error == "ax_read_failed", "only unreadable reads -> ax_read_failed (got \(s.error ?? "nil"))")
}

// A read that fails partway through a sample leaves the earlier readable snapshots intact.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.fieldUnreadableFromMs = 1000
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s.snapshots.contains { $0.unreadable == nil && $0.fieldText == "calc" && !$0.rows.isEmpty },
          "readable snapshots before the failure are kept")
    check(s.snapshots.filter { $0.readStartMs >= 1000 }.allSatisfy { $0.unreadable != nil },
          "every read after the failure is marked unreadable")
    check(s.error == nil, "a sample with readable matching snapshots is not an error")
}

// A failed row read is recorded as unreadable, not silently skipped.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.rowsFail = true
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    let failed = s.snapshots.filter { $0.unreadable?.hasPrefix("rows:") ?? false }
    check(failed.count >= 50, "row-read failures are recorded (got \(failed.count))")
    check(failed.allSatisfy { $0.rows.isEmpty && $0.fieldText == "calc" || $0.fieldText.count < 4 },
          "an unreadable-rows snapshot keeps the field text it read")
    check(s.error == "ax_read_failed", "only unreadable rows -> ax_read_failed")
}

// The accessibility value of a text field maps to a field reading.
check(AX.fieldRead(status: .success, value: "calc" as CFString) == .text("calc"), "AX string value -> text")
check(AX.fieldRead(status: .success, value: "" as CFString) == .text(""), "AX empty string -> empty text")
check(AX.fieldRead(status: .cannotComplete, value: nil) == .unreadable("ax_error_-25204"),
      "AX error -> unreadable with its code")
check(AX.fieldRead(status: .noValue, value: nil) == .unreadable("ax_error_-25212"),
      "AX no-value -> unreadable (whether an empty field reports this is checked in the VM)")
check(AX.fieldRead(status: .success, value: 3 as CFNumber) == .unreadable("not_a_string"),
      "AX non-string value -> unreadable")

// The read budget gives each call only the time left, and nothing once it is spent.
do {
    let clock = FakeClock()
    let budget = ReadBudget()
    check(budget.nextCallTimeout(cap: 0.5) == 0.5, "no active budget -> the normal per-call cap")
    budget.begin(ms: 150, clock: clock)
    clock.spend(100)
    check(budget.nextCallTimeout(cap: 0.5) == 0.05, "100 ms into a 150 ms budget -> 0.05 s for the next call")
    clock.spend(50)
    check(budget.nextCallTimeout(cap: 0.5) == nil, "a spent budget allows no further call")
    check(budget.end(), "a read that ran out of budget reports it")
    budget.begin(ms: 150, clock: clock)
    clock.spend(160)
    check(budget.end(), "a read that finished after its deadline is over budget even without another call")
    budget.begin(ms: 150, clock: clock)
    clock.spend(150)
    check(!budget.end(), "a read finishing exactly at its deadline is within budget")
}

// A read that runs past its budget is discarded as unreadable, never kept as a partial result.
do {
    let clock = FakeClock()
    let launcher = FakeLauncher(clock: clock, rows: [calc])
    launcher.readRowsTakesMs = 300
    launcher.rowCalls = 10
    let (sampler, _) = makeSampler(launcher, clock)
    let s = sampler.run(text: "calc", mode: .completed, windowMs: 3000)
    let afterTyping = s.snapshots.filter { $0.readStartMs > 0 }
    check(!afterTyping.isEmpty && afterTyping.allSatisfy { $0.unreadable == "deadline" && $0.rows.isEmpty },
          "over-budget reads are unreadable with reason 'deadline' and no rows")
    check(afterTyping.allSatisfy { $0.readEndMs - $0.readStartMs <= Sampler.readBudgetMs + 30 },
          "an over-budget read stops within one call of its budget")
    check(s.fieldShowsMs == nil, "an over-budget read never counts as the field showing the text")
    check(s.error == "ax_read_failed", "only over-budget reads -> ax_read_failed (got \(s.error ?? "nil"))")

    let clock2 = FakeClock()
    let quick = FakeLauncher(clock: clock2, rows: [calc])
    quick.readRowsTakesMs = 100
    quick.rowCalls = 10
    let (sampler2, _) = makeSampler(quick, clock2)
    let s2 = sampler2.run(text: "calc", mode: .completed, windowMs: 3000)
    check(s2.error == nil && s2.snapshots.contains { $0.unreadable == nil && !$0.rows.isEmpty },
          "reads within the budget are kept")
}

// Floodlight rows: title then kind label, as its table exposes them.
check(FloodlightParsing.row(texts: ["Calculator", "Application"], selected: true)
      == RowDTO(title: "Calculator", kind: "app", source: "local", folder: nil, paneId: nil, selected: true,
                category: "floodlight:Application"), "floodlight app row")
check(FloodlightParsing.row(texts: ["Wi\u{2011}Fi", "System Settings"], selected: false)?.paneId == "Wi\u{2011}Fi"
      && FloodlightParsing.row(texts: ["Wi\u{2011}Fi", "System Settings"], selected: false)?.kind == "settings_pane",
      "floodlight settings row")
check(FloodlightParsing.row(texts: ["szx-621", "~/Documents", "Folder"], selected: false, home: "/Users/bench")
      == RowDTO(title: "szx-621", kind: "folder", source: "local", folder: "/Users/bench/Documents", paneId: nil,
                selected: false, category: "floodlight:Folder"), "floodlight folder row with parent")
check(FloodlightParsing.row(texts: [], selected: false) == nil, "floodlight row with no text is skipped")

/// A launcher's UI processes: ending one takes `exitAfterPolls` checks; a relaunch adds a new pid.
final class FakeProcesses {
    var running: Set<Int32> = [100]
    var dying: Set<Int32> = []
    var pollsLeft = 0
    var relaunchedWhileOldAlive = false
    var relaunches = 0
    var respawnsItself = false
    let exitAfterPolls: Int
    init(exitAfterPolls: Int) { self.exitAfterPolls = exitAfterPolls }
    func pids() -> Set<Int32> {
        if !dying.isEmpty {
            if pollsLeft == 0 {
                running.subtract(dying); dying = []
                if respawnsItself { running.insert(300) }
            } else { pollsLeft -= 1 }
        }
        return running
    }
    func terminate() { dying = running; pollsLeft = exitAfterPolls }
    func relaunch() {
        relaunches += 1
        if !dying.isEmpty { relaunchedWhileOldAlive = true; return }  // reaches the exiting app: no-op
        running.insert(200)
    }
    func restart(selfRelaunching: Bool = false, polls: Int = 200) -> Bool {
        UIRestart(pids: pids, terminate: terminate, relaunch: selfRelaunching ? nil : relaunch,
                  waitUntil: { _, condition in (0..<polls).contains { _ in condition() } })
            .run(timeoutMs: 10_000)
    }
}

let slowExit = FakeProcesses(exitAfterPolls: 5)
check(slowExit.restart() && !slowExit.relaunchedWhileOldAlive && slowExit.running == [200],
      "UI restart relaunches only after the old process has exited")
let neverExits = FakeProcesses(exitAfterPolls: 1_000)
check(!neverExits.restart() && neverExits.relaunches == 0,
      "UI restart fails without relaunching when the old process never exits")
let noRespawn = FakeProcesses(exitAfterPolls: 3)
check(!noRespawn.restart(selfRelaunching: true),
      "UI restart does not count the old process as running again")
let respawns = FakeProcesses(exitAfterPolls: 3)
respawns.respawnsItself = true
check(respawns.restart(selfRelaunching: true) && respawns.running == [300] && respawns.relaunches == 0,
      "UI restart of a self-relaunching launcher waits for its new process")

/// Readiness reads answered from a script (the last answer repeats); each read costs `readMs`.
func settled(_ answers: [Bool], readMs: [Int] = [], timeoutMs: Int = 10_000) -> (SettledReadiness.Outcome, Int, Int) {
    let clock = FakeClock()
    var reads = 0
    let outcome = SettledReadiness(clock: clock) {
        clock.spend(reads < readMs.count ? readMs[reads] : 5)
        defer { reads += 1 }
        return answers[min(reads, answers.count - 1)]
    }.wait(timeoutMs: timeoutMs, settleMs: 300)
    return (outcome, reads, clock.nowMs())
}

let steady = settled([true, true])
check(steady.0 == .init(ready: true, failedRechecks: 0) && steady.1 == 2,
      "settled readiness: ready, pause, one re-read, as before")
let stall = settled([true, false, true, true], readMs: [5, 2000])
check(stall.0 == .init(ready: true, failedRechecks: 1) && stall.1 == 4,
      "settled readiness: a stalled re-read is retried within the deadline")
let neverSettles = settled([true, false])
check(!neverSettles.0.ready && neverSettles.0.failedRechecks >= 1 && neverSettles.2 <= 10_000 + 300 + 5 + 5,
      "settled readiness: gives up by the deadline when re-reads keep failing")
let neverReady = settled([false])
check(neverReady.0 == .init(ready: false, failedRechecks: 0),
      "settled readiness: never ready is not ready")

/// Readiness that depends on the time a read finishes; returns the outcome and every read's start time.
func settledAt(timeoutMs: Int = 10_000, readMs: @escaping (Int) -> Int = { _ in 5 },
               ready: @escaping (Int) -> Bool) -> (SettledReadiness.Outcome, [Int]) {
    let clock = FakeClock()
    var starts: [Int] = []
    let outcome = SettledReadiness(clock: clock) {
        starts.append(clock.nowMs())
        clock.spend(readMs(starts.count - 1))
        return ready(clock.nowMs())
    }.wait(timeoutMs: timeoutMs, settleMs: 300)
    return (outcome, starts)
}

check(!settledAt(readMs: { $0 == 0 ? 10_005 : 5 }, ready: { _ in true }).0.ready,
      "settled readiness: a ready first read that finishes after the deadline is not ready")
check(!settledAt(readMs: { $0 == 1 ? 9_700 : 5 }, ready: { _ in true }).0.ready,
      "settled readiness: a ready re-read that finishes after the deadline is not ready")
let noRoom = settledAt(readMs: { $0 == 0 ? 9_800 : 5 }, ready: { _ in true })
check(!noRoom.0.ready && noRoom.1.count == 1,
      "settled readiness: no pause or re-read when the pause cannot finish before the deadline")
let expired = settledAt(ready: { $0 >= 10_000 })
check(!expired.0.ready && expired.1.allSatisfy { $0 < 10_000 },
      "settled readiness: no read starts after the deadline, and late readiness is not ready")

print(failures == 0 ? "ALL PASSED" : "\(failures) FAILED")
exit(failures == 0 ? 0 : 1)
