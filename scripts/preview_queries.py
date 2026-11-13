"""Writes a readable Markdown preview of the generated queries for review."""

import json
import sys
from pathlib import Path

from bench.generate import generate_collisions, generate_dev, generate_stepped
from bench.inventory import App

RULES = ["full", "nospace", "initials", "prefix1", "prefix2", "prefix3", "prefix4", "typo"]


def main(inventory_path: str, out_path: str) -> int:
    data = json.loads(Path(inventory_path).read_text())
    inventory = [App(**a) for a in data["apps"]]
    dev = generate_dev(inventory)
    collisions = generate_collisions(inventory)
    stepped = generate_stepped(inventory)
    ambiguous = sum(q.ambiguous for q in dev)
    lines = [
        f"# Query preview ({len(inventory)} apps, macOS {data['macos']['version']})",
        "",
        f"Dev queries: {len(dev)} ({ambiguous} ambiguous, {len(dev) - ambiguous} unambiguous). "
        f"Collision prefixes: {len(collisions)}. Stepped (every prefix): {len(stepped)} apps.",
        "",
        "`*` = ambiguous: more than one app counts as an acceptable answer.",
        "",
        "| App | " + " | ".join(RULES) + " |",
        "|---|" + "---|" * len(RULES),
    ]
    by_app: dict[str, dict[str, str]] = {}
    for q in dev:
        assert q.intended is not None
        by_app.setdefault(q.intended.id, {})[q.rule] = q.text + ("*" if q.ambiguous else "")
    for app in sorted(by_app, key=str.lower):
        cells = [f"`{by_app[app][r]}`" if r in by_app[app] else "-" for r in RULES]
        lines.append(f"| {app} | " + " | ".join(cells) + " |")
    lines += ["", "## Collision prefixes (no single right answer)", "", "| Typed | Acceptable |"]
    lines.append("|---|---|")
    for q in collisions:
        lines.append(f"| `{q.text}` | " + ", ".join(sorted(t.id for t in q.acceptable)) + " |")
    Path(out_path).write_text("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
