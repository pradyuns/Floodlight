import AppKit

public enum LaunchTarget: Sendable, Equatable {
    case application(URL)
    case url(URL)
}

public func launchTarget(for item: Item) -> LaunchTarget? {
    switch item.kind {
    case .app:
        return .application(URL(fileURLWithPath: item.path))
    case .settingsPane:
        guard !item.path.isEmpty, let url = URL(string: item.path) else { return nil }
        return .url(url)
    case .file, .folder:
        return .url(URL(fileURLWithPath: item.path))
    }
}

/// Opens an item. The only side effect in the core.
@MainActor
public enum Launcher {
    public static func open(_ item: Item) -> Bool {
        switch launchTarget(for: item) {
        case .application(let url)?:
            NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration())
            return true
        case .url(let url)?:
            return NSWorkspace.shared.open(url)
        case nil:
            return false
        }
    }
}
