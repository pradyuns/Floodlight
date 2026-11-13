import Foundation

public protocol ProbeClock: AnyObject {
    func nowMs() -> Int
    func sleep(untilMs: Int)
}

/// Monotonic wall-independent clock (milliseconds since boot).
public final class MonotonicClock: ProbeClock {
    public init() {}
    public func nowMs() -> Int { Int(DispatchTime.now().uptimeNanoseconds / 1_000_000) }
    public func sleep(untilMs target: Int) {
        let remaining = target - nowMs()
        if remaining > 0 { usleep(useconds_t(remaining * 1000)) }
    }
}
