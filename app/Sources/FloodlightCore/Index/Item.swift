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
    /// Search-only synonyms ("battery" for the Energy pane): the weakest kind of match.
    public let keywords: [String]
    /// The item's own other names (an app's bundle names, e.g. "Chrome" for Google Chrome): they
    /// match as strongly as the title.
    public let aliases: [String]

    public init(id: String, title: String, kind: ItemKind, path: String, keywords: [String] = [],
                aliases: [String] = []) {
        self.id = id
        self.title = title
        self.kind = kind
        self.path = path
        self.keywords = keywords
        self.aliases = aliases
    }
}

/// Usage score per item id; higher means used more, more recently.
public typealias Frecency = [String: Double]
