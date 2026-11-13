public protocol KeyPoster: AnyObject {
    func type(_ character: String)
}

/// What the probe needs from a launcher. Every tool is read through this same channel.
public protocol LauncherAdapter: AnyObject {
    func isReady() -> Bool
    func fieldText() -> String?
    func readRows() throws -> [RowDTO]
}
