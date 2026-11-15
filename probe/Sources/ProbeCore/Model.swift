public enum TypingMode: String, Codable, Sendable {
    case completed, continuous, stepped

    public var keyIntervalMs: Int { self == .stepped ? 1000 : 80 }
}

/// What one read of the search field found. An empty field is `.text("")`; a read that failed is
/// `.unreadable`, which says nothing about what the field showed.
public enum FieldRead: Equatable, Sendable {
    case text(String)
    case unreadable(String)
}

public struct RowDTO: Codable, Equatable, Sendable {
    public let title: String
    public let kind: String
    public let source: String
    public let folder: String?
    public let paneId: String?
    public let selected: Bool?
    public let category: String?

    public init(title: String, kind: String, source: String, folder: String?, paneId: String?,
                selected: Bool?, category: String? = nil) {
        self.title = title
        self.kind = kind
        self.source = source
        self.folder = folder
        self.paneId = paneId
        self.selected = selected
        self.category = category
    }
}

/// Times are milliseconds since the first key was due.
public struct SnapshotDTO: Codable, Sendable {
    /// When the accessibility read began: the screen content is no older than this.
    public let readStartMs: Int
    /// When the read finished: the rows were not known before this.
    public let readEndMs: Int
    public let rows: [RowDTO]
    public let fieldText: String
    /// The launcher's own label for what Enter would do, when it shows one (Raycast's action bar).
    public let primaryAction: String?
    /// The field showed text that isn't what was typed so far (e.g. a lost first key). Kept as
    /// evidence; never scored.
    public let fieldMismatch: Bool
    /// Why this read saw nothing ("field:…" or "rows:…"); nil when the read succeeded. An
    /// unreadable snapshot is an observation failure, never an empty result.
    public let unreadable: String?

    public init(readStartMs: Int, readEndMs: Int, rows: [RowDTO], fieldText: String,
                primaryAction: String? = nil, fieldMismatch: Bool = false,
                unreadable: String? = nil) {
        self.readStartMs = readStartMs
        self.readEndMs = readEndMs
        self.rows = rows
        self.fieldText = fieldText
        self.primaryAction = primaryAction
        self.fieldMismatch = fieldMismatch
        self.unreadable = unreadable
    }
}

public struct KeyPostDTO: Codable, Equatable, Sendable {
    public let plannedMs: Int
    public let actualMs: Int

    public init(plannedMs: Int, actualMs: Int) {
        self.plannedMs = plannedMs
        self.actualMs = actualMs
    }
}

public struct SampleDTO: Sendable {
    public var keyPosts: [KeyPostDTO]
    public var fieldShowsMs: Int?
    public var snapshots: [SnapshotDTO]
    public var error: String?

    /// When the final key was actually posted, not when it was due.
    public var finalKeyPostMs: Int { keyPosts.last?.actualMs ?? 0 }
    public var maxKeyLatenessMs: Int { keyPosts.map { $0.actualMs - $0.plannedMs }.max() ?? 0 }

    public init(keyPosts: [KeyPostDTO], fieldShowsMs: Int?, snapshots: [SnapshotDTO], error: String?) {
        self.keyPosts = keyPosts
        self.fieldShowsMs = fieldShowsMs
        self.snapshots = snapshots
        self.error = error
    }
}
