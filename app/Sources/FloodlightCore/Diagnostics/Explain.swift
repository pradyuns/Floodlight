public enum Stage: Sendable, Equatable {
    case notIndexed, notMatched, rankedLow
}

public struct Trace: Sendable, Equatable {
    public let indexed: Bool
    public let matchClass: MatchClass?
    /// Zero-based position in the ranked results.
    public let position: Int?

    public var firstFailure: Stage? {
        if !indexed { return .notIndexed }
        guard matchClass != nil, let position else { return .notMatched }
        return position == 0 ? nil : .rankedLow
    }
}

/// What each stage did for one target item.
public func explain(_ query: String, target id: String, in index: IndexSnapshot, frecency: Frecency) -> Trace {
    let candidates = match(query, in: index)
    return Trace(indexed: index.contains(id: id),
                 matchClass: candidates.first { $0.item.id == id }?.matchClass,
                 position: rank(candidates, frecency: frecency).firstIndex { $0.id == id })
}
