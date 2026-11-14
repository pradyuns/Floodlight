import CoreGraphics

public protocol KeyPoster: AnyObject {
    func type(_ character: String)
}

/// What the probe needs from a launcher. Every tool is read through this same channel.
public protocol LauncherAdapter: AnyObject {
    func isReady() -> Bool
    func fieldText() -> String?
    func readRows() throws -> [RowDTO]
    func primaryAction() -> String?
}

extension LauncherAdapter {
    public func primaryAction() -> String? { nil }
}

/// A launcher the probe can open, close and restart, on top of reading it.
public protocol ControlledLauncher: LauncherAdapter {
    var openShortcut: (key: CGKeyCode, flags: CGEventFlags) { get }
    func isOpen() -> Bool
    func isRunning() -> Bool
    func isBusy() -> Bool
    /// Whether the search field has keyboard focus (nil: the field isn't there to ask).
    func isFieldFocused() -> Bool?
    func killUI()
}
