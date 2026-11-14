import Foundation

public protocol ProbeClock: AnyObject {
    func nowMs() -> Int
    func sleep(untilMs: Int)
}

/// Monotonic wall-independent clock (milliseconds since boot).
public final class MonotonicClock: ProbeClock, Sendable {
    public init() {}
    public func nowMs() -> Int { Int(DispatchTime.now().uptimeNanoseconds / 1_000_000) }
    public func sleep(untilMs target: Int) {
        let remainingUs = target * 1000 - Int(DispatchTime.now().uptimeNanoseconds / 1000)
        if remainingUs > 0 { usleep(useconds_t(remainingUs)) }
    }
}
