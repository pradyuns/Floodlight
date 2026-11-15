import AppKit
import ApplicationServices

/// One item of Raycast's flattened "Root search results" group, in screen order.
public enum RaycastToken: Equatable, Sendable {
    case header(String)
    case text(String)
    /// The ⌘-number hint ("1"…"9", "0") that ends each of the first ten rows.
    case rowEnd
}

/// Pure parsing of what Raycast 2.12.1.0 exposes via Accessibility. Its UI is a web view: rows
/// are flattened static texts, so a row is the text between two ⌘-number hints. Rows after the
/// tenth carry no hint and are not read. The highlighted row is not exposed (selected = nil).
public enum RaycastParsing {
    static let badges: Set<String> = ["Pro"]

    public static func rows(
        from tokens: [RaycastToken], home: String, isDirectory: (String) -> Bool?
    ) -> [RowDTO] {
        var section = ""
        var texts: [String] = []
        var rows: [RowDTO] = []
        for token in tokens {
            switch token {
            case .header(let h):
                section = h
                texts = []
            case .text(let s):
                if !badges.contains(s) { texts.append(s) }
            case .rowEnd:
                if let first = texts.first {
                    rows.append(row(title: first, rest: Array(texts.dropFirst()), section: section,
                                    home: home, isDirectory: isDirectory))
                }
                texts = []
            }
        }
        return rows
    }

    static func row(
        title: String, rest: [String], section: String, home: String,
        isDirectory: (String) -> Bool?
    ) -> RowDTO {
        let label = rest.last ?? ""
        func make(_ kind: String, _ source: String, folder: String? = nil, paneId: String? = nil,
                  tag: String) -> RowDTO {
            RowDTO(title: title, kind: kind, source: source, folder: folder, paneId: paneId,
                   selected: nil, category: "raycast:\(section):\(tag)")
        }
        if section.hasPrefix("Use “") { return make("other", "web", tag: label) }
        if section == "Calculator" { return make("other", "instant", tag: label) }
        if section == "Files", let shown = rest.first {
            let parent = expandHome(shown, home: home)
            switch isDirectory(parent + "/" + title) {
            case true?: return make("folder", "local", folder: parent, tag: "folder")
            case false?: return make("file", "local", folder: parent, tag: "file")
            case nil: return make("other", "local", folder: parent, tag: "unresolved")
            }
        }
        switch label {
        case "Application": return make("app", "local", tag: label)
        case "System Setting": return make("settings_pane", "local", paneId: title, tag: label)
        default: return make("other", "local", tag: label)
        }
    }

    public static func expandHome(_ path: String, home: String) -> String {
        if path == "~" { return home }
        if path.hasPrefix("~/") { return home + path.dropFirst(1) }
        return path
    }
}

/// Depth-first search with a depth and visit cap: accessibility trees can be cyclic or
/// pathologically deep (Raycast's is, briefly, while it restarts).
public enum TreeSearch {
    public static let maxDepth = 64
    public static let maxVisits = 5000

    public static func first<T>(
        from root: T, children: (T) -> [T], where match: (T) -> Bool
    ) -> T? {
        var visits = 0
        func search(_ node: T, _ depth: Int) -> T? {
            guard depth < maxDepth, visits < maxVisits else { return nil }
            visits += 1
            if match(node) { return node }
            for child in children(node) {
                if let hit = search(child, depth + 1) { return hit }
            }
            return nil
        }
        return search(root, 0)
    }
}

/// Reads Raycast's main window through Accessibility; keys are sent separately by a KeyPoster.
public final class RaycastAdapter: ControlledLauncher {
    static let bundleId = "com.raycast.macos"
    static let messagingTimeout: Float = 0.5
    static let resultsTitle = "Root search results"

    public let openShortcut = (key: CGKeyCode(49), flags: CGEventFlags.maskAlternate)
    let home: String

    public init(home: String = NSHomeDirectory()) { self.home = home }

    func application() -> AXUIElement? {
        guard let pid = NSRunningApplication.runningApplications(
            withBundleIdentifier: RaycastAdapter.bundleId
        ).first?.processIdentifier else { return nil }
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, RaycastAdapter.messagingTimeout)
        return app
    }

    func find(_ element: AXUIElement, _ match: (AXUIElement) -> Bool) -> AXUIElement? {
        TreeSearch.first(from: element, children: AX.children, where: match)
    }

    func field() -> AXUIElement? {
        guard let app = application() else { return nil }
        let windows: [AXUIElement] = AX.attribute(app, kAXWindowsAttribute) ?? []
        for w in windows {
            if let f = find(w, { AX.role($0) == kAXTextFieldRole }) { return f }
        }
        return nil
    }

    public func isOpen() -> Bool { field() != nil }

    public func isFieldFocused() -> Bool? {
        field().map { AX.attribute($0, kAXFocusedAttribute) ?? false }
    }

    public func isRunning() -> Bool { application() != nil }

    /// Raycast shows no busy indicator in its accessibility tree.
    public func isBusy() -> Bool { false }

    public func isReady() -> Bool { fieldText() == .text("") }

    public func fieldText() -> FieldRead {
        guard let f = field() else { return .unreadable("no_field") }
        return AX.fieldRead(f)
    }

    public func readRows() throws -> [RowDTO] {
        guard let app = application(),
              let results = find(app, { (AX.attribute($0, kAXTitleAttribute) as String?) == RaycastAdapter.resultsTitle })
        else { throw ProbeError.noWindow }
        return RaycastParsing.rows(from: tokens(in: results), home: home) { path in
            var isDir: ObjCBool = false
            return FileManager.default.fileExists(atPath: path, isDirectory: &isDir)
                ? isDir.boolValue : nil
        }
    }

    func tokens(in results: AXUIElement) -> [RaycastToken] {
        var out: [RaycastToken] = []
        for child in AX.children(results) {
            switch AX.role(child) {
            case kAXStaticTextRole:
                let v: String = AX.attribute(child, kAXValueAttribute) ?? ""
                out.append(v.count == 1 && v.first?.isASCII == true && v.first?.isNumber == true
                           ? .rowEnd : .text(v))
            case kAXGroupRole:
                let classes: [String] = AX.attribute(child, "AXDOMClassList") ?? []
                let texts = AX.staticTexts(in: child)
                if classes.contains(where: { $0.hasPrefix("text__size-11") }) {
                    if !texts.isEmpty { out.append(.header(texts.joined())) }
                } else {
                    out += texts.map { .text($0) }
                }
            default:
                continue
            }
        }
        return out
    }

    /// The action bar's Enter button, e.g. "Open Application ↵" -> "Open Application".
    public func primaryAction() -> String? {
        guard let app = application(),
              let button = find(app, {
                  AX.role($0) == kAXButtonRole
                      && ((AX.attribute($0, kAXTitleAttribute) as String?)?.hasSuffix("↵") ?? false)
              }),
              let title: String = AX.attribute(button, kAXTitleAttribute)
        else { return nil }
        return title.dropLast().trimmingCharacters(in: .whitespaces)
    }

    /// Quits Raycast and launches it again (it does not relaunch itself the way Spotlight does).
    public func killUI() {
        for (tool, args) in [("/usr/bin/killall", ["Raycast"]),
                             ("/usr/bin/open", ["-b", RaycastAdapter.bundleId])] {
            let p = Process()
            p.executableURL = URL(fileURLWithPath: tool)
            p.arguments = args
            try? p.run()
            p.waitUntilExit()
        }
    }
}
