import Foundation

/// Folders and files under the home folder. Skips dot-files, ~/Library and package contents;
/// apps are AppSource's job.
public struct FileSource: Sendable {
    public let root: URL
    public let maxDepth: Int
    public let maxItems: Int

    public init(root: URL = URL(fileURLWithPath: NSHomeDirectory()), maxDepth: Int = 8, maxItems: Int = 200_000) {
        self.root = root.standardizedFileURL
        self.maxDepth = maxDepth
        self.maxItems = maxItems
    }

    public func items() -> [Item] {
        let keys: [URLResourceKey] = [.isDirectoryKey, .isPackageKey]
        guard let walker = FileManager.default.enumerator(
            at: root, includingPropertiesForKeys: keys,
            options: [.skipsHiddenFiles, .skipsPackageDescendants])
        else { return [] }
        let library = root.appendingPathComponent("Library").path
        var out: [Item] = []
        while let url = walker.nextObject() as? URL, out.count < maxItems {
            let path = url.standardizedFileURL.path
            if path == library || walker.level > maxDepth {
                walker.skipDescendants()
                continue
            }
            if url.pathExtension == "app" { continue }
            let values = try? url.resourceValues(forKeys: Set(keys))
            let isFolder = (values?.isDirectory ?? false) && !(values?.isPackage ?? false)
            out.append(Item(id: path, title: url.lastPathComponent, kind: isFolder ? .folder : .file, path: path))
        }
        return out
    }
}

/// The folder a file or folder row shows beneath its name; nil for apps and settings panes.
public func parentFolder(of item: Item) -> String? {
    switch item.kind {
    case .file, .folder: (item.path as NSString).deletingLastPathComponent
    case .app, .settingsPane: nil
    }
}
