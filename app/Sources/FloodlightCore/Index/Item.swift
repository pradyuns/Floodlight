public enum ItemKind: Int, Sendable, Hashable, Comparable {
    case app, settingsPane, folder, file

    public static func < (a: ItemKind, b: ItemKind) -> Bool { a.rawValue < b.rawValue }
}

public struct Item: Sendable, Hashable {
    public let id: String
    public let title: String
    public let kind: ItemKind
    /// Filesystem path for apps, files and folders; a URL string for settings panes.
    public let path: String
    public let keywords: [String]

    public init(id: String, title: String, kind: ItemKind, path: String, keywords: [String] = []) {
        self.id = id
        self.title = title
        self.kind = kind
        self.path = path
        self.keywords = keywords
    }
}

/// Usage score per item id; higher means used more, more recently.
public typealias Frecency = [String: Double]
