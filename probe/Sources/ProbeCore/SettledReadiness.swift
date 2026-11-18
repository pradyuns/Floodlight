/// Waits for a ready read, pauses, and re-reads. A failed re-read goes back to waiting, within
/// one deadline; when the first re-read succeeds this is a single wait, pause and read.
public struct SettledReadiness {
    public struct Outcome: Equatable, Sendable {
        public let ready: Bool
        public let failedRechecks: Int
        public init(ready: Bool, failedRechecks: Int) {
            self.ready = ready
            self.failedRechecks = failedRechecks
        }
    }

    let clock: any ProbeClock
    let pollMs: Int
    let isReady: () -> Bool

    public init(clock: any ProbeClock, pollMs: Int = 50, isReady: @escaping () -> Bool) {
        self.clock = clock
        self.pollMs = pollMs
        self.isReady = isReady
    }

    public func wait(timeoutMs: Int, settleMs: Int) -> Outcome {
        let deadline = clock.nowMs() + timeoutMs
        var failed = 0
        while true {
            guard waitForReady(until: deadline) else { return Outcome(ready: false, failedRechecks: failed) }
            clock.sleep(untilMs: clock.nowMs() + settleMs)
            if isReady() { return Outcome(ready: true, failedRechecks: failed) }
            failed += 1
            if clock.nowMs() >= deadline { return Outcome(ready: false, failedRechecks: failed) }
        }
    }

    private func waitForReady(until deadline: Int) -> Bool {
        while clock.nowMs() < deadline {
            if isReady() { return true }
            clock.sleep(untilMs: min(clock.nowMs() + pollMs, deadline))
        }
        return isReady()
    }
}
