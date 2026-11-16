import FloodlightCore
import Foundation

// Offline dev check: Floodlight's matcher over the dev queries and the bench VM's app inventory.
// Usage: dev-eval <inventory.json> <aliases.json> <queries.json>. Prints Intended@1 by rule and the misses.
struct Ref: Decodable { let id: String; let kind: String }
struct Query: Decodable { let id: String; let text: String; let rule: String; let ambiguous: Bool; let intended: Ref }
struct InventoryApp: Decodable { let name: String; let path: String }
struct Inventory: Decodable { let apps: [InventoryApp] }
struct Aliases: Decodable { let aliases: [String: [[String]]] }

let args = CommandLine.arguments
guard args.count == 4 else { print("usage: dev-eval <inventory> <aliases> <queries>"); exit(2) }
func load<T: Decodable>(_ path: String) -> T {
    do { return try JSONDecoder().decode(T.self, from: Data(contentsOf: URL(fileURLWithPath: path))) } catch {
        print("can't read \(path): \(error)"); exit(2)
    }
}
let inventory: Inventory = load(args[1])
let aliases: Aliases = load(args[2])
let queries: [Query] = load(args[3])

let apps = inventory.apps.map {
    Item(id: $0.path, title: $0.name, kind: .app, path: $0.path,
         keywords: (aliases.aliases[$0.name] ?? []).compactMap(\.first))
}
let index = IndexSnapshot(apps + SettingsSource.items())

var byRule: [String: (hit: Int, n: Int)] = [:]
var misses: [String] = []
for q in queries where !q.ambiguous {
    let top = search(q.text, in: index, frecency: [:]).first
    let hit = top.map { Normalized($0.title).compact == Normalized(q.intended.id).compact } ?? false
    byRule[q.rule, default: (0, 0)].n += 1
    if hit { byRule[q.rule, default: (0, 0)].hit += 1 } else {
        let shown = search(q.text, in: index, frecency: [:]).prefix(3).map(\.title).joined(separator: " | ")
        misses.append("\(q.rule)\t\(q.text)\twant \(q.intended.id)\tgot \(shown)")
    }
}
var total = (hit: 0, n: 0)
for (rule, r) in byRule.sorted(by: { $0.key < $1.key }) {
    print(String(format: "%-9@ %5.1f%% (%d/%d)", rule as NSString, 100 * Double(r.hit) / Double(r.n), r.hit, r.n))
    total.hit += r.hit
    total.n += r.n
}
print(String(format: "all unambiguous, query-weighted: %.1f%% (%d/%d)", 100 * Double(total.hit) / Double(total.n), total.hit, total.n))
print("--- misses")
misses.forEach { print($0) }
