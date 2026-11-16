import AppKit
import Carbon.HIToolbox
import FloodlightCore

/// Keeps a borderless panel able to take typing without activating the app, like Spotlight.
final class SearchPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    /// The app has no menu bar, which is where Cmd-A/C/V/X/Z normally come from.
    static let editKeys: [String: Selector] = [
        "a": #selector(NSText.selectAll(_:)),
        "c": #selector(NSText.copy(_:)),
        "v": #selector(NSText.paste(_:)),
        "x": #selector(NSText.cut(_:)),
        "z": Selector(("undo:")),
    ]

    /// Drag the panel from anywhere, including the search field (as Spotlight allows): a press
    /// that moves more than a few points drags the window; a plain click still reaches the field.
    override func sendEvent(_ event: NSEvent) {
        guard event.type == .leftMouseDown, event.clickCount == 1 else { return super.sendEvent(event) }
        let start = event.locationInWindow
        while let next = nextEvent(matching: [.leftMouseUp, .leftMouseDragged], until: .distantFuture,
                                   inMode: .eventTracking, dequeue: false) {
            if next.type == .leftMouseUp { break }
            if hypot(next.locationInWindow.x - start.x, next.locationInWindow.y - start.y) > 3 {
                performDrag(with: event)
                return
            }
            _ = nextEvent(matching: .leftMouseDragged)
        }
        super.sendEvent(event)
    }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if flags == .command, let key = event.charactersIgnoringModifiers,
           let action = Self.editKeys[key], NSApp.sendAction(action, to: nil, from: self) {
            return true
        }
        return super.performKeyEquivalent(with: event)
    }
}

/// Usage counts with decay, stored in Application Support. Ranking uses it only within a match class.
@MainActor
final class FrecencyStore {
    private(set) var scores: Frecency = [:]
    private let url: URL

    init() {
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Floodlight")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        url = dir.appendingPathComponent("frecency.json")
        if let data = try? Data(contentsOf: url),
           let saved = try? JSONDecoder().decode(Frecency.self, from: data) {
            scores = saved
        }
    }

    func recordLaunch(_ id: String) {
        for key in scores.keys { scores[key, default: 0] *= 0.95 }
        scores[id, default: 0] += 1
        if let data = try? JSONEncoder().encode(scores) { try? data.write(to: url, options: .atomic) }
    }
}

/// An image handed from a background queue to the main thread; never touched by both at once.
struct LoadedImage: @unchecked Sendable { let image: NSImage }

/// Icons load off the main thread: a slow icon must never freeze the panel (it did in the VM).
@MainActor
final class IconCache {
    static let side: CGFloat = 52
    private var cache: [String: NSImage] = [:]
    private var pending: Set<String> = []
    private let placeholder = NSImage(systemSymbolName: "app", accessibilityDescription: nil) ?? NSImage()

    func image(for path: String, loaded: @escaping @MainActor (String) -> Void) -> NSImage {
        if let hit = cache[path] { return hit }
        if pending.insert(path).inserted {
            let side = Self.side
            DispatchQueue.global(qos: .userInitiated).async {
                let source = NSWorkspace.shared.icon(forFile: path)
                let drawn = NSImage(size: NSSize(width: side, height: side))
                drawn.lockFocus()
                source.draw(in: NSRect(x: 0, y: 0, width: side, height: side))
                drawn.unlockFocus()
                let box = LoadedImage(image: drawn)
                DispatchQueue.main.async {
                    MainActor.assumeIsolated {
                        self.cache[path] = box.image
                        self.pending.remove(path)
                        loaded(path)
                    }
                }
            }
        }
        return placeholder
    }
}

/// Opt-in timing log (`--trace`): query length, counts and milliseconds only, never query text.
/// Times are on the monotonic uptime clock that NSEvent timestamps use. "ui" means the UI update
/// finished in code, not that pixels reached the screen.
@MainActor
enum Trace {
    static let enabled = CommandLine.arguments.contains("--trace")
    static var lines: [String] = []

    static func now() -> TimeInterval { ProcessInfo.processInfo.systemUptime }

    static func ms(_ from: TimeInterval, _ to: TimeInterval) -> String { String(format: "%.1f", (to - from) * 1000) }

    static func log(_ line: String) {
        guard enabled else { return }
        lines.append(line)
        let dir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Floodlight")
        try? (lines.joined(separator: "\n") + "\n").write(to: dir.appendingPathComponent("trace.log"),
                                                             atomically: true, encoding: .utf8)
    }
}

/// One results row, reused across keystrokes. Accessibility texts stay: title, parent folder
/// (files and folders only: hidden, not empty, otherwise), kind label. The probe parses that order.
final class ResultCell: NSTableCellView {
    static let id = NSUserInterfaceItemIdentifier("result")
    let icon = NSImageView()
    let title = NSTextField(labelWithString: "")
    let parent = NSTextField(labelWithString: "")
    let kind = NSTextField(labelWithString: "")

    init() {
        super.init(frame: .zero)
        identifier = Self.id
        icon.imageScaling = .scaleProportionallyUpOrDown
        icon.setAccessibilityElement(false)
        title.font = .systemFont(ofSize: 15)
        title.lineBreakMode = .byTruncatingTail
        parent.font = .systemFont(ofSize: 12)
        parent.textColor = .tertiaryLabelColor
        parent.lineBreakMode = .byTruncatingMiddle
        kind.font = .systemFont(ofSize: 12)
        kind.textColor = .secondaryLabelColor
        kind.alignment = .right
        for view in [icon, title, parent, kind] as [NSView] {
            view.translatesAutoresizingMaskIntoConstraints = false
            addSubview(view)
        }
        textField = title
        NSLayoutConstraint.activate([
            icon.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 12),
            icon.centerYAnchor.constraint(equalTo: centerYAnchor),
            icon.widthAnchor.constraint(equalToConstant: 26),
            icon.heightAnchor.constraint(equalToConstant: 26),
            title.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 10),
            title.centerYAnchor.constraint(equalTo: centerYAnchor),
            parent.leadingAnchor.constraint(equalTo: title.trailingAnchor, constant: 8),
            parent.centerYAnchor.constraint(equalTo: centerYAnchor),
            kind.leadingAnchor.constraint(greaterThanOrEqualTo: parent.trailingAnchor, constant: 8),
            kind.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -14),
            kind.centerYAnchor.constraint(equalTo: centerYAnchor),
        ])
        title.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)
        parent.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) { nil }

    func configure(_ item: Item, image: NSImage?) {
        icon.image = image
        title.stringValue = item.title
        let folder = parentFolder(of: item)
        parent.stringValue = folder.map { ($0 as NSString).abbreviatingWithTildeInPath } ?? ""
        parent.isHidden = folder == nil
        kind.stringValue = SearchController.kindLabel(item.kind)
    }
}

/// A soft, rounded highlight for the selected row, like Spotlight's.
final class RoundedRowView: NSTableRowView {
    override func drawSelection(in dirtyRect: NSRect) {
        guard selectionHighlightStyle != .none else { return }
        NSColor.labelColor.withAlphaComponent(0.12).setFill()
        NSBezierPath(roundedRect: bounds.insetBy(dx: 4, dy: 2), xRadius: 9, yRadius: 9).fill()
    }
}

@MainActor
final class SearchController: NSObject, NSTextFieldDelegate, NSTableViewDataSource, NSTableViewDelegate,
    NSWindowDelegate {
    static let width: CGFloat = 640
    static let fieldHeight: CGFloat = 56
    static let rowHeight: CGFloat = 40
    static let maxVisibleRows = 8
    /// Accessibility exposes every table row; thousands of rows made a single read take seconds.
    static let maxResults = 20

    let panel: SearchPanel
    let field = NSTextField()
    let table = NSTableView()
    let scroll = NSScrollView()
    let divider = NSBox()
    let searchIcon = NSImageView()
    let statusLabel = NSTextField(labelWithString: "")
    /// A message in place of results (e.g. a failed open); cleared by the next keystroke.
    var status: String?
    /// Rows the list is sized for; it grows while typing but never shrinks until the text is cleared,
    /// so the panel doesn't jump.
    var sizedRows = 0
    var isLayingOut = false
    static let positionKey = "panelTopCenter"
    var index = IndexSnapshot([Item]())
    var appItems: [Item] = []
    var fileItems: [Item] = []
    var filesScannedAt: Date?
    var results: [Item] = []
    var searchGeneration = 0
    var indexBuilds = LatestOnly()
    /// The text the shown results belong to.
    var resultsQuery = ""
    let frecency = FrecencyStore()
    let icons = IconCache()

    override init() {
        panel = SearchPanel(contentRect: NSRect(x: 0, y: 0, width: Self.width, height: Self.fieldHeight),
                            styleMask: [.nonactivatingPanel, .fullSizeContentView, .borderless],
                            backing: .buffered, defer: false)
        super.init()
        panel.level = .floating
        panel.isFloatingPanel = true
        panel.hidesOnDeactivate = false
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.delegate = self
        panel.animationBehavior = .none
        panel.isMovableByWindowBackground = true
        panel.setAccessibilityTitle("Floodlight")

        let background = NSVisualEffectView()
        background.material = .popover
        background.blendingMode = .behindWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 18
        background.layer?.masksToBounds = true
        panel.contentView = background

        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.font = .systemFont(ofSize: 22)
        searchIcon.image = NSImage(systemSymbolName: "magnifyingglass", accessibilityDescription: nil)
        searchIcon.symbolConfiguration = .init(pointSize: 18, weight: .regular)
        searchIcon.contentTintColor = .secondaryLabelColor
        searchIcon.setAccessibilityElement(false)
        field.placeholderString = "Floodlight Search"
        field.delegate = self
        field.cell?.usesSingleLineMode = true
        field.cell?.lineBreakMode = .byTruncatingTail
        field.setAccessibilityIdentifier("floodlight.search")

        divider.boxType = .separator

        let column = NSTableColumn(identifier: NSUserInterfaceItemIdentifier("item"))
        table.addTableColumn(column)
        table.headerView = nil
        table.rowHeight = Self.rowHeight
        table.intercellSpacing = .zero
        table.backgroundColor = .clear
        table.style = .plain
        table.selectionHighlightStyle = .regular
        table.dataSource = self
        table.delegate = self
        table.target = self
        table.doubleAction = #selector(openClicked)
        table.refusesFirstResponder = true
        table.setAccessibilityIdentifier("floodlight.results")
        table.setAccessibilityLabel("Results")

        scroll.documentView = table
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.autohidesScrollers = true

        statusLabel.font = .systemFont(ofSize: 14)
        statusLabel.textColor = .secondaryLabelColor
        statusLabel.alignment = .center
        statusLabel.isHidden = true
        for view in [searchIcon, field, divider, scroll, statusLabel] as [NSView] { background.addSubview(view) }
        layout()
    }

    func layout() {
        // Grows while typing, never shrinks until the text is cleared or the panel reopens; a query
        // with no matches keeps the area and says so.
        let current = resultsQuery == field.stringValue
        let message = status ?? (current && results.isEmpty && !field.stringValue.isEmpty ? "No results" : nil)
        sizedRows = field.stringValue.isEmpty && status == nil
            ? 0 : max(sizedRows, min(results.count, Self.maxVisibleRows), message == nil ? 0 : 1)
        statusLabel.stringValue = message ?? ""
        statusLabel.isHidden = message == nil
        let listHeight = sizedRows == 0 ? 0 : CGFloat(sizedRows) * Self.rowHeight + 12
        let height = Self.fieldHeight + listHeight
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        var anchor = NSPoint(x: screen.midX, y: screen.maxY - screen.height * 0.22)
        if let saved = UserDefaults.standard.array(forKey: Self.positionKey) as? [Double], saved.count == 2 {
            let point = NSPoint(x: saved[0], y: saved[1])
            if NSScreen.screens.contains(where: { $0.frame.contains(point) }) { anchor = point }
        }
        let frame = NSRect(x: anchor.x - Self.width / 2, y: anchor.y - height, width: Self.width, height: height)
        if panel.frame != frame {
            isLayingOut = true
            panel.setFrame(frame, display: true)
            isLayingOut = false
        }
        // Center the icon and the text line (the field's own height, not a fixed box) on the bar.
        let barMid = height - Self.fieldHeight / 2
        let textHeight = (field.cell?.cellSize.height ?? 28).rounded(.up)
        searchIcon.frame = NSRect(x: 18, y: (barMid - 12).rounded(), width: 24, height: 24)
        field.frame = NSRect(x: 50, y: (barMid - textHeight / 2).rounded(), width: Self.width - 68, height: textHeight)
        divider.frame = NSRect(x: 0, y: listHeight, width: Self.width, height: 1)
        divider.isHidden = sizedRows == 0
        scroll.frame = NSRect(x: 6, y: 6, width: Self.width - 12, height: max(0, listHeight - 12))
        scroll.isHidden = results.isEmpty
        statusLabel.frame = NSRect(x: 20, y: max(0, listHeight / 2 - 10), width: Self.width - 40, height: 20)
    }

    /// Remember where the user dragged the panel (its top centre), not our own resizes.
    func windowDidMove(_ notification: Notification) {
        guard !isLayingOut else { return }
        UserDefaults.standard.set([Double(panel.frame.midX), Double(panel.frame.maxY)], forKey: Self.positionKey)
    }

    /// Apps and panes on every open; the home folder walk at most once a minute.
    func refreshIndex() {
        Task.detached(priority: .userInitiated) {
            let apps = AppSource().items() + SettingsSource.items()
            await MainActor.run {
                guard apps != self.appItems else { return }
                self.appItems = apps
                self.rebuild()
            }
        }
        if let last = filesScannedAt, Date().timeIntervalSince(last) < 60 { return }
        filesScannedAt = Date()
        let previous = fileItems
        Task.detached(priority: .utility) {
            let files = FileSource().items()
            guard files != previous else { return }
            await MainActor.run {
                self.fileItems = files
                self.rebuild()
            }
        }
    }

    func rebuild() {
        let items = appItems + fileItems
        let build = indexBuilds.begin()
        Task.detached(priority: .userInitiated) {
            let snapshot = IndexSnapshot(items)
            await MainActor.run {
                guard self.indexBuilds.mayPublish(build) else { return }
                self.index = snapshot
                // Never reorder a list the user is looking at; the next keystroke uses the new
                // index. Only fill an empty list (e.g. the first scan finishing).
                if self.panel.isVisible, self.results.isEmpty, !self.field.stringValue.isEmpty { self.update() }
            }
        }
    }

    func toggle() {
        let pressed = NSApp.currentEvent?.timestamp ?? Trace.now()
        if panel.isVisible { hide(); return }
        show()
        Trace.log("open hotkey_to_ui=\(Trace.ms(pressed, Trace.now()))")
    }

    func show() {
        status = nil
        field.stringValue = ""
        sizedRows = 0
        update()
        refreshIndex()
        NSApp.activate()
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(field)
    }

    /// Closing without opening anything hands focus back through the standard app hide, which
    /// makes macOS reactivate the previous app and its key window. (Restoring focus ourselves while
    /// never being the active app left keys going nowhere after typing + Escape: user report.)
    func hide(restoreFocus: Bool = true) {
        panel.orderOut(nil)
        if restoreFocus, NSApp.isActive { NSApp.hide(nil) }
    }

    /// QA aid: show the panel with a query, wait for the index, and save the window as a PNG.
    func render(query: String, to path: String) {
        show()
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
            self.field.stringValue = query
            self.update()
            DispatchQueue.main.asyncAfter(deadline: .now() + 3) {
                guard let view = self.panel.contentView,
                      let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { exit(1) }
                view.cacheDisplay(in: view.bounds, to: rep)
                let ok = (try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))) != nil
                exit(ok ? 0 : 1)
            }
        }
    }

    /// Searches off the main thread so typing never waits; a result for text that has since
    /// changed is dropped.
    func update(keyAt: TimeInterval? = nil) {
        let query = field.stringValue
        let keyTime = keyAt ?? Trace.now()
        searchGeneration += 1
        let generation = searchGeneration
        if query.trimmingCharacters(in: .whitespaces).isEmpty {
            show(results: [], for: query)
            return
        }
        let index = self.index, scores = frecency.scores, limit = Self.maxResults
        let dispatched = Trace.now()
        Task.detached(priority: .userInitiated) {
            let started = ProcessInfo.processInfo.systemUptime
            let found = search(query, in: index, frecency: scores, limit: limit)
            let searched = ProcessInfo.processInfo.systemUptime
            await MainActor.run {
                guard generation == self.searchGeneration else {
                    Trace.log("stale len=\(query.count) search=\(Trace.ms(started, searched))")
                    return
                }
                let applied = Trace.now()
                let (rows, laidOut) = self.show(results: found, for: query)
                Trace.log("key len=\(query.count) results=\(found.count) start=\(Trace.ms(dispatched, started)) "
                    + "search=\(Trace.ms(started, searched)) wait=\(Trace.ms(searched, applied)) "
                    + "rows=\(Trace.ms(applied, rows)) layout=\(Trace.ms(rows, laidOut)) "
                    + "key_to_ui=\(Trace.ms(keyTime, laidOut))")
            }
        }
    }

    /// Returns when the rows and the layout finished updating (for the trace).
    @discardableResult
    func show(results found: [Item], for query: String) -> (TimeInterval, TimeInterval) {
        results = found
        resultsQuery = query
        table.reloadData()
        if !results.isEmpty {
            table.selectRowIndexes([0], byExtendingSelection: false)
            table.scrollRowToVisible(0)
        }
        let rows = Trace.now()
        layout()
        return (rows, Trace.now())
    }

    func iconLoaded(_ path: String) {
        let rows = IndexSet(results.indices.filter { results[$0].path == path })
        if !rows.isEmpty { table.reloadData(forRowIndexes: rows, columnIndexes: [0]) }
    }

    /// Usage is recorded only once macOS confirms the item opened; a failure brings the panel back
    /// with a message (the item may have been removed since indexing).
    func open(row: Int) {
        guard results.indices.contains(row) else { return }
        let item = results[row]
        hide(restoreFocus: false)
        Launcher.open(item) { [weak self] opened in
            guard let self else { return }
            if opened {
                self.frecency.recordLaunch(item.id)
            } else {
                NSSound.beep()
                self.status = "Couldn\u{2019}t open \u{201C}\(item.title)\u{201D}"
                NSApp.activate()
                self.panel.makeKeyAndOrderFront(nil)
                self.panel.makeFirstResponder(self.field)
                self.refreshIndex()
                self.layout()
            }
        }
    }

    /// Enter right after a fast keystroke must not open the previous text's top result.
    func openSelectedForCurrentText() {
        let query = field.stringValue
        if resultsQuery != query {
            searchGeneration += 1
            show(results: search(query, in: index, frecency: frecency.scores, limit: Self.maxResults), for: query)
        }
        open(row: table.selectedRow)
    }

    @objc func openClicked() { open(row: table.clickedRow) }

    func move(_ delta: Int) {
        guard !results.isEmpty else { return }
        let row = max(0, min(results.count - 1, table.selectedRow + delta))
        table.selectRowIndexes([row], byExtendingSelection: false)
        table.scrollRowToVisible(row)
    }

    // MARK: Field

    func controlTextDidChange(_ obj: Notification) {
        status = nil
        update(keyAt: NSApp.currentEvent?.timestamp)
    }

    func control(_ control: NSControl, textView: NSTextView, doCommandBy selector: Selector) -> Bool {
        switch selector {
        case #selector(NSResponder.moveDown(_:)): move(1)
        case #selector(NSResponder.moveUp(_:)): move(-1)
        case #selector(NSResponder.insertNewline(_:)): openSelectedForCurrentText()
        case #selector(NSResponder.cancelOperation(_:)): hide()
        default: return false
        }
        return true
    }

    /// Clicking into another app gives that app focus; clicking nowhere hands focus back.
    func windowDidResignKey(_ notification: Notification) {
        guard panel.isVisible else { return }
        hide(restoreFocus: NSWorkspace.shared.frontmostApplication == NSRunningApplication.current)
    }

    // MARK: Table

    func numberOfRows(in tableView: NSTableView) -> Int { results.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let item = results[row]
        let cell = tableView.makeView(withIdentifier: ResultCell.id, owner: nil) as? ResultCell ?? ResultCell()
        let image = item.kind == .settingsPane
            ? NSImage(systemSymbolName: "gearshape", accessibilityDescription: nil)
            : icons.image(for: item.path) { [weak self] path in self?.iconLoaded(path) }
        cell.configure(item, image: image)
        return cell
    }

    func tableView(_ tableView: NSTableView, rowViewForRow row: Int) -> NSTableRowView? { RoundedRowView() }

    static func kindLabel(_ kind: ItemKind) -> String {
        switch kind {
        case .app: "Application"
        case .settingsPane: "System Settings"
        case .folder: "Folder"
        case .file: "Document"
        }
    }
}

// MARK: Hotkey (Control-Space)

enum Hub {
    @MainActor static var controller: SearchController?
}

func installHotKey() -> Bool {
    var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
    let handler: EventHandlerUPP = { _, _, _ in
        MainActor.assumeIsolated { Hub.controller?.toggle() }
        return noErr
    }
    guard InstallEventHandler(GetApplicationEventTarget(), handler, 1, &spec, nil, nil) == noErr else { return false }
    var ref: EventHotKeyRef?
    let id = EventHotKeyID(signature: OSType(0x464C_4954), id: 1)
    return RegisterEventHotKey(UInt32(kVK_Space), UInt32(controlKey), id, GetApplicationEventTarget(), 0, &ref) == noErr
        && ref != nil
}

let app = NSApplication.shared
app.setActivationPolicy(.accessory)
MainActor.assumeIsolated {
    Hub.controller = SearchController()
    Hub.controller?.refreshIndex()
    guard installHotKey() else {
        FileHandle.standardError.write(Data("Floodlight: couldn't register Control-Space\n".utf8))
        exit(1)
    }
    if CommandLine.arguments.contains("--show") { Hub.controller?.show() }
    if let i = CommandLine.arguments.firstIndex(of: "--icon"), CommandLine.arguments.count > i + 2 {
        let image = NSWorkspace.shared.icon(forFile: CommandLine.arguments[i + 1])
        let ok = image.tiffRepresentation.flatMap { NSBitmapImageRep(data: $0)?.representation(using: .png, properties: [:]) }
            .map { (try? $0.write(to: URL(fileURLWithPath: CommandLine.arguments[i + 2]))) != nil } ?? false
        exit(ok ? 0 : 1)
    }
    if let i = CommandLine.arguments.firstIndex(of: "--render"), CommandLine.arguments.count > i + 2 {
        Hub.controller?.render(query: CommandLine.arguments[i + 1], to: CommandLine.arguments[i + 2])
    }
}
app.run()
