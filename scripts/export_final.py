"""Public export of the final held-out campaign: whitelisted fields only, never row titles,
host-machine readings or paths.

usage: python -m scripts.export_final HELDOUT NONCE OUT_DIR PART_DIR [PART_DIR ...]
Scored parts get samples.jsonl (bench.export rows, one per reported sample). Every part,
including a stopped one, gets attempts.jsonl (delivery outcome of every attempt), blocks.jsonl
and meta.json.
"""

import json
import sys
from pathlib import Path
from typing import Any

from bench.delivery import classify
from bench.export import PUBLIC_FIELDS, export_public
from bench.final import load_heldout, published_commitment
from bench.generate import Query
from bench.runner import _sample
from bench.score import score_sample
from bench.selection import select_samples

SAMPLE_EXTRA = frozenset({"flagged", "block"})
ATTEMPT_FIELDS = frozenset(
    {
        "query_id",
        "tool",
        "run",
        "condition",
        "block",
        "attempt",
        "outcome",
        "prep_ms",
        "failed_rechecks",
        "block_flagged",
    }
)
BLOCK_FIELDS = frozenset(
    {
        "block",
        "attempt",
        "requeue_of_errors",
        "pause_ms",
        "slots",
        "results",
        "secs",
        "flagged",
        "reasons",
    }
)
META_FIELDS = frozenset(
    {
        "label",
        "campaign",
        "env",
        "snapshot",
        "probe",
        "probe_sha256",
        "window_ms",
        "block_size",
        "macos",
        "raycast",
        "index_settled",
        "locked",
        "prepared",
        "commit",
        "heldout_commitment",
    }
)


def sample_rows(
    raw: list[dict[str, Any]],
    flagged: dict[tuple[int, int], bool],
    queries: dict[str, Query],
    env: str,
) -> list[dict[str, Any]]:
    picked, kept_errors = select_samples(raw, flagged)
    if kept_errors:
        raise SystemExit(f"{len(kept_errors)} kept errors: export has no row format for them")
    rows = []
    for slot in sorted(picked):
        rec = picked[slot]
        sample = _sample(rec, env)  # type: ignore[arg-type]
        (row,) = export_public([(sample, queries[slot[0]], score_sample(sample, queries[slot[0]]))])
        row.update(flagged=rec["flagged"], block=rec["block"])
        if not set(row) <= PUBLIC_FIELDS | SAMPLE_EXTRA:
            raise AssertionError(set(row) - PUBLIC_FIELDS - SAMPLE_EXTRA)
        rows.append(row)
    return rows


def attempt_rows(
    raw: list[dict[str, Any]], flagged: dict[tuple[int, int], bool]
) -> list[dict[str, Any]]:
    return [
        {
            "query_id": r["query_id"],
            "tool": r["tool"],
            "run": r["run"],
            "condition": r["condition"],
            "block": r["block"],
            "attempt": r["attempt"],
            "outcome": classify(r),
            "prep_ms": r.get("prep_ms"),
            "failed_rechecks": r.get("failed_rechecks"),
            "block_flagged": flagged[(r["block"], r["attempt"])],
        }
        for r in raw
    ]


def _pick(d: dict[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if k in fields}


def export_part(part_dir: Path, queries: dict[str, Query], out: Path) -> dict[str, int]:
    meta = json.loads((part_dir / "meta.json").read_text())
    blocks = [json.loads(x) for x in (part_dir / "blocks.jsonl").read_text().splitlines()]
    raw = [json.loads(x) for x in (part_dir / "raw.jsonl").read_text().splitlines()]
    flagged = {(b["block"], b["attempt"]): b["flagged"] for b in blocks}
    out.mkdir(parents=True, exist_ok=False)
    files: dict[str, list[dict[str, Any]]] = {
        "attempts.jsonl": attempt_rows(raw, flagged),
        "blocks.jsonl": [_pick(b, BLOCK_FIELDS) for b in blocks],
    }
    if not (part_dir / "stopped.txt").exists():
        files["samples.jsonl"] = sample_rows(raw, flagged, queries, meta["env"])
    for name, rows in files.items():
        (out / name).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    public_meta = _pick(meta, META_FIELDS)
    if (part_dir / "stopped.txt").exists():
        public_meta["stopped"] = (part_dir / "stopped.txt").read_text().strip()
    (out / "meta.json").write_text(json.dumps(public_meta, indent=1, sort_keys=True) + "\n")
    return {name: len(rows) for name, rows in files.items()}


def main() -> int:
    heldout, nonce, out_dir = map(Path, sys.argv[1:4])
    held = load_heldout(heldout, nonce, published_commitment(Path("LOCK.txt").read_text()))
    for part_dir in map(Path, sys.argv[4:]):
        print(part_dir.name, export_part(part_dir, held.queries, out_dir / part_dir.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
