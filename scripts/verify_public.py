"""Checks the released results from the public files alone: verifies the held-out commitment, then
recomputes the primary statistic and the matched-query timing table from the exported samples.
It re-aggregates exported per-sample scores; it cannot rescore accessibility rows (titles are not
released) or check what was on screen.

usage: python -m scripts.verify_public HELDOUT_JSON NONCE_BIN WARM_SAMPLES_JSONL
"""

import json
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from bench.baseline import RUNS
from bench.final import FINAL_TOOLS, load_heldout, published_commitment
from bench.generate import Query
from bench.stats import _percentile, app_means, paired_cluster_bootstrap, verdict, weighted_mean

TOOLS = FINAL_TOOLS


def _require_one_per_slot(rows: list[dict[str, Any]], primary: set[str]) -> None:
    """Exactly one warm sample for every primary query, tool and run; otherwise the statistics
    would silently describe a different set."""
    seen = Counter((s["query_id"], s["tool"], s["run"]) for s in rows)
    expected = {(q, t, r) for q in primary for t in TOOLS for r in range(RUNS)}
    problems = []
    if missing := expected - set(seen):
        problems.append(f"{len(missing)} missing, e.g. {sorted(missing)[0]}")
    if duplicate := [k for k, n in seen.items() if n > 1]:
        problems.append(f"{len(duplicate)} duplicate, e.g. {sorted(duplicate)[0]}")
    if unexpected := set(seen) - expected:
        problems.append(f"{len(unexpected)} unexpected, e.g. {sorted(unexpected)[0]}")
    if problems:
        raise ValueError("primary samples incomplete: " + "; ".join(problems))


def primary_and_timing(samples: list[dict[str, Any]], queries: dict[str, Query]) -> dict[str, Any]:
    primary = {k for k, q in queries.items() if q.stratum == "b" and not q.ambiguous}
    rows = [s for s in samples if s["query_id"] in primary and s["condition"] == "warm"]
    _require_one_per_slot(rows, primary)
    values: dict[str, list[tuple[str, str, float]]] = {t: [] for t in TOOLS}
    for s in rows:
        q = queries[s["query_id"]]
        assert q.intended is not None
        values[s["tool"]].append((q.intended.id, q.id, float(s["intended_at1"] is True)))
    out: dict[str, Any] = {
        t: {
            "hits": int(sum(v for *_, v in values[t])),
            "n": len(values[t]),
            "app_weighted": 100 * weighted_mean(values[t], "app"),
        }
        for t in TOOLS
    }
    est, lo, hi = paired_cluster_bootstrap(
        app_means(values["floodlight"]), app_means(values["spotlight"])
    )
    out["floodlight_minus_spotlight"] = {
        "diff": est,
        "lo": lo,
        "hi": hi,
        "verdict": verdict(lo, hi),
    }
    by_query: dict[str, list[dict[str, Any]]] = {}
    for s in rows:
        by_query.setdefault(s["query_id"], []).append(s)
    matched = sorted(k for k, ss in by_query.items() if all(s["intended_at1"] is True for s in ss))
    out["matched_queries"] = len(matched)
    for t in TOOLS:
        times = sorted(s["t_at1"] for k in matched for s in by_query[k] if s["tool"] == t)
        out[t]["t_at1_p50"] = statistics.median(times) if times else None
        out[t]["t_at1_p95"] = _percentile(times, 0.95) if times else None
    return out


def main() -> int:
    heldout, nonce, samples_path = map(Path, sys.argv[1:4])
    held = load_heldout(heldout, nonce, published_commitment(Path("LOCK.txt").read_text()))
    print("commitment verified")
    samples = [json.loads(x) for x in samples_path.read_text().splitlines()]
    print(json.dumps(primary_and_timing(samples, held.queries), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
