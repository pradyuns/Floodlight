import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from bench.generate import (
    generate_collisions,
    generate_dev,
    generate_stepped,
    queries_to_json,
)
from bench.inventory import App, build_inventory, index_coverage, manifest_kinds
from bench.vm import VM


def cmd_inventory(args: argparse.Namespace) -> int:
    tools_under_test, third_party = manifest_kinds(Path(args.manifest).read_text())
    vm = VM(args.clone_name, args.base)
    vm.clone()
    try:
        vm.start()
        settle = vm.wait_index_settled()
        apps, excluded = build_inventory(vm, tools_under_test, third_party)
        coverage = index_coverage(apps, vm.indexed_paths())
        macos = vm.ssh("sw_vers -productVersion; sw_vers -buildVersion", 30).split()
    finally:
        vm.destroy()
    out = {
        "macos": {"version": macos[0], "build": macos[1]},
        "base_snapshot": args.base,
        "index_settled": settle.settled,
        "apps": [asdict(a) for a in apps],
        "excluded": excluded,
        "indexed": coverage,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    missing = [name for name, ok in coverage.items() if not ok]
    kinds = dict(Counter(a.kind for a in apps))
    not_installed = sorted((tools_under_test | third_party) - {a.bundle_id for a in apps})
    print(
        f"apps={len(apps)} kinds={kinds} excluded={excluded} settled={settle.settled} "
        f"missing={missing} not_installed={not_installed}"
    )
    if missing or not_installed or not settle.settled:
        return 1
    return 0


def cmd_queries(args: argparse.Namespace) -> int:
    inventory = [App(**a) for a in json.loads(Path(args.inventory).read_text())["apps"]]
    out_dir = Path(args.out_dir)
    suites = {
        "dev-queries.json": generate_dev(inventory),
        "collision-queries.json": generate_collisions(inventory),
        "stepped-queries.json": generate_stepped(inventory),
    }
    for name, queries in suites.items():
        (out_dir / name).write_text(queries_to_json(queries))
        print(f"{name}: {len(queries)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench")
    sub = parser.add_subparsers(required=True)
    inv = sub.add_parser("inventory", help="build the reference app inventory from a fresh clone")
    inv.add_argument("--base", default="bench-clean-2026-11-12")
    inv.add_argument("--clone-name", default="bench-inventory")
    inv.add_argument("--out", required=True)
    inv.add_argument("--manifest", default="data/third-party.json")
    inv.set_defaults(func=cmd_inventory)
    qs = sub.add_parser("queries", help="write the dev, collision and stepped query files")
    qs.add_argument("--inventory", required=True)
    qs.add_argument("--out-dir", default="data")
    qs.set_defaults(func=cmd_queries)
    args = parser.parse_args()
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
