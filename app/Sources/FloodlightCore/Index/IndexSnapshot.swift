import Foundation

/// Lowercased, accent-folded alphanumeric words. Punctuation, symbols and invisible marks split words.
public struct Normalized: Sendable, Hashable {
    public let words: [String]
    public let compact: String

    public init(_ text: String) {
        let folded = text.folding(options: [.caseInsensitive, .diacriticInsensitive], locale: nil)
        var words: [String] = []
        var current = ""
        for ch in folded {
            if ch.isLetter || ch.isNumber {
                current.append(ch)
            } else if !current.isEmpty {
                words.append(current)
                current = ""
            }
        }
        if !current.isEmpty { words.append(current) }
        self.words = words
        compact = words.joined()
    }

    var initials: String { String(words.compactMap(\.first)) }
}

struct Entry: Sendable {
    let item: Item
    let title: Normalized
    let keywords: [Normalized]
}

/// Immutable, normalized store of everything discovered. Lookup only; it never ranks.
public struct IndexSnapshot: Sendable {
    let entries: [Entry]

    public init<S: Sequence>(_ items: S) where S.Element == Item {
        var seen = Set<String>()
        entries = items
            .filter { seen.insert($0.id).inserted }
            .sorted { $0.id < $1.id }
            .map { Entry(item: $0, title: Normalized($0.title), keywords: $0.keywords.map(Normalized.init)) }
    }

    public var items: [Item] { entries.map(\.item) }

    public func contains(id: String) -> Bool { entries.contains { $0.item.id == id } }
}
