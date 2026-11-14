"""Publishable shape of a corpus: counts, bytes, extensions, depth and name patterns; no names."""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from corpus.make_corpus import CREATION_DAY, Entry, build_manifest
from fixtures.make_files import content_for


def summarize(manifest: list[Entry], seed: int) -> dict[str, Any]:
    sizes = [len(content_for(e.path, seed)) for e in manifest]
    paths = [PurePosixPath(e.path) for e in manifest]
    return {
        "seed": seed,
        "files": len(manifest),
        "bytes": sum(sizes),
        "max_file_bytes": max(sizes, default=0),
        "folders": len({str(p.parent) for p in paths}),
        "by_extension": dict(sorted(Counter(p.suffix for p in paths).items())),
        "by_pattern": dict(sorted(Counter(e.pattern for e in manifest).items())),
        "by_top_folder": dict(sorted(Counter(p.parts[0] for p in paths).items())),
        "by_depth": dict(sorted(Counter(len(p.parts) for p in paths).items())),
        "in_node_modules": sum("node_modules" in p.parts for p in paths),
        "creation_day_utc": datetime.fromtimestamp(CREATION_DAY, UTC).date().isoformat(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(prog="corpus.summary")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--files", type=int, required=True)
    parser.add_argument("--forbid-file", type=Path, required=True)
    args = parser.parse_args()
    forbid = set(json.loads(args.forbid_file.read_text()))
    summary = summarize(build_manifest(args.seed, args.files, forbid), args.seed)
    print(json.dumps(summary, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
