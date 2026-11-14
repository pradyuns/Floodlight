import CoreGraphics
import Foundation
import ProbeCore

// probe dump --tool spotlight --query TEXT
// probe overhead --tool spotlight [--trials N]
// probe run-schedule --schedule FILE.jsonl --out FILE.jsonl
// Runs inside the benchmark VM. Timing happens here, never across SSH.

struct ScheduleLine: Codable {
    let queryId: String
    let text: String
    let tool: String
    let run: Int
    let condition: String
    let mode: TypingMode
    let windowMs: Int
}

struct ResultLine: Codable {
    let queryId: String
    let tool: String
    let run: Int
    let condition: String
    let mode: TypingMode
    let finalKeyPostMs: Int
    let maxKeyLatenessMs: Int
    let keyPosts: [KeyPostDTO]
    let fieldShowsMs: Int?
    let snapshots: [SnapshotDTO]
    let error: String?
    let attempt: Int
}

let escapeKey: CGKeyCode = 53
let selectAllKey: CGKeyCode = 0
let deleteKey: CGKeyCode = 51
let readyTimeoutMs = 10_000

func arg(_ name: String) -> String? {
    guard let i = CommandLine.arguments.firstIndex(of: name), i + 1 < CommandLine.arguments.count
    else { return nil }
    return CommandLine.arguments[i + 1]
}

func fail(_ message: String) -> Never {
    FileHandle.standardError.write(Data((message + "\n").utf8))
    exit(2)
}

@MainActor func adapter(for tool: String) -> any ControlledLauncher {
    switch tool {
    case "spotlight": return SpotlightAdapter()
    case "raycast": return RaycastAdapter()
    default: fail("unknown tool \(tool)")
    }
}

let clock = MonotonicClock()
let keys = CGEventKeys()

@MainActor func waitUntil(_ timeoutMs: Int, _ condition: () -> Bool) -> Bool {
    let deadline = clock.nowMs() + timeoutMs
    while clock.nowMs() < deadline {
        if condition() { return true }
        usleep(50_000)
    }
    return condition()
}

@MainActor func close(_ launcher: any ControlledLauncher) {
    for _ in 0..<4 where launcher.isOpen() {
        keys.press(keyCode: escapeKey)
        usleep(300_000)
    }
}

/// Closes, optionally restarts the UI process, opens, and waits for an empty, idle field.
@MainActor func prepare(_ launcher: any ControlledLauncher, uiRestart: Bool) -> Bool {
    close(launcher)
    if launcher.isOpen() { return false }
    if uiRestart {
        launcher.killUI()
        // Wait for the launcher's UI process to be running again before asking it to open.
        guard waitUntil(readyTimeoutMs, { launcher.isRunning() }) else { return false }
        usleep(500_000)
    }
    var opened = false
    for _ in 0..<3 where !opened {
        keys.press(keyCode: launcher.openShortcut.key, flags: launcher.openShortcut.flags)
        opened = waitUntil(3000) { launcher.isOpen() }
    }
    guard opened else { return false }
    // Launchers can reopen with the previous search text still in the field; clear it.
    if launcher.fieldText() != "" {
        keys.press(keyCode: selectAllKey, flags: .maskCommand)
        keys.press(keyCode: deleteKey)
    }
    return waitUntil(readyTimeoutMs) { launcher.isReady() }
}

let encoder = JSONEncoder()
encoder.keyEncodingStrategy = .convertToSnakeCase
let decoder = JSONDecoder()
decoder.keyDecodingStrategy = .convertFromSnakeCase

switch CommandLine.arguments.dropFirst().first {
case "dump":
    let launcher = adapter(for: arg("--tool") ?? "spotlight")
    guard let query = arg("--query") else { fail("--query required") }
    guard !Session.isScreenLockedNow() else { fail("screen is locked: keys would go to the lock screen") }
    guard prepare(launcher, uiRestart: false) else { fail("launcher not ready") }
    let sample = Sampler(adapter: launcher, pacer: ThreadKeyPacer(keys: keys, clock: clock), clock: clock)
        .run(text: query, mode: .completed, windowMs: 2500)
    close(launcher)
    let rows = sample.snapshots.last?.rows ?? []
    print(String(data: try encoder.encode(rows), encoding: .utf8) ?? "[]")
    if let error = sample.error { fail("error: \(error)") }

case "state":
    let launcher = adapter(for: arg("--tool") ?? "spotlight")
    let rows = (try? launcher.readRows()) ?? []
    print("open=\(launcher.isOpen()) field=\(launcher.fieldText().map { "'\($0)'" } ?? "nil") "
        + "focused=\(launcher.isFieldFocused().map(String.init) ?? "nil") "
        + "busy=\(launcher.isBusy()) ready=\(launcher.isReady()) rows=\(rows.count)")

case "overhead":
    let launcher = adapter(for: arg("--tool") ?? "spotlight")
    let trials = Int(arg("--trials") ?? "10") ?? 10
    guard !Session.isScreenLockedNow() else { fail("screen is locked: keys would go to the lock screen") }
    var echo: [Int] = []
    var read: [Int] = []
    for _ in 0..<trials {
        guard prepare(launcher, uiRestart: false) else { fail("launcher not ready") }
        let t0 = clock.nowMs()
        keys.type("a")
        if waitUntil(2000, { launcher.fieldText() == "a" }) { echo.append(clock.nowMs() - t0) }
        let r0 = clock.nowMs()
        _ = try? launcher.readRows()
        read.append(clock.nowMs() - r0)
        close(launcher)
    }
    func median(_ xs: [Int]) -> Int { xs.sorted()[xs.count / 2] }
    guard !echo.isEmpty else { fail("field never echoed a key") }
    print("{\"key_to_field_ms_median\": \(median(echo)), \"key_to_field_ms_max\": \(echo.max()!), "
        + "\"ax_read_ms_median\": \(median(read)), \"ax_read_ms_max\": \(read.max()!), "
        + "\"trials\": \(echo.count), \"poll_resolution_ms\": 50}")

case "run-schedule":
    guard let schedulePath = arg("--schedule"), let outPath = arg("--out") else {
        fail("--schedule and --out required")
    }
    let lines = try String(contentsOfFile: schedulePath, encoding: .utf8)
        .split(separator: "\n").map { try decoder.decode(ScheduleLine.self, from: Data($0.utf8)) }
    FileManager.default.createFile(atPath: outPath, contents: nil)
    guard let out = FileHandle(forWritingAtPath: outPath) else { fail("cannot write \(outPath)") }
    for line in lines {
        let launcher = adapter(for: line.tool)
        var result: SampleDTO
        if Session.isScreenLockedNow() {
            result = SampleDTO(keyPosts: [], fieldShowsMs: nil, snapshots: [], error: "screen_locked")
        } else if prepare(launcher, uiRestart: line.condition == "ui_restart") {
            result = Sampler(adapter: launcher, pacer: ThreadKeyPacer(keys: keys, clock: clock),
                             clock: clock)
                .run(text: line.text, mode: line.mode, windowMs: line.windowMs)
        } else {
            result = SampleDTO(keyPosts: [], fieldShowsMs: nil, snapshots: [], error: "not_ready")
        }
        close(launcher)
        let record = ResultLine(
            queryId: line.queryId, tool: line.tool, run: line.run, condition: line.condition,
            mode: line.mode, finalKeyPostMs: result.finalKeyPostMs,
            maxKeyLatenessMs: result.maxKeyLatenessMs, keyPosts: result.keyPosts,
            fieldShowsMs: result.fieldShowsMs, snapshots: result.snapshots, error: result.error,
            attempt: 0)
        out.write(try encoder.encode(record))
        out.write(Data("\n".utf8))
    }
    try out.close()

default:
    fail("usage: probe dump|overhead|run-schedule ...")
}
