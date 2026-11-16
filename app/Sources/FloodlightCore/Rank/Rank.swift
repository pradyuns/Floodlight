/// Strength first, then apps before other kinds, then usage, then shorter and alphabetical names,
/// so ties always break the same way.
func ranksBefore(_ a: Candidate, _ b: Candidate, _ frecency: Frecency) -> Bool {
    if a.matchClass != b.matchClass { return a.matchClass > b.matchClass }
    if a.penalty != b.penalty { return a.penalty < b.penalty }
    if a.item.kind != b.item.kind { return a.item.kind < b.item.kind }
    let fa = frecency[a.item.id] ?? 0, fb = frecency[b.item.id] ?? 0
    if fa != fb { return fa > fb }
    if a.name.count != b.name.count { return a.name.count < b.name.count }
    if a.name != b.name { return a.name < b.name }
    return a.item.id < b.item.id
}

/// Orders matches; never adds or drops one.
public func rank(_ candidates: [Candidate], frecency: Frecency) -> [Item] {
    candidates.sorted { ranksBefore($0, $1, frecency) }.map(\.item)
}

public func search(_ query: String, in index: IndexSnapshot, frecency: Frecency) -> [Item] {
    rank(match(query, in: index), frecency: frecency)
}

/// The first `limit` items of the full ranking. Checks only apps, panes and the files whose words
/// start with the query's first letter, and keeps just the best `limit` while scanning.
public func search(_ query: String, in index: IndexSnapshot, frecency: Frecency, limit: Int) -> [Item] {
    let q = Normalized(query)
    guard let first = q.compact.first, limit > 0 else { return [] }
    var top: [Candidate] = []
    top.reserveCapacity(limit + 1)
    func consider(_ i: Int) {
        let entry = index.entries[i]
        guard let (matchClass, penalty) = classify(q, entry) else { return }
        let c = Candidate(item: entry.item, matchClass: matchClass, penalty: penalty, name: entry.title.compact)
        if top.count == limit, let last = top.last, !ranksBefore(c, last, frecency) { return }
        let at = top.firstIndex { ranksBefore(c, $0, frecency) } ?? top.endIndex
        top.insert(c, at: at)
        if top.count > limit { top.removeLast() }
    }
    index.launchable.forEach(consider)
    index.byWordStart[first]?.forEach(consider)
    return top.map(\.item)
}
