/// Orders matches; never adds or drops one. Strength first, then apps before other kinds, then usage,
/// then shorter and alphabetical names so ties always break the same way.
public func rank(_ candidates: [Candidate], frecency: Frecency) -> [Item] {
    candidates.sorted { a, b in
        if a.matchClass != b.matchClass { return a.matchClass > b.matchClass }
        if a.penalty != b.penalty { return a.penalty < b.penalty }
        if a.item.kind != b.item.kind { return a.item.kind < b.item.kind }
        let fa = frecency[a.item.id] ?? 0, fb = frecency[b.item.id] ?? 0
        if fa != fb { return fa > fb }
        let na = Normalized(a.item.title).compact, nb = Normalized(b.item.title).compact
        if na.count != nb.count { return na.count < nb.count }
        if na != nb { return na < nb }
        return a.item.id < b.item.id
    }.map(\.item)
}

public func search(_ query: String, in index: IndexSnapshot, frecency: Frecency) -> [Item] {
    rank(match(query, in: index), frecency: frecency)
}
