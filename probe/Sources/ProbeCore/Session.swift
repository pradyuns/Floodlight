import CoreGraphics

/// The login session the probe types into. A locked screen swallows every key.
public enum Session {
    public static func isScreenLocked(_ info: [String: Any]) -> Bool {
        (info["CGSSessionScreenIsLocked"] as? Bool) ?? false
    }

    /// No session dictionary means no console session to type into: treated as locked.
    public static func isScreenLockedNow() -> Bool {
        guard let info = CGSessionCopyCurrentDictionary() as? [String: Any] else { return true }
        return isScreenLocked(info)
    }
}
