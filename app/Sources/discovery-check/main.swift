import FloodlightCore
import Foundation

// Prints titles of apps found under /System only (identical on every Mac), and timing.
let t0 = Date()
let items = AppSource(roots: [URL(fileURLWithPath: "/System/Applications"),
                              URL(fileURLWithPath: "/System/Library/CoreServices/Applications")]).items()
print("found \(items.count) system apps in \(Int(Date().timeIntervalSince(t0) * 1000)) ms")
let index = IndexSnapshot(items + SettingsSource.items())
for q in ["image playground", "find my", "findmy", "voicememos", "calcualtor", "apps", "time", "wifi", "am", "ca"] {
    print(q, "->", search(q, in: index, frecency: [:]).prefix(3).map(\.title))
}
