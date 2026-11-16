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

/// Opens an item and reports, on the main actor, whether macOS actually opened it.
@MainActor
public enum Launcher {
    public static func open(_ item: Item, completion: @escaping @MainActor (Bool) -> Void) {
        switch launchTarget(for: item) {
        case .application(let url)?:
            NSWorkspace.shared.openApplication(at: url, configuration: NSWorkspace.OpenConfiguration()) { app, error in
                let opened = app != nil && error == nil
                DispatchQueue.main.async { MainActor.assumeIsolated { completion(opened) } }
            }
        case .url(let url)? where url.isFileURL:
            // A file moved or deleted since the last scan: report it ourselves rather than letting
            // Finder show "The file can't be found" (user report).
            guard FileManager.default.fileExists(atPath: url.path) else { return completion(false) }
            completion(NSWorkspace.shared.open(url))
        case .url(let url)?:
            completion(NSWorkspace.shared.open(url))
        case nil:
            completion(false)
        }
    }
}
