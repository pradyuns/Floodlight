import FloodlightCore
import Foundation

// Prints counts and timings only (never names): how long indexing and each keystroke's search take.
func ms(_ t: Date) -> Int { Int(Date().timeIntervalSince(t) * 1000) }
var t = Date()
let apps = AppSource().items() + SettingsSource.items()
print("apps+panes: \(apps.count) in \(ms(t)) ms")
t = Date()
let files = FileSource().items()
print("files+folders: \(files.count) in \(ms(t)) ms")
t = Date()
let index = IndexSnapshot(apps + files)
print("index build: \(ms(t)) ms")
for q in ["s", "sa", "saf", "safa", "safar", "safari", "c", "ca", "cal", "calc", "calcualtor"] {
    t = Date()
    let r = search(q, in: index, frecency: [:], limit: 20)
    print("search \(q.count) chars: \(ms(t)) ms, \(r.count) matches")
}
