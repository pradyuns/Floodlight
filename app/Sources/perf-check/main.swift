import FloodlightCore
import Foundation

// Search timing on this Mac's real index. Prints counts and timings only, never names or paths.
// Each query: median and worst of 5 runs of the top-20 search used by the app.
func ms(_ a: UInt64, _ b: UInt64) -> Double { Double(b - a) / 1_000_000 }
func now() -> UInt64 { DispatchTime.now().uptimeNanoseconds }

var t = now()
let apps = AppSource().items() + SettingsSource.items()
print(String(format: "apps+panes: %d in %.0f ms", apps.count, ms(t, now())))
t = now()
let files = FileSource().items()
print(String(format: "files+folders: %d in %.0f ms", files.count, ms(t, now())))
t = now()
let index = IndexSnapshot(apps + files)
print(String(format: "index build: %.0f ms", ms(t, now())))

let groups: [(String, [String])] = [
    ("1 letter", ["a", "c", "s", "p"]),
    ("2 letters", ["ca", "ma", "pr", "te"]),
    ("word prefix", ["cal", "term", "voic", "doc", "not"]),
    ("initials", ["am", "fm", "ss"]),
    ("alias", ["code", "chrome"]),
    ("typo", ["calcualtor", "safri", "termnal"]),
    ("full name", ["calculator", "system settings", "wifi"]),
    ("file-ish", ["readme", "png", "index", "screenshot"]),
]
var all: [Double] = []
for (label, queries) in groups {
    var medians: [Double] = [], worsts: [Double] = []
    for q in queries {
        var runs: [Double] = []
        for _ in 0..<5 {
            let s = now()
            _ = search(q, in: index, frecency: [:], limit: 20)
            runs.append(ms(s, now()))
        }
        runs.sort()
        medians.append(runs[2])
        worsts.append(runs[4])
        all += runs
    }
    print(String(format: "%-12@ median %5.1f ms   worst %5.1f ms", label as NSString,
                 medians.sorted()[medians.count / 2], worsts.max() ?? 0))
}
all.sort()
print(String(format: "ALL searches: median %.1f ms, p95 %.1f ms, worst %.1f ms (n=%d)",
             all[all.count / 2], all[Int(Double(all.count) * 0.95)], all.last ?? 0, all.count))
