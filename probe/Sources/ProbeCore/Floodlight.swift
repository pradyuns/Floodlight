import AppKit
import ApplicationServices

/// Pure parsing of a Floodlight results row: its static texts are the title, then the kind label.
public enum FloodlightParsing {
    public static func row(texts: [String], selected: Bool?, home: String = NSHomeDirectory()) -> RowDTO? {
        guard let title = texts.first else { return nil }
        let label = texts.dropFirst().last ?? ""
        let parent = texts.count >= 3 ? RaycastParsing.expandHome(texts[1], home: home) : nil
        let kind: String
        switch label {
        case "Application": kind = "app"
        case "System Settings": kind = "settings_pane"
        case "Folder": kind = "folder"
        case "Document": kind = "file"
        default: kind = "other"
        }
        return RowDTO(title: title, kind: kind, source: "local",
                      folder: kind == "folder" || kind == "file" ? parent : nil,
                      paneId: kind == "settings_pane" ? title : nil, selected: selected,
                      category: "floodlight:\(label)")
    }
}

/// Reads Floodlight's panel through Accessibility; keys are sent separately by a KeyPoster.
public final class FloodlightAdapter: ControlledLauncher {
    static let bundleId = "app.floodlight.Floodlight"
    static let messagingTimeout: Float = 0.5
    static let fieldId = "floodlight.search"
    static let resultsId = "floodlight.results"

    public let openShortcut = (key: CGKeyCode(49), flags: CGEventFlags.maskControl)

    let home: String

    public init(home: String = NSHomeDirectory()) { self.home = home }

    func application() -> AXUIElement? {
        guard let pid = NSRunningApplication.runningApplications(
            withBundleIdentifier: FloodlightAdapter.bundleId
        ).first?.processIdentifier else { return nil }
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, FloodlightAdapter.messagingTimeout)
        return app
    }

    func find(_ id: String) -> AXUIElement? {
        guard let app = application() else { return nil }
        let windows: [AXUIElement] = AX.attribute(app, kAXWindowsAttribute) ?? []
        for w in windows {
            if let hit = TreeSearch.first(from: w, children: AX.children, where: {
                (AX.attribute($0, kAXIdentifierAttribute) as String?) == id
            }) { return hit }
        }
        return nil
    }

    public func isOpen() -> Bool { find(FloodlightAdapter.fieldId) != nil }

    public func isFieldFocused() -> Bool? {
        find(FloodlightAdapter.fieldId).map { AX.attribute($0, kAXFocusedAttribute) ?? false }
    }

    public func isRunning() -> Bool { application() != nil }

    public func isBusy() -> Bool { false }

    public func isReady() -> Bool { fieldText() == .text("") }

    public func fieldText() -> FieldRead {
        guard let f = find(FloodlightAdapter.fieldId) else { return .unreadable("no_field") }
        return AX.fieldRead(f)
    }

    /// An open panel with a non-empty query and no matches has no results table rows; that is an
    /// empty list, not an error.
    public func readRows() throws -> [RowDTO] {
        guard isOpen() else { throw ProbeError.noWindow }
        guard let table = find(FloodlightAdapter.resultsId) else { return [] }
        let rows: [AXUIElement] = AX.attribute(table, kAXRowsAttribute) ?? []
        return rows.compactMap { row in
            FloodlightParsing.row(texts: AX.staticTexts(in: row), selected: AX.attribute(row, kAXSelectedAttribute), home: home)
        }
    }

    public func uiPids() -> Set<Int32> { runningPids(bundleId: FloodlightAdapter.bundleId) }
    public func terminateUI() { runTool("/usr/bin/killall", ["Floodlight"]) }
    public let relaunchUI: (() -> Void)? = { runTool("/usr/bin/open", ["-b", FloodlightAdapter.bundleId]) }
}
