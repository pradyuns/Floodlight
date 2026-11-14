import AppKit
import ApplicationServices

/// Reads the pane list System Settings itself shows in its sidebar (macOS 26.4.1): the first
/// AXOutline in its window, one AXRow per pane, the row's title in a static text.
public enum SettingsSidebar {
    static let bundleId = "com.apple.systempreferences"
    static let messagingTimeout: Float = 1.0

    public static func titles<T>(
        root: T, children: (T) -> [T], role: (T) -> String?, value: (T) -> String?
    ) -> [String]? {
        guard let outline = TreeSearch.first(from: root, children: children, where: {
            role($0) == "AXOutline"
        }) else { return nil }
        return children(outline).filter { role($0) == "AXRow" }.compactMap { row in
            TreeSearch.first(from: row, children: children, where: {
                role($0) == "AXStaticText" && !(value($0) ?? "").isEmpty
            }).flatMap(value)
        }
    }

    /// Sidebar titles of the running System Settings' first window, or nil if unreadable.
    @MainActor public static func read() -> [String]? {
        guard let pid = NSRunningApplication.runningApplications(withBundleIdentifier: bundleId)
            .first?.processIdentifier else { return nil }
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, messagingTimeout)
        let windows: [AXUIElement] = AX.attribute(app, kAXWindowsAttribute) ?? []
        guard let window = windows.first else { return nil }
        return titles(
            root: window, children: AX.children, role: AX.role,
            value: { AX.attribute($0, kAXValueAttribute) })
    }
}
