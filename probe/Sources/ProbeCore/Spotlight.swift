import AppKit
import ApplicationServices

/// Pure parsing of what Spotlight exposes via Accessibility (macOS 26.4.1).
/// Each result is an AXCell whose AXIdentifier looks like
/// "Identifier:ResultCell,Section:0,Row:0,Bundle:com.apple.applications".
public enum SpotlightParsing {
    static let instantBundles: Set<String> = [
        "com.apple.dictionary", "com.apple.calculation", "com.apple.conversion",
    ]

    public static func bundle(forIdentifier id: String) -> String? {
        id.split(separator: ",").first { $0.hasPrefix("Bundle:") }.map { String($0.dropFirst(7)) }
    }

    public static func kind(forIdentifier id: String, subtitle: String? = nil) -> String {
        switch bundle(forIdentifier: id) {
        case "com.apple.applications": return "app"
        case "com.apple.systempreferences": return "settings_pane"
        case "com.apple.directories": return "folder"
        case "com.apple.documents": return "file"
        default: return "other"
        }
    }

    public static func source(forIdentifier id: String) -> String {
        guard let b = bundle(forIdentifier: id) else { return "local" }
        if b == "com.apple.spotlight.related_search" || b.hasPrefix("com.apple.parsec.") {
            return "web"
        }
        return instantBundles.contains(b) ? "instant" : "local"
    }

    /// Settings results: a top-level pane has no breadcrumb (identity = title); a setting
    /// inside a pane shows its pane breadcrumb, e.g. "General → Language & Region".
    public static func paneId(title: String, subtitle: String?) -> String {
        guard let s = subtitle, !s.isEmpty else { return title }
        return s
    }

    /// File subtitles end with the parent folder's name, e.g. "text · 5 bytes · Today · ￼ Docs".
    public static func folder(fromSubtitle subtitle: String) -> String? {
        guard let last = subtitle.components(separatedBy: " · ").last else { return nil }
        let cleaned = last.replacingOccurrences(of: "\u{FFFC}", with: "")
            .trimmingCharacters(in: .whitespaces)
        return cleaned.isEmpty ? nil : cleaned
    }
}

enum AX {
    static func attribute<T>(_ element: AXUIElement, _ name: String) -> T? {
        var value: CFTypeRef?
        guard AXUIElementCopyAttributeValue(element, name as CFString, &value) == .success
        else { return nil }
        return value as? T
    }

    static func children(_ element: AXUIElement) -> [AXUIElement] {
        attribute(element, kAXChildrenAttribute) ?? []
    }

    static func role(_ element: AXUIElement) -> String? { attribute(element, kAXRoleAttribute) }

    static func staticTexts(in element: AXUIElement) -> [String] {
        var out: [String] = []
        for child in children(element) {
            if role(child) == kAXStaticTextRole, let v: String = attribute(child, kAXValueAttribute) {
                out.append(v)
            } else {
                out += staticTexts(in: child)
            }
        }
        return out
    }
}

/// Reads Spotlight's panel through Accessibility; keys are sent separately by a KeyPoster.
public final class SpotlightAdapter: LauncherAdapter {
    static let bundleId = "com.apple.Spotlight"
    static let messagingTimeout: Float = 0.5

    public init() {}

    func window() -> AXUIElement? {
        guard let pid = NSRunningApplication.runningApplications(
            withBundleIdentifier: SpotlightAdapter.bundleId
        ).first?.processIdentifier else { return nil }
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, SpotlightAdapter.messagingTimeout)
        let windows: [AXUIElement] = AX.attribute(app, kAXWindowsAttribute) ?? []
        return windows.first
    }

    func walk(_ element: AXUIElement, _ visit: (AXUIElement) -> Bool) {
        guard visit(element) else { return }
        for child in AX.children(element) { walk(child, visit) }
    }

    public func isOpen() -> Bool { window() != nil }

    public func isRunning() -> Bool {
        !NSRunningApplication.runningApplications(withBundleIdentifier: SpotlightAdapter.bundleId)
            .isEmpty
    }

    public func isBusy() -> Bool {
        guard let w = window() else { return false }
        var busy = false
        walk(w) { e in
            if AX.role(e) == "AXBusyIndicator" { busy = true }
            return !busy
        }
        return busy
    }

    public func isReady() -> Bool {
        window() != nil && fieldText() == "" && !isBusy()
    }

    public func fieldText() -> String? {
        guard let w = window() else { return nil }
        var text: String?
        walk(w) { e in
            if text == nil, let id: String = AX.attribute(e, "AXIdentifier"),
               id == "SpotlightSearchField", AX.role(e) == kAXTextFieldRole {
                text = AX.attribute(e, kAXValueAttribute) ?? ""
            }
            return text == nil
        }
        return text
    }

    public func readRows() throws -> [RowDTO] {
        guard let w = window() else { throw ProbeError.noWindow }
        var rows: [RowDTO] = []
        walk(w) { e in
            guard AX.role(e) == "AXCell", let id: String = AX.attribute(e, "AXIdentifier"),
                  id.contains("Cell,") else { return true }
            let texts = AX.staticTexts(in: e)
            let subtitle = texts.count > 1 ? texts[1] : nil
            let kind = SpotlightParsing.kind(forIdentifier: id, subtitle: subtitle)
            rows.append(RowDTO(
                title: texts.first ?? "",
                kind: kind,
                source: SpotlightParsing.source(forIdentifier: id),
                folder: kind == "file" || kind == "folder"
                    ? subtitle.flatMap(SpotlightParsing.folder(fromSubtitle:)) : nil,
                paneId: kind == "settings_pane"
                    ? SpotlightParsing.paneId(title: texts.first ?? "", subtitle: subtitle) : nil,
                selected: AX.attribute(e, kAXSelectedAttribute),
                category: SpotlightParsing.bundle(forIdentifier: id)))
            return false
        }
        return rows
    }

    public func killUI() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/killall")
        p.arguments = ["Spotlight"]
        try? p.run()
        p.waitUntilExit()
    }
}

public enum ProbeError: Error {
    case noWindow
    case notReady
}

/// Posts real keyboard events (the launcher sees them exactly like a person typing).
public final class CGEventKeys: KeyPoster {
    public init() {}

    /// Sends the character as a real US-keyboard key press. Characters with no key are
    /// rejected loudly rather than silently skipped.
    public func type(_ character: String) {
        guard let ch = character.first, let key = USKeyboard.keyCode(for: ch) else {
            FileHandle.standardError.write(Data("no key code for '\(character)'\n".utf8))
            return
        }
        press(keyCode: key.code, flags: key.shift ? .maskShift : [])
    }

    public func press(keyCode: CGKeyCode, flags: CGEventFlags = []) {
        for down in [true, false] {
            guard let event = CGEvent(keyboardEventSource: nil, virtualKey: keyCode, keyDown: down)
            else { continue }
            event.flags = flags
            event.post(tap: .cghidEventTap)
        }
    }
}
