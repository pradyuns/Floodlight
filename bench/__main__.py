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


def cmd_fixtures(args: argparse.Namespace) -> int:
    from corpus.make_corpus import Entry, write_tar
    from fixtures.plan import PUBLIC_SEED, build_layout, corpus_forbid

    inventory = [App(**a) for a in json.loads(Path(args.inventory).read_text())["apps"]]
    layout = build_layout(inventory, Path(args.dictionary))
    fam = layout.families
    data, out = Path(args.data_dir), Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifests = {
        "planted-dev-queries.json": list(fam["planted-dev"].queries),
        "stress-queries.json": [
            q for k in ("stress-2x2", "stress-two-word", "stress-test-py") for q in fam[k].queries
        ],
        "folder-queries.json": list(fam["folders"].queries),
        "cross-kind-queries.json": list(fam["cross-kind"].queries),
    }
    for name, queries in manifests.items():
        (data / name).write_text(queries_to_json(queries))
        print(f"{name}: {len(queries)}")
    plan = {
        k: {"apps": list(f.apps), "files": list(f.files), "decoys": list(f.decoys)}
        for k, f in fam.items()
    }
    (data / "fixture-layout.json").write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n")
    for k, f in fam.items():
        (out / f"{k}-apps.txt").write_text("".join(a + "\n" for a in f.apps))
        if f.files:
            write_tar([Entry(p, "fixture") for p in f.files], PUBLIC_SEED, out / f"{k}.tar.gz")
    (out / "corpus-forbid.json").write_text(json.dumps(sorted(corpus_forbid(layout))) + "\n")
    print(f"families={len(fam)} out={out}")
    return 0


REPO = Path(__file__).resolve().parent.parent


def cmd_heldout(args: argparse.Namespace) -> int:
    import hashlib
    import os

    from bench.heldout import build_heldout, canonical_bytes, commitment

    out = Path(args.out_dir).expanduser().resolve()
    if out == REPO or REPO in out.parents:
        sys.exit("refusing: --out-dir is inside the repo; the held-out file must stay private")
    files = (out / "heldout.json", out / "nonce.bin")
    if any(f.exists() for f in files):
        sys.exit("refusing: held-out output already exists in --out-dir; nothing overwritten")
    data_dir = Path(args.data_dir)
    public: set[str] = set()
    for f in sorted(data_dir.glob("*queries*.json")):
        public |= {q["text"] for q in json.loads(f.read_text())}
    layout = json.loads((data_dir / "fixture-layout.json").read_text())
    names = {a.replace("\u200e", "") for fam in layout.values() for a in fam["apps"]}
    apps = [App(**a) for a in json.loads(Path(args.inventory).read_text())["apps"]]
    seed = Path(args.seed_file).expanduser().read_bytes()
    if len(seed.strip()) < 16:
        sys.exit("refusing: the seed file should hold at least 16 random characters")
    heldout = build_heldout(seed, apps, Path(args.dictionary), public, names)
    data = canonical_bytes(heldout)
    nonce = os.urandom(32)
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    files[0].write_bytes(data)
    files[1].write_bytes(nonce)
    print(f"commitment: {commitment(nonce, data)}")
    print(
        f"stratum_a={len(heldout['strata']['a'])} stratum_b={len(heldout['strata']['b'])} "
        f"secret_apps={len(heldout['planted_names'])} "
        f"b_overlap_with_public={heldout['overlap_b_with_dev']}"
    )
    print(f"dictionary_sha256={hashlib.sha256(Path(args.dictionary).read_bytes()).hexdigest()}")
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
    fx = sub.add_parser("fixtures", help="write fixture query files and per-family bundles")
    fx.add_argument("--inventory", required=True)
    fx.add_argument("--dictionary", default="/usr/share/dict/words")
    fx.add_argument("--data-dir", default="data")
    fx.add_argument("--out-dir", default="fixtures/out")
    fx.set_defaults(func=cmd_fixtures)
    ho = sub.add_parser("heldout", help="write the secret held-out set; prints digest and counts")
    ho.add_argument("--seed-file", required=True)
    ho.add_argument("--out-dir", required=True)
    ho.add_argument("--inventory", default="data/inventory-macos-26.4.1.json")
    ho.add_argument("--dictionary", default="/usr/share/dict/words")
    ho.add_argument("--data-dir", default="data")
    ho.set_defaults(func=cmd_heldout)
    args = parser.parse_args()
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
