import Foundation
import FloodlightCore

// Swift Testing / XCTest don't run under Command Line Tools 26.6, so checks live here.
nonisolated(unsafe) var failures = 0

func check(_ condition: Bool, _ name: String) {
    if condition {
        print("PASS \(name)")
    } else {
        failures += 1
        print("FAIL \(name)")
    }
}

func app(_ title: String, keywords: [String] = []) -> Item {
    Item(id: "/Applications/\(title).app", title: title, kind: .app,
         path: "/Applications/\(title).app", keywords: keywords)
}

func pane(_ title: String, keywords: [String] = []) -> Item {
    Item(id: "pane:\(title)", title: title, kind: .settingsPane, path: "x-apple.systempreferences:\(title)",
         keywords: keywords)
}

let apps = [
    "Activity Monitor", "AirPort Utility", "App Store", "Calculator", "Calendar", "FaceTime", "Grok Bot",
    "iTerm", "Terminal", "Time Machine", "Voice Memos", "VoiceOver Utility", "Phone", "Photo Booth",
    "Photos", "Safari", "Notes", "Mail", "Migration Assistant", "Image Playground", "Apps", "Books",
    "Contacts", "\u{200E}WhatsApp", "Preview", "Rectangle",
].map { app($0) } + [app("Phone Companion", keywords: ["voicemail"]), app("TV", keywords: ["apple tv", "video"])]
let panes = [pane("Wi\u{2011}Fi", keywords: ["wifi", "wireless"]), pane("Bluetooth"), pane("Displays")]
let index = IndexSnapshot(apps + panes)

func top(_ q: String, _ frecency: Frecency = [:]) -> String? { search(q, in: index, frecency: frecency).first?.title }

// Names
check(top("whatsapp") == "\u{200E}WhatsApp", "invisible marks in a title don't block a match")
check(top("grokbot") == "Grok Bot", "no-space form finds a two-word name")
check(top("voicememos") == "Voice Memos", "no-space form of Voice Memos")
check(top("am") == "Activity Monitor", "initials find Activity Monitor")
check(search("am", in: IndexSnapshot([app("Audio MIDI Setup"), app("Activity Monitor")]), frecency: [:]).first?.title == "Activity Monitor", "full initials beat partial initials")
check(top("calculator") == "Calculator", "exact name is first")
check(top("Calculator") == "Calculator", "case doesn't matter")
check(top("wifi") == "Wi\u{2011}Fi", "wifi finds the Wi-Fi pane")
check(top("image playground") == "Image Playground", "Image Playground is listed")
check(top("apps") == "Apps", "apps finds the Apps app before App Store")

// Typos
check(top("calcualtor") == "Calculator", "transposition typo finds Calculator")
check(top("safri") == "Safari", "deletion typo finds Safari")
check(top("termnal") == "Terminal", "typo finds Terminal")
check(top("calcl") == "Calculator", "typo while still typing a prefix")
check(search("xq", in: index, frecency: [:]).isEmpty, "two letters with no match give no fuzzy results")
check(search("zzzzzz", in: index, frecency: [:]).isEmpty, "nonsense finds nothing")

// Strength order
check(top("time") == "Time Machine", "word-start beats mid-word (Time Machine over FaceTime)")
check(top("term") == "Terminal", "word-start beats mid-word (Terminal over iTerm)")
check(top("voic") == "Voice Memos", "a name match beats a keyword match")
check(top("video") == "TV", "keywords still match when nothing else does")
check(search("time", in: index, frecency: [:]).contains { $0.title == "FaceTime" }, "mid-word matches are still listed")

// Invariant: a correct name never gets worse because of typo tolerance.
for item in apps {
    let q = item.title
    check(search(q, in: index, frecency: [:]).first == item, "exact name \(q) is #1")
}

// Invariant: exact full name is #1 regardless of frecency.
let notesID = apps.first { $0.title == "Notes" }!.id
let mailID = apps.first { $0.title == "Mail" }!.id
check(top("notes", [mailID: 1000]) == "Notes", "frecency can't beat an exact name")

// Frecency breaks ties within a class.
check(top("ca", [notesID: 0, apps.first { $0.title == "Calendar" }!.id: 5]) == "Calendar", "frecency orders equal matches")
check(top("ca") == "Calendar" || top("ca") == "Calculator", "ca gives Calendar or Calculator")

// App before settings pane only among equally strong matches.
let both = IndexSnapshot([app("Bluetooth File Exchange"), pane("Bluetooth")])
check(search("bluetooth", in: both, frecency: [:]).first?.kind == .settingsPane, "exact pane beats an app prefix")
let tied = IndexSnapshot([pane("Displays"), app("Displays")])
check(search("displays", in: tied, frecency: [:]).first?.kind == .app, "app first among equal matches")

// Determinism
check(search("c", in: index, frecency: [:]) == search("c", in: index, frecency: [:]), "same input, same output")
let shuffled = IndexSnapshot((apps + panes).reversed())
check(search("c", in: index, frecency: [:]) == search("c", in: shuffled, frecency: [:]), "input order doesn't change results")

// A limited search returns exactly the top of the full ranking.
for q in ["c", "ca", "a", "time", "voic", "s", "doc"] {
    for k in [1, 3, 20] {
        check(search(q, in: index, frecency: [:], limit: k) == Array(search(q, in: index, frecency: [:]).prefix(k)),
              "limit \(k) matches the full ranking for \(q)")
    }
}

// Component boundaries
let candidates = match("ca", in: index)
let ranked = rank(candidates, frecency: [:])
check(Set(ranked) == Set(candidates.map(\.item)) && ranked.count == candidates.count, "ranking keeps exactly the matched items")
check(match("cal", in: index).map(\.item) == match("cal", in: index).map(\.item), "matching is stable")

// Diagnostics
let calc = apps.first { $0.title == "Calculator" }!
check(explain("calculator", target: calc.id, in: index, frecency: [:]).firstFailure == nil, "explain: found at #1")
check(explain("zzzz", target: calc.id, in: index, frecency: [:]).firstFailure == .notMatched, "explain: not matched")
check(explain("x", target: "missing", in: index, frecency: [:]).firstFailure == .notIndexed, "explain: not indexed")
check(explain("ca", target: calc.id, in: index, frecency: [:]).firstFailure == .rankedLow
      || top("ca") == "Calculator", "explain: ranked low")

// Discovery: apps
let root = FileManager.default.temporaryDirectory.appendingPathComponent("floodlight-selftest-\(ProcessInfo.processInfo.processIdentifier)")
func makeApp(_ rel: String, bundleName: String? = nil) {
    let contents = root.appendingPathComponent(rel).appendingPathComponent("Contents")
    try? FileManager.default.createDirectory(at: contents, withIntermediateDirectories: true)
    var info: [String: Any] = ["CFBundleIdentifier": "test.\(rel.count)"]
    if let bundleName { info["CFBundleName"] = bundleName }
    (info as NSDictionary).write(to: contents.appendingPathComponent("Info.plist"), atomically: true)
}
makeApp("Foo.app", bundleName: "FooAlias")
makeApp("Vendor/Bar.app")
makeApp("Foo.app/Contents/Helpers/Inner.app")
makeApp("../elsewhere/Linked.app")
try? FileManager.default.createSymbolicLink(atPath: root.appendingPathComponent("Linked.app").path,
                                           withDestinationPath: "../elsewhere/Linked.app")
_ = lchflags(root.appendingPathComponent("Linked.app").path, UInt32(UF_HIDDEN))
makeApp(".Dot.app")
let found = AppSource(roots: [root]).items()
check(Set(found.map(\.title)) == ["Foo", "Bar", "Linked"], "apps found in nested folders and hidden-flagged symlinks (like Safari), not inside apps or dot-files")
check(found.allSatisfy { $0.kind == .app }, "discovered apps are apps")
check(search("fooalias", in: IndexSnapshot(found), frecency: [:]).first?.title == "Foo", "bundle name works as an alias")
check(AppSource(roots: [root.appendingPathComponent("missing")]).items().isEmpty, "missing root finds nothing")
try? FileManager.default.removeItem(at: root)

// Discovery: folders and files
let home = FileManager.default.temporaryDirectory.appendingPathComponent("floodlight-home-\(ProcessInfo.processInfo.processIdentifier)")
for dir in ["Code/web/node_modules/calcpkg", "Code/py/venv/lib", "Code/py/__pycache__", "Movies/Media.localized", "Documents/Vocals", "Documents/abc-101/inner", "Documents/jms-166", ".hidden/secretdir", "Library/Caches/cachedir"] {
    try? FileManager.default.createDirectory(at: home.appendingPathComponent(dir), withIntermediateDirectories: true)
}
FileManager.default.createFile(atPath: home.appendingPathComponent("Documents/jms-166/digit.txt").path, contents: Data())
let fsItems = FileSource(root: home).items()
let fsTitles = Set(fsItems.map(\.title))
check(fsTitles.isSuperset(of: ["abc-101", "inner", "jms-166", "digit.txt", "Documents"]), "folders and files under home are found")
check(fsTitles.isDisjoint(with: ["secretdir", "cachedir", ".hidden", "Library"]), "dot-folders and Library are skipped")
check(fsTitles.isDisjoint(with: ["node_modules", "calcpkg", "venv", "lib", "__pycache__"]) && fsTitles.contains("web"),
      "dependency and cache folders are skipped, their parents kept")
check(fsItems.first { $0.title == "abc-101" }?.kind == .folder && fsItems.first { $0.title == "digit.txt" }?.kind == .file, "kinds are folder and file")
let fsIndex = IndexSnapshot(fsItems + [app("Digital Color Meter")])
check(fsTitles.contains("Media") && !fsTitles.contains("Media.localized"), "folders show their display name")
check(search("cal", in: IndexSnapshot(fsItems), frecency: [:]).isEmpty, "no mid-word matches for folders and files")
check(search("abc101", in: fsIndex, frecency: [:]).first?.title == "abc-101", "folder found without its punctuation")
check(search("digit", in: fsIndex, frecency: [:]).first?.title == "digit.txt", "exact file name beats an app prefix")
check(search("digit.txt", in: fsIndex, frecency: [:]).first?.title == "digit.txt", "full file name with extension finds the file")
check(search("digit.t", in: fsIndex, frecency: [:]).first?.title == "digit.txt", "typing into the extension keeps the file")
check(search("digi", in: fsIndex, frecency: [:]).first?.title == "Digital Color Meter", "app first among equal prefixes")
check(parentFolder(of: fsItems.first { $0.title == "abc-101" }!) == home.appendingPathComponent("Documents").path, "rows know the parent folder")
try? FileManager.default.removeItem(at: home)

// Discovery: settings
let settings = SettingsSource.items()
check(settings.count >= 25 && settings.allSatisfy { $0.kind == .settingsPane && $0.path.hasPrefix("x-apple.systempreferences:") }, "settings panes have open URLs")
check(search("wifi", in: IndexSnapshot(settings), frecency: [:]).first?.title == "Wi\u{2011}Fi", "real pane list: wifi")
check(search("battery", in: IndexSnapshot(settings), frecency: [:]).first?.title == "Energy", "battery finds the Energy pane")

// Launch targets
check(launchTarget(for: app("Calculator")) == .application(URL(fileURLWithPath: "/Applications/Calculator.app")), "apps open as applications")
check(launchTarget(for: settings[0]) == .url(URL(string: "x-apple.systempreferences:com.apple.wifi-settings-extension")!), "panes open by URL")
check(launchTarget(for: Item(id: "bad", title: "Bad", kind: .settingsPane, path: "")) == nil, "a pane with no URL can't be opened")

if failures > 0 {
    print("\(failures) FAILED")
    exit(1)
}
print("ALL PASSED")
