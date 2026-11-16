import Foundation

/// Folders and files under the home folder. Skips dot-files, ~/Library and package contents;
/// apps are AppSource's job.
public struct FileSource: Sendable {
    /// Dependency, environment and cache folders: thousands of files nobody searches for by name.
    public static let skippedFolders: Set<String> = [
        "node_modules", "bower_components", "Pods", "Carthage", "venv", "site-packages",
        "__pycache__", "DerivedData",
    ]

    public let root: URL
    public let maxDepth: Int
    public let maxItems: Int

    public init(root: URL = URL(fileURLWithPath: NSHomeDirectory()), maxDepth: Int = 8, maxItems: Int = 200_000) {
        self.root = root.standardizedFileURL
        self.maxDepth = maxDepth
        self.maxItems = maxItems
    }

    static let keys: [URLResourceKey] = [.isDirectoryKey, .isPackageKey]

    /// Everything under the home folder: the union of every branch.
    public func items() -> [Item] {
        branches().flatMap(items(in:))
    }

    /// The home folder's top-level entries (Desktop, Documents, …), minus ~/Library, dot-files and
    /// skipped folders. Each can be scanned on its own, so one slow or permission-blocked folder
    /// never holds back the others.
    public func branches() -> [URL] {
        let children = (try? FileManager.default.contentsOfDirectory(
            at: root, includingPropertiesForKeys: Self.keys, options: [.skipsHiddenFiles])) ?? []
        return children
            .filter { $0.lastPathComponent != "Library" && !Self.skippedFolders.contains($0.lastPathComponent) }
            .sorted { $0.path < $1.path }
    }

    /// One branch: the entry itself and, for a folder, everything below it.
    public func items(in branch: URL) -> [Item] {
        var out: [Item] = []
        guard let first = item(branch) else { return [] }
        out.append(first)
        guard first.kind == .folder,
              let walker = FileManager.default.enumerator(
                  at: branch, includingPropertiesForKeys: Self.keys,
                  options: [.skipsHiddenFiles, .skipsPackageDescendants])
        else { return out }
        while let url = walker.nextObject() as? URL, out.count < maxItems {
            if walker.level + 1 > maxDepth || Self.skippedFolders.contains(url.lastPathComponent) {
                walker.skipDescendants()
                continue
            }
            if let found = item(url) { out.append(found) }
        }
        return out
    }

    private func item(_ url: URL) -> Item? {
        if url.pathExtension == "app" { return nil }
        let path = url.standardizedFileURL.path
        let values = try? url.resourceValues(forKeys: Set(Self.keys))
        let isFolder = (values?.isDirectory ?? false) && !(values?.isPackage ?? false)
        let title = isFolder ? FileManager.default.displayName(atPath: path) : url.lastPathComponent
        return Item(id: path, title: title, kind: isFolder ? .folder : .file, path: path)
    }
}

/// The folder a file or folder row shows beneath its name; nil for apps and settings panes.
public func parentFolder(of item: Item) -> String? {
    switch item.kind {
    case .file, .folder: (item.path as NSString).deletingLastPathComponent
    case .app, .settingsPane: nil
    }
}
