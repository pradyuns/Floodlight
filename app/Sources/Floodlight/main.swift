import AppKit
import Carbon.HIToolbox
import FloodlightCore

/// Keeps a borderless panel able to take typing without activating the app, like Spotlight.
final class SearchPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
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

@MainActor
final class SearchController: NSObject, NSTextFieldDelegate, NSTableViewDataSource, NSTableViewDelegate,
    NSWindowDelegate {
    static let width: CGFloat = 640
    static let fieldHeight: CGFloat = 56
    static let rowHeight: CGFloat = 40
    static let maxVisibleRows = 8

    let panel: SearchPanel
    let field = NSTextField()
    let table = NSTableView()
    let scroll = NSScrollView()
    let divider = NSBox()
    var index = IndexSnapshot([Item]())
    var appItems: [Item] = []
    var fileItems: [Item] = []
    var filesScannedAt: Date?
    var results: [Item] = []
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
        panel.setAccessibilityTitle("Floodlight")

        let background = NSVisualEffectView()
        background.material = .popover
        background.blendingMode = .behindWindow
        background.state = .active
        background.wantsLayer = true
        background.layer?.cornerRadius = 14
        background.layer?.masksToBounds = true
        panel.contentView = background

        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.font = .systemFont(ofSize: 24, weight: .light)
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

        for view in [field, divider, scroll] as [NSView] { background.addSubview(view) }
        layout()
    }

    func layout() {
        let rows = min(results.count, Self.maxVisibleRows)
        let listHeight = rows == 0 ? 0 : CGFloat(rows) * Self.rowHeight + 12
        let height = Self.fieldHeight + listHeight
        let screen = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let top = screen.maxY - screen.height * 0.22
        panel.setFrame(NSRect(x: screen.midX - Self.width / 2, y: top - height, width: Self.width, height: height),
                       display: true)
        field.frame = NSRect(x: 18, y: height - Self.fieldHeight + 12, width: Self.width - 36, height: 32)
        divider.frame = NSRect(x: 0, y: listHeight, width: Self.width, height: 1)
        divider.isHidden = rows == 0
        scroll.frame = NSRect(x: 6, y: 6, width: Self.width - 12, height: max(0, listHeight - 12))
        scroll.isHidden = rows == 0
    }

    /// Apps and panes on every open; the home folder walk at most once a minute.
    func refreshIndex() {
        Task.detached(priority: .userInitiated) {
            let apps = AppSource().items() + SettingsSource.items()
            await MainActor.run { self.appItems = apps; self.rebuild() }
        }
        if let last = filesScannedAt, Date().timeIntervalSince(last) < 60 { return }
        filesScannedAt = Date()
        Task.detached(priority: .utility) {
            let files = FileSource().items()
            await MainActor.run { self.fileItems = files; self.rebuild() }
        }
    }

    func rebuild() {
        let items = appItems + fileItems
        Task.detached(priority: .userInitiated) {
            let snapshot = IndexSnapshot(items)
            await MainActor.run {
                self.index = snapshot
                if self.panel.isVisible { self.update() }
            }
        }
    }

    func toggle() {
        panel.isVisible ? hide() : show()
    }

    func show() {
        field.stringValue = ""
        update()
        refreshIndex()
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(field)
    }

    func hide() {
        panel.orderOut(nil)
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

    func update() {
        let query = field.stringValue
        results = query.trimmingCharacters(in: .whitespaces).isEmpty
            ? [] : search(query, in: index, frecency: frecency.scores)
        table.reloadData()
        if !results.isEmpty {
            table.selectRowIndexes([0], byExtendingSelection: false)
            table.scrollRowToVisible(0)
        }
        layout()
    }

    func iconLoaded(_ path: String) {
        let rows = IndexSet(results.indices.filter { results[$0].path == path })
        if !rows.isEmpty { table.reloadData(forRowIndexes: rows, columnIndexes: [0]) }
    }

    func open(row: Int) {
        guard results.indices.contains(row) else { return }
        let item = results[row]
        hide()
        if Launcher.open(item) { frecency.recordLaunch(item.id) }
    }

    @objc func openClicked() { open(row: table.clickedRow) }

    func move(_ delta: Int) {
        guard !results.isEmpty else { return }
        let row = max(0, min(results.count - 1, table.selectedRow + delta))
        table.selectRowIndexes([row], byExtendingSelection: false)
        table.scrollRowToVisible(row)
    }

    // MARK: Field

    func controlTextDidChange(_ obj: Notification) { update() }

    func control(_ control: NSControl, textView: NSTextView, doCommandBy selector: Selector) -> Bool {
        switch selector {
        case #selector(NSResponder.moveDown(_:)): move(1)
        case #selector(NSResponder.moveUp(_:)): move(-1)
        case #selector(NSResponder.insertNewline(_:)): open(row: table.selectedRow)
        case #selector(NSResponder.cancelOperation(_:)): hide()
        default: return false
        }
        return true
    }

    func windowDidResignKey(_ notification: Notification) { hide() }

    // MARK: Table

    func numberOfRows(in tableView: NSTableView) -> Int { results.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let item = results[row]
        let cell = NSTableCellView()
        let icon = NSImageView()
        icon.image = item.kind == .settingsPane
            ? NSImage(systemSymbolName: "gearshape", accessibilityDescription: nil)
            : icons.image(for: item.path) { [weak self] path in self?.iconLoaded(path) }
        icon.imageScaling = .scaleProportionallyUpOrDown
        let title = NSTextField(labelWithString: item.title)
        title.font = .systemFont(ofSize: 15)
        title.lineBreakMode = .byTruncatingTail
        let kind = NSTextField(labelWithString: Self.kindLabel(item.kind))
        kind.font = .systemFont(ofSize: 12)
        kind.textColor = .secondaryLabelColor
        kind.alignment = .right
        let parent = NSTextField(labelWithString: parentFolder(of: item).map { ($0 as NSString).abbreviatingWithTildeInPath } ?? "")
        parent.font = .systemFont(ofSize: 12)
        parent.textColor = .tertiaryLabelColor
        parent.lineBreakMode = .byTruncatingMiddle
        parent.isHidden = parentFolder(of: item) == nil
        icon.setAccessibilityElement(false)
        for view in [icon, title, parent, kind] as [NSView] {
            view.translatesAutoresizingMaskIntoConstraints = false
            cell.addSubview(view)
        }
        cell.textField = title
        NSLayoutConstraint.activate([
            icon.leadingAnchor.constraint(equalTo: cell.leadingAnchor, constant: 10),
            icon.centerYAnchor.constraint(equalTo: cell.centerYAnchor),
            icon.widthAnchor.constraint(equalToConstant: 26),
            icon.heightAnchor.constraint(equalToConstant: 26),
            title.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 10),
            title.centerYAnchor.constraint(equalTo: cell.centerYAnchor),
            parent.leadingAnchor.constraint(equalTo: title.trailingAnchor, constant: 8),
            parent.centerYAnchor.constraint(equalTo: cell.centerYAnchor),
            kind.leadingAnchor.constraint(greaterThanOrEqualTo: parent.trailingAnchor, constant: 8),
            kind.trailingAnchor.constraint(equalTo: cell.trailingAnchor, constant: -12),
            kind.centerYAnchor.constraint(equalTo: cell.centerYAnchor),
        ])
        title.setContentCompressionResistancePriority(.defaultHigh, for: .horizontal)
        parent.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        return cell
    }

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
