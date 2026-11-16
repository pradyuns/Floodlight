import Foundation

/// Finds .app bundles on disk, including inside vendor folders, but never inside another app.
public struct AppSource: Sendable {
    public static let standardRoots: [URL] = [
        "/Applications", "/System/Applications", "/System/Library/CoreServices/Applications",
        NSHomeDirectory() + "/Applications",
    ].map { URL(fileURLWithPath: $0) }

    public let roots: [URL]
    public let maxDepth: Int

    public init(roots: [URL] = AppSource.standardRoots, maxDepth: Int = 4) {
        self.roots = roots
        self.maxDepth = maxDepth
    }

    public func items() -> [Item] {
        var seen = Set<String>()
        return roots.flatMap { bundles(in: $0, depth: 0) }
            .filter { seen.insert($0.resolvingSymlinksInPath().path).inserted }
            .map(Self.item)
    }

    private func bundles(in dir: URL, depth: Int) -> [URL] {
        guard depth <= maxDepth,
              let children = try? FileManager.default.contentsOfDirectory(
                  at: dir, includingPropertiesForKeys: [.isDirectoryKey], options: [])
        else { return [] }
        // Not .skipsHiddenFiles: macOS flags the /Applications/Safari.app symlink hidden.
        return children.filter { !$0.lastPathComponent.hasPrefix(".") }.sorted { $0.path < $1.path }.flatMap { url -> [URL] in
            if url.pathExtension == "app" { return [url] }
            let isDir = (try? url.resourceValues(forKeys: [.isDirectoryKey]).isDirectory) ?? false
            return isDir ? bundles(in: url, depth: depth + 1) : []
        }
    }

    static func item(_ url: URL) -> Item {
        let fileName = url.deletingPathExtension().lastPathComponent
        var title = FileManager.default.displayName(atPath: url.path)
        if title.hasSuffix(".app") { title = String(title.dropLast(4)) }
        let info = Bundle(url: url)?.localizedInfoDictionary ?? [:]
        let base = Bundle(url: url)?.infoDictionary ?? [:]
        let names = [fileName, info["CFBundleDisplayName"], info["CFBundleName"],
                     base["CFBundleDisplayName"], base["CFBundleName"]].compactMap { $0 as? String }
        var keywords: [String] = []
        for n in names where n != title && !keywords.contains(n) { keywords.append(n) }
        return Item(id: url.path, title: title, kind: .app, path: url.path, keywords: keywords)
    }
}
