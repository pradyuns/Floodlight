/// How strongly an item matches, weakest first.
public enum MatchClass: Int, Sendable, Comparable {
    case typo, keyword, midWord, initials, wordPrefix, titlePrefix, exactFull

    public static func < (a: MatchClass, b: MatchClass) -> Bool { a.rawValue < b.rawValue }
}

public struct Candidate: Sendable, Hashable {
    public let item: Item
    public let matchClass: MatchClass
    /// Within a class, lower is a closer match (edit distance for typos, word position for word prefixes).
    public let penalty: Int
}

let minMidWordLength = 3
let minTypoLength = 4

func typoBudget(_ length: Int) -> Int { length >= 8 ? 2 : 1 }

/// Decides whether each item matches and how strongly. Never orders: results keep index order.
public func match(_ query: String, in index: IndexSnapshot) -> [Candidate] {
    let q = Normalized(query)
    guard !q.compact.isEmpty else { return [] }
    return index.entries.compactMap { entry in
        classify(q, entry).map { Candidate(item: entry.item, matchClass: $0.0, penalty: $0.1) }
    }
}

func classify(_ q: Normalized, _ entry: Entry) -> (MatchClass, Int)? {
    let t = entry.title
    let qc = q.compact
    if t.compact == qc { return (.exactFull, 0) }
    if t.compact.hasPrefix(qc) || wordsMatch(q.words, t.words, from: 0) { return (.titlePrefix, 0) }
    for i in t.words.indices.dropFirst() where t.words[i...].joined().hasPrefix(qc) || wordsMatch(q.words, t.words, from: i) {
        return (.wordPrefix, i)
    }
    if qc.count >= 2, t.words.count > 1, t.initials.hasPrefix(qc) { return (.initials, t.initials.count - qc.count) }
    if qc.count >= minMidWordLength, t.compact.contains(qc) { return (.midWord, 0) }
    if entry.keywords.contains(where: { $0.compact.hasPrefix(qc) || $0.words.contains { $0.hasPrefix(qc) } }) {
        return (.keyword, 0)
    }
    if let d = typoDistance(qc, t) { return (.typo, d) }
    return nil
}

/// Each query word is a prefix of consecutive title words starting at `start`.
func wordsMatch(_ q: [String], _ t: [String], from start: Int) -> Bool {
    guard q.count > 1, start + q.count <= t.count else { return false }
    return zip(q, t[start...]).allSatisfy { $1.hasPrefix($0) }
}

/// Smallest edit distance (with transpositions) between the query and a same-length-ish prefix of the
/// title, starting at the title or at any word. Nil above the budget.
func typoDistance(_ qc: String, _ t: Normalized) -> Int? {
    guard qc.count >= minTypoLength else { return nil }
    let q = Array(qc)
    let k = typoBudget(q.count)
    var best: Int?
    for i in t.words.indices {
        let tail = Array(t.words[i...].joined())
        let lo = max(1, q.count - k), hi = min(tail.count, q.count + k)
        guard lo <= hi else { continue }
        for len in lo...hi {
            let d = osaDistance(q, Array(tail[0..<len]))
            if d <= k, d < (best ?? .max) { best = d }
        }
    }
    return best
}

/// Optimal string alignment distance: insertions, deletions, substitutions and adjacent transpositions.
func osaDistance(_ a: [Character], _ b: [Character]) -> Int {
    if a.isEmpty { return b.count }
    if b.isEmpty { return a.count }
    var d = Array(repeating: Array(repeating: 0, count: b.count + 1), count: a.count + 1)
    for i in 0...a.count { d[i][0] = i }
    for j in 0...b.count { d[0][j] = j }
    for i in 1...a.count {
        for j in 1...b.count {
            let cost = a[i - 1] == b[j - 1] ? 0 : 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
            if i > 1, j > 1, a[i - 1] == b[j - 2], a[i - 2] == b[j - 1] {
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
            }
        }
    }
    return d[a.count][b.count]
}
