"""Reference app inventory, built from .app bundles on the VM filesystem (never from mdfind)."""

import json
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal

from bench.vm import VM

AppKind = Literal["builtin", "third_party", "tool_under_test", "planted"]
TOOLS_UNDER_TEST = frozenset({"com.raycast.macos"})

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


def manifest_kinds(manifest_json: str) -> tuple[set[str], set[str]]:
    """Splits the third-party manifest into (tools under test, third-party) bundle ids."""
    ids: set[str] = set()
    for entry in json.loads(manifest_json):
        bundle_id = entry.get("bundle_id")
        if not isinstance(bundle_id, str) or not bundle_id:
            raise ValueError(f"manifest entry without bundle_id: {entry}")
        ids.add(bundle_id)
    return ids & TOOLS_UNDER_TEST, ids - TOOLS_UNDER_TEST


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


def parse_bundle_names(output: str, apps_by_path: dict[str, str]) -> dict[str, Any]:
    """Alias table from scripts/app_names.sh output: each app's other names from its own bundle
    (Info.plist and English localizations), with their source. A name claimed by two apps is
    refused, so an alias can never make a row ambiguous."""
    from bench.normalize import normalize

    meta = {}
    found: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if parts[0] in ("LOCALE", "LANGS"):
            meta[parts[0]] = parts[1]
        elif parts[0] == "NAME":
            _, path, source, key, value = parts
            name = apps_by_path[path]
            if normalize(value) != normalize(name):
                found.setdefault(name, {}).setdefault(value, f"{source} {key}")
    owners: dict[str, set[str]] = {}
    shown: dict[str, set[str]] = {}
    pairs = [(name, name) for name in apps_by_path.values()]
    pairs += [(alias, name) for name, aliases in found.items() for alias in aliases]
    for text, name in pairs:
        owners.setdefault(normalize(text), set()).add(name)
        shown.setdefault(normalize(text), set()).add(text)
    shared = {"/".join(sorted(shown[n])): sorted(o) for n, o in owners.items() if len(o) > 1}
    if shared:
        raise ValueError(f"names claimed by more than one app: {shared}")
    return {
        "locale": meta["LOCALE"],
        "languages": meta["LANGS"],
        "aliases": {
            name: [[alias, src] for alias, src in sorted(aliases.items())]
            for name, aliases in sorted(found.items())
        },
    }
