public enum TypingMode: String, Codable, Sendable {
    case completed, continuous, stepped

    public var keyIntervalMs: Int { self == .stepped ? 1000 : 80 }
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

public struct SnapshotDTO: Codable, Sendable {
    public let tMs: Int
    public let rows: [RowDTO]
    public let fieldText: String
    /// The launcher's own label for what Enter would do, when it shows one (Raycast's action bar).
    public let primaryAction: String?

    public init(tMs: Int, rows: [RowDTO], fieldText: String, primaryAction: String? = nil) {
        self.tMs = tMs
        self.rows = rows
        self.fieldText = fieldText
        self.primaryAction = primaryAction
    }
}

public struct SampleDTO: Codable, Sendable {
    public var finalKeyPostMs: Int
    public var fieldShowsMs: Int?
    public var snapshots: [SnapshotDTO]
    public var error: String?

    public init(finalKeyPostMs: Int, fieldShowsMs: Int?, snapshots: [SnapshotDTO], error: String?) {
        self.finalKeyPostMs = finalKeyPostMs
        self.fieldShowsMs = fieldShowsMs
        self.snapshots = snapshots
        self.error = error
    }
}
