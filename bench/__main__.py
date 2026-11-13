import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from bench.inventory import build_inventory, index_coverage
from bench.vm import VM


def cmd_inventory(args: argparse.Namespace) -> int:
    vm = VM(args.clone_name, args.base)
    vm.clone()
    try:
        vm.start()
        settle = vm.wait_index_settled()
        apps, excluded = build_inventory(vm, tools_under_test=set())
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
    print(f"apps={len(apps)} excluded={len(excluded)} settled={settle.settled} missing={missing}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="bench")
    sub = parser.add_subparsers(required=True)
    inv = sub.add_parser("inventory", help="build the reference app inventory from a fresh clone")
    inv.add_argument("--base", default="bench-clean-2026-11-12")
    inv.add_argument("--clone-name", default="bench-inventory")
    inv.add_argument("--out", required=True)
    inv.set_defaults(func=cmd_inventory)
    args = parser.parse_args()
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
