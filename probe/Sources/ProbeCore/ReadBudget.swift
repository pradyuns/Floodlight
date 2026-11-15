import Foundation

/// Bounds one whole launcher read. While a budget is active, every accessibility call is given
/// only the time left as its messaging timeout, set on the element it is made on (so nothing
/// depends on whether child elements inherit a timeout), and once the time is gone further calls
/// fail at once. A read that ran out is discarded by the caller, never kept as a partial result.
public final class ReadBudget: @unchecked Sendable {
    public static let shared = ReadBudget()
    private let lock = NSLock()
    private var deadlineMs: Int?
    private var hit = false
    private var clock: (any ProbeClock)?

    public init() {}

    public func begin(ms: Int, clock: any ProbeClock) {
        lock.withLock {
            self.clock = clock
            deadlineMs = clock.nowMs() + ms
            hit = false
        }
    }

    /// Ends the read and reports whether it ran out of budget.
    public func end() -> Bool {
        lock.withLock {
            defer {
                deadlineMs = nil
                clock = nil
            }
            guard let deadline = deadlineMs, let clock else { return false }
            return hit || clock.nowMs() > deadline
        }
    }

    /// Seconds the next call may take (at most `cap`); nil when the budget is spent. With no
    /// active budget, `cap`.
    public func nextCallTimeout(cap: Float) -> Float? {
        lock.withLock {
            guard let deadline = deadlineMs, let clock else { return cap }
            let left = deadline - clock.nowMs()
            if left <= 0 {
                hit = true
                return nil
            }
            return min(cap, Float(left) / 1000)
        }
    }
}
