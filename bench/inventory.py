"""Reference app inventory, built from .app bundles on the VM filesystem (never from mdfind)."""

import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Literal

from bench.vm import VM

AppKind = Literal["builtin", "third_party", "tool_under_test", "planted"]

APP_DIRS = [
    "/Applications",
    "/Applications/Utilities",
    "/System/Applications",
    "/System/Applications/Utilities",
]

LIST_CMD = (
    "for d in " + " ".join(APP_DIRS) + "; do "
    'find "$d" -maxdepth 1 -name "*.app" 2>/dev/null; done | while IFS= read -r p; do '
    'r=$(cd -P "$p" 2>/dev/null && pwd); '
    "n=$(osascript -l JavaScript -e \"ObjC.import('Foundation'); "
    "\\$.NSFileManager.defaultManager.displayNameAtPath('$p').js\" 2>/dev/null); "
    '[ -n "$n" ] || n=$(basename "$p" .app); n="${n%.app}"; '
    "b=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' \"$p/Contents/Info.plist\" "
    "2>/dev/null); "
    'printf \'%s\\t%s\\t%s\\t%s\\n\' "$p" "$r" "$n" "$b"; done'
)


@dataclass(frozen=True)
class App:
    name: str
    path: str
    real_path: str
    bundle_id: str
    kind: AppKind


def _has_format_char(s: str) -> bool:
    return any(unicodedata.category(c) == "Cf" for c in s)


def parse_inventory(
    listing: str,
    tools_under_test: set[str],
    third_party: set[str] | None = None,
    planted: set[str] | None = None,
) -> tuple[list[App], dict[str, str]]:
    third_party = third_party or set()
    planted = planted or set()
    rows = [line.split("\t") for line in listing.splitlines() if line.strip()]
    counts = Counter(row[2] for row in rows)
    apps: list[App] = []
    excluded: dict[str, str] = {}
    for path, real_path, name, bundle_id in rows:
        if counts[name] > 1:
            excluded[name] = "duplicate name"
            continue
        if _has_format_char(name):
            excluded[name] = "format character in name"
            continue
        kind: AppKind = "builtin"
        if bundle_id in tools_under_test:
            kind = "tool_under_test"
        elif bundle_id in third_party:
            kind = "third_party"
        elif bundle_id in planted:
            kind = "planted"
        apps.append(App(name, path, real_path or path, bundle_id, kind))
    return sorted(apps, key=lambda a: a.name.lower()), excluded


def build_inventory(
    vm: VM,
    tools_under_test: set[str],
    third_party: set[str] | None = None,
    planted: set[str] | None = None,
) -> tuple[list[App], dict[str, str]]:
    return parse_inventory(vm.ssh(LIST_CMD, 300), tools_under_test, third_party, planted)


def index_coverage(apps: list[App], indexed_paths: set[str]) -> dict[str, bool]:
    return {a.name: a.path in indexed_paths or a.real_path in indexed_paths for a in apps}
