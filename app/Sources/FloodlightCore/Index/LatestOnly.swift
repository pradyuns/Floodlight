/// Numbers background jobs so that only the newest one may publish: builds started later can
/// finish earlier, and an older finisher must not replace their result.
public struct LatestOnly: Sendable {
    private var latest = 0

    public init() {}

    public mutating func begin() -> Int {
        latest += 1
        return latest
    }

    public func mayPublish(_ job: Int) -> Bool { job == latest }
}
