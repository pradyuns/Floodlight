"""Summarizes pilot runs (unscored) into the numbers that set the locked pilot-derived settings.

usage: python -m scripts.pilot_report RUN_DIR [RUN_DIR ...]
Prints per-tool error rate, time per sample, key lateness, input overhead, late-change rate for
3/4 s windows against 5 s, checkpoint unobserved rates, and host conditions. No result titles.
"""

import itertools
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

from bench.generate import queries_from_json
from bench.runner import parse_results
from bench.score import score_sample

QUERY_FILES = ("data/dev-queries.json",)


def _pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(p * len(s)))] if s else float("nan")


def main() -> int:
    queries = {q.id: q for f in QUERY_FILES for q in queries_from_json(Path(f).read_text())}
    for d in map(Path, sys.argv[1:]):
        meta = json.loads((d / "meta.json").read_text())
        samples = parse_results(d / "raw.jsonl", meta["env"])
        blocks = [json.loads(line) for line in (d / "blocks.jsonl").read_text().splitlines()]
        print(
            f"== {d.name}: env={meta['env']} window={meta['window_ms']} ms, {len(samples)} samples"
        )
        secs = sum(b["secs"] for b in blocks) / max(1, sum(b["results"] for b in blocks))
        print(f"time per sample: {secs:.2f} s; guest ready wait {meta.get('guest_ready_wait_s')} s")
        by_tool: dict[str, list] = defaultdict(list)
        for s in samples:
            by_tool[s.tool].append(s)
        for tool, ss in sorted(by_tool.items()):
            errors = Counter(s.error for s in ss if s.error)
            ok = [s for s in ss if not s.error]
            lateness = [s.max_key_lateness_ms for s in ok]
            overhead = [s.field_shows_ms - s.final_key_post_ms for s in ok if s.field_shows_ms]
            late = {3000: 0, 4000: 0}
            unobs = Counter()
            for s in ok:
                q = queries[s.query_id]
                full = score_sample(s, q, window_ms=5000)
                for w in late:
                    if score_sample(s, q, window_ms=w).intended_at1 != full.intended_at1:
                        late[w] += 1
                for cp in (100, 250):
                    unobs[cp] += full.wrong_enter[cp] == "unobserved"
            n = max(1, len(ok))
            print(
                f"  {tool:9} n={len(ss)} errors={sum(errors.values())} {dict(errors)}\n"
                f"            key lateness max/p95: {max(lateness, default=0)}/"
                f"{_pct(lateness, 0.95)} ms;"
                f" input overhead median/p95: {statistics.median(overhead) if overhead else 'n/a'}/"
                f"{_pct(overhead, 0.95)} ms\n"
                f"            top-1 changes after 3 s: {late[3000] / n:.1%}, after 4 s:"
                f" {late[4000] / n:.1%}; unobserved at 100 ms: {unobs[100] / n:.1%},"
                f" 250 ms: {unobs[250] / n:.1%}"
            )
        host = [h for b in blocks for h in b["host"]]
        rates = [
            ((b2["swapins"] - b1["swapins"]) + (b2["swapouts"] - b1["swapouts"]))
            / max(b2["t"] - b1["t"], 1e-9)
            for b in blocks
            for b1, b2 in itertools.pairwise(b["host"])
        ]
        loads = [h["load1"] for h in host]
        print(
            f"  host: load1 median/p95/max {statistics.median(loads):.2f}/{_pct(loads, 0.95):.2f}/"
            f"{max(loads):.2f}; pressure levels {dict(Counter(h['pressure_level'] for h in host))};"
            f" swap pages/s p95/max {_pct(rates, 0.95):.0f}/{max(rates, default=0):.0f};"
            f" on AC {all(h['on_ac'] for h in host)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
