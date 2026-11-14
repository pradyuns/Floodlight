"""Synthetic busy-Mac corpus: many small valid files under the guest's home, from a public seed.

Usage: python -m corpus.make_corpus --seed S --files N --forbid-file F --out OUT.tar.gz
Extract in the guest with `tar -xzf OUT.tar.gz -C ~`. Targeted names (planted apps, decoys, query
strings) are passed in --forbid-file and never occur in any path.
"""

import argparse
import calendar
import io
import json
import random
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from fixtures.make_files import content_for

CREATION_DAY = calendar.timegm((2026, 1, 15, 12, 0, 0))
VOCABULARY = [
    "amber",
    "anchor",
    "arch",
    "atlas",
    "autumn",
    "badge",
    "basin",
    "beacon",
    "birch",
    "bridge",
    "bronze",
    "cabin",
    "canyon",
    "cedar",
    "chalk",
    "cliff",
    "clover",
    "coast",
    "copper",
    "coral",
    "cotton",
    "crane",
    "crystal",
    "delta",
    "desert",
    "drift",
    "dune",
    "eagle",
    "echo",
    "ember",
    "fabric",
    "falcon",
    "fern",
    "field",
    "flint",
    "forest",
    "frost",
    "garnet",
    "glacier",
    "granite",
    "grove",
    "harbor",
    "hazel",
    "heron",
    "hollow",
    "island",
    "ivory",
    "jade",
    "juniper",
    "lagoon",
    "lantern",
    "ledger",
    "linen",
    "lotus",
    "maple",
    "marble",
    "meadow",
    "mesa",
    "mint",
    "moss",
    "nectar",
    "oak",
    "ocean",
    "olive",
    "opal",
    "orchard",
    "otter",
    "pebble",
    "pine",
    "plaza",
    "prairie",
    "quartz",
    "quill",
    "raven",
    "reef",
    "ridge",
    "saddle",
    "sage",
    "sand",
    "scarlet",
    "shore",
    "sierra",
    "slate",
    "spruce",
    "summit",
    "swift",
    "thistle",
    "timber",
    "topaz",
    "trail",
    "tulip",
    "tundra",
    "valley",
    "velvet",
    "violet",
    "walnut",
    "willow",
    "budget",
    "draft",
    "estimate",
    "invoice",
    "outline",
    "proposal",
    "schedule",
    "summary",
    "minutes",
    "agenda",
    "roadmap",
]
PATTERNS: list[tuple[str, int, tuple[str, ...]]] = [
    ("word-word-N", 30, (".txt", ".md", ".pdf", ".csv", ".json")),
    ("Word Word vN", 10, (".pdf", ".txt")),
    ("word-YYYY-MM-DD", 10, (".pdf", ".csv")),
    ("IMG_NNNN", 15, (".png",)),
    ("word_word", 25, (".py", ".swift", ".js", ".json")),
    ("word-N", 10, (".svg", ".png")),
]
CODE_EXTENSIONS = {".py", ".swift", ".js"}


@dataclass(frozen=True)
class Entry:
    path: str  # relative to the guest home
    pattern: str


def _stem(pattern: str, rng: random.Random) -> str:
    w = rng.choice
    if pattern == "word-word-N":
        return f"{w(VOCABULARY)}-{w(VOCABULARY)}-{rng.randint(1, 99)}"
    if pattern == "Word Word vN":
        return f"{w(VOCABULARY).capitalize()} {w(VOCABULARY).capitalize()} v{rng.randint(1, 9)}"
    if pattern == "word-YYYY-MM-DD":
        return f"{w(VOCABULARY)}-2025-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"
    if pattern == "IMG_NNNN":
        return f"IMG_{rng.randint(0, 9999):04d}"
    if pattern == "word_word":
        return f"{w(VOCABULARY)}_{w(VOCABULARY)}"
    return f"{w(VOCABULARY)}-{rng.randint(1, 999)}"


def _folders(rng: random.Random, count: int) -> tuple[list[str], list[str]]:
    """Document-like folders and project source folders (including node_modules)."""
    w = rng.choice
    docs: list[str] = ["Downloads", "Desktop"]
    code: list[str] = []
    while len(docs) + len(code) < count:
        if rng.random() < 0.6:
            base = f"Documents/{w(VOCABULARY)}-{w(VOCABULARY)}"
            docs.append(base if rng.random() < 0.5 else f"{base}/{rng.randint(2019, 2025)}")
        else:
            repo = f"Projects/{w(VOCABULARY)}-{w(VOCABULARY)}"
            sub = rng.choice(["src", "tests", "docs", f"src/{w(VOCABULARY)}"])
            if rng.random() < 0.2:
                sub = f"node_modules/{w(VOCABULARY)}-{w(VOCABULARY)}/lib"
            code.append(f"{repo}/{sub}")
    return sorted(set(docs)), sorted(set(code))


def build_manifest(seed: int, n: int, forbid: set[str]) -> list[Entry]:
    rng = random.Random(seed)
    banned = [f.lower() for f in forbid]
    docs, code = _folders(rng, max(4, n // 40))
    names = [p[0] for p in PATTERNS]
    weights = [p[1] for p in PATTERNS]
    extensions = {p[0]: p[2] for p in PATTERNS}
    seen: set[str] = set()
    out: list[Entry] = []
    while len(out) < n:
        pattern = rng.choices(names, weights)[0]
        ext = rng.choice(extensions[pattern])
        folder = rng.choice(code if ext in CODE_EXTENSIONS and code else docs)
        path = f"{folder}/{_stem(pattern, rng)}{ext}"
        if path in seen or any(b in path.lower() for b in banned):
            continue
        seen.add(path)
        out.append(Entry(path, pattern))
    return out


def _directories(manifest: list[Entry]) -> list[str]:
    """Every parent below the top-level home folders (those already exist in the guest)."""
    dirs: set[str] = set()
    for e in manifest:
        parents = PurePosixPath(e.path).parents
        dirs.update(str(p) for p in parents if len(p.parts) >= 2)
    return sorted(dirs, key=lambda d: (d.count("/"), d))


def write_tar(manifest: list[Entry], seed: int, out: Path) -> None:
    with tarfile.open(out, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for d in _directories(manifest):
            info = tarfile.TarInfo(d)
            info.type, info.mode, info.mtime = tarfile.DIRTYPE, 0o755, CREATION_DAY
            tar.addfile(info)
        for e in manifest:
            data = content_for(e.path, seed)
            info = tarfile.TarInfo(e.path)
            info.size, info.mode, info.mtime = len(data), 0o644, CREATION_DAY
            tar.addfile(info, io.BytesIO(data))


def main() -> int:
    parser = argparse.ArgumentParser(prog="make_corpus")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--files", type=int, required=True)
    parser.add_argument("--forbid-file", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    forbid = set(json.loads(args.forbid_file.read_text()))
    manifest = build_manifest(args.seed, args.files, forbid)
    write_tar(manifest, args.seed, args.out)
    print(f"files={len(manifest)} forbidden_strings={len(forbid)} out={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
