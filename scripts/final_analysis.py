"""Scores the final held-out campaign parts with the locked scoring and statistics (analysis plan
§7-§9, items 28-30). Each part is scored on its own; nothing is pooled.

usage: python -m scripts.final_analysis HELDOUT NONCE OUT_DIR PART_DIR [PART_DIR ...]
Writes OUT_DIR/<part>.json (numbers) and OUT_DIR/<part>-misses.jsonl (every non-hit, for reading
by hand). Both contain query text and result titles: local only, never committed.
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from bench.final import FINAL_TOOLS, final_plan, load_heldout, published_commitment
from bench.generate import Query
from bench.runner import _sample
from bench.score import SampleScore, score_sample
from bench.selection import select_samples
from bench.stats import (
    app_means,
    error_check,
    paired_cluster_bootstrap,
    run_spread,
    unobserved_check,
    verdict,
    weighted_mean,
)

Slot = tuple[str, str, int, str]


def _length_bucket(text: str) -> str:
    n = len(text)
    return str(n) if n < 4 else "4+"


def _outcome(score: SampleScore | None) -> str:
    if score is None:
        return "kept_error"
    if score.final_unobserved:
        return "unobserved"
    if score.identity_unresolved:
        return "unresolved"
    return "hit" if score.intended_at1 else "miss"


def _compare(values: dict[str, list[tuple[str, str, float]]], a: str, b: str) -> dict[str, Any]:
    est, lo, hi = paired_cluster_bootstrap(app_means(values[a]), app_means(values[b]))
    qa, qb = weighted_mean(values[a], "query"), weighted_mean(values[b], "query")
    return {
        "diff": round(est, 2),
        "lo": round(lo, 2),
        "hi": round(hi, 2),
        "verdict": verdict(lo, hi),
        "query_weighted_diff": round(100 * (qa - qb), 2),
    }


def analyse(
    part_dir: Path, queries: dict[str, Query], held: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    meta = json.loads((part_dir / "meta.json").read_text())
    part = meta.get("campaign") or meta.get("part") or part_dir.name.rsplit("-", 2)[0]
    plan = final_plan(part, held)
    blocks = [json.loads(line) for line in (part_dir / "blocks.jsonl").read_text().splitlines()]
    flagged = {(b["block"], b["attempt"]): b["flagged"] for b in blocks}
    raw = [json.loads(line) for line in (part_dir / "raw.jsonl").read_text().splitlines()]
    picked, kept_errors = select_samples(raw, flagged)
    scheduled: list[Slot] = [
        (q, t, r, c)
        for q in plan.query_ids
        for t in plan.tools
        for r in range(plan.runs)
        for c in plan.conditions
    ]
    missing = [s for s in scheduled if s not in picked and s not in kept_errors]
    scores: dict[Slot, SampleScore | None] = {}
    for slot in scheduled:
        rec = picked.get(slot)
        scores[slot] = (
            None if rec is None else score_sample(_sample(rec, plan.env), queries[slot[0]])
        )

    per_tool_sched = len(scheduled) // len(plan.tools)
    first = Counter(r["tool"] for r in raw if r["attempt"] == 0 and r.get("error"))
    out: dict[str, Any] = {
        "part": part,
        "dir": part_dir.name,
        "env": plan.env,
        "conditions": plan.conditions,
        "queries": len(plan.query_ids),
        "scheduled_per_tool": per_tool_sched,
        "attempts_recorded": len(raw),
        "flagged_blocks": sum(b["flagged"] for b in blocks),
        "reported_flagged": sum(1 for r in picked.values() if r["flagged"]),
        "kept_errors": dict(Counter(s[1] for s in kept_errors + missing)),
        "first_attempt_errors": dict(first),
    }
    errors_by_tool = {t: out["kept_errors"].get(t, 0) for t in plan.tools}
    out["error_gate"] = error_check(per_tool_sched, errors_by_tool)

    def subset(cond: str, stratum: str | None, unambiguous: bool = True) -> list[Slot]:
        return [
            s
            for s in scheduled
            if s[3] == cond
            and (stratum is None or queries[s[0]].stratum == stratum)
            and (not unambiguous or not queries[s[0]].ambiguous)
        ]

    def table(slots: list[Slot]) -> dict[str, Any]:
        res: dict[str, Any] = {}
        values: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
        per_run: dict[str, dict[int, list[tuple[str, str, float]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for slot in slots:
            q = queries[slot[0]]
            app = q.intended.id if q.intended else slot[0]
            v = 1.0 if _outcome(scores[slot]) == "hit" else 0.0
            values[slot[1]].append((app, slot[0], v))
            per_run[slot[1]][slot[2]].append((app, slot[0], v))
        for t in plan.tools:
            ts = [s for s in slots if s[1] == t]
            outc = Counter(_outcome(scores[s]) for s in ts)
            we = Counter(str(sc.wrong_enter[250]) for s in ts if (sc := scores[s]) is not None)
            res[t] = {
                "n": len(ts),
                "intended_at1_app_weighted": round(100 * weighted_mean(values[t], "app"), 2),
                "outcomes": dict(outc),
                "run_spread_points": round(
                    run_spread({r: weighted_mean(v, "app") for r, v in per_run[t].items()}), 2
                ),
                "wrong_enter_250_selected_row_proxy": dict(we),
            }
        unobs = {t: res[t]["outcomes"].get("unobserved", 0) for t in plan.tools}
        n_tool = len(slots) // len(plan.tools)
        res["observability_gate"] = unobserved_check(n_tool, unobs)
        res["floodlight_minus_spotlight"] = _compare(values, "floodlight", "spotlight")
        res["floodlight_minus_raycast"] = _compare(values, "floodlight", "raycast")
        res["raycast_minus_spotlight"] = _compare(values, "raycast", "spotlight")
        return res

    for cond in plan.conditions:
        out[f"{cond}:stratum_b_unambiguous"] = table(subset(cond, "b"))
        out[f"{cond}:stratum_a"] = table(subset(cond, "a"))
        out[f"{cond}:all_unambiguous"] = table(subset(cond, None))
        for label, key in (
            ("rule", lambda q: q.rule),
            ("length", lambda q: _length_bucket(q.text)),
        ):
            groups: dict[str, list[Slot]] = defaultdict(list)
            for s in subset(cond, None):
                groups[f"{queries[s[0]].stratum}:{key(queries[s[0]])}"].append(s)
            out[f"{cond}:by_{label}"] = {
                g: {
                    t: round(
                        100
                        * sum(_outcome(scores[s]) == "hit" for s in ss if s[1] == t)
                        / max(1, sum(s[1] == t for s in ss)),
                        1,
                    )
                    for t in plan.tools
                }
                for g, ss in sorted(groups.items())
            }
        amb = subset(cond, None, unambiguous=False)
        out[f"{cond}:ambiguous_acceptable_at1"] = {
            t: round(
                100
                * statistics_share(
                    [
                        (sc := scores[s]) is not None and sc.acceptable_at1 is True
                        for s in amb
                        if s[1] == t and queries[s[0]].ambiguous
                    ]
                ),
                1,
            )
            for t in plan.tools
        }

    misses = []
    for slot in scheduled:
        oc = _outcome(scores[slot])
        if oc == "hit":
            continue
        q = queries[slot[0]]
        rec = picked.get(slot)
        final_rows: list[dict[str, Any]] = []
        if rec is not None:
            snaps = [
                s
                for s in rec["snapshots"]
                if s["read_end_ms"] <= rec["final_key_post_ms"] + 3000
                and not s["field_mismatch"]
                and s.get("unreadable") is None
            ]
            if snaps:
                final_rows = [
                    {"title": r["title"], "kind": r["kind"]} for r in snaps[-1]["rows"][:5]
                ]
        misses.append(
            {
                "part": part,
                "tool": slot[1],
                "run": slot[2],
                "condition": slot[3],
                "query_id": q.id,
                "text": q.text,
                "rule": q.rule,
                "stratum": q.stratum,
                "ambiguous": q.ambiguous,
                "intended": q.intended.id if q.intended else None,
                "outcome": oc,
                "rank": None if (sc := scores[slot]) is None else sc.final_observed_rank,
                "final_rows": final_rows,
            }
        )
    return out, misses


def statistics_share(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else float("nan")


def main() -> int:
    heldout, nonce, out_dir = map(Path, sys.argv[1:4])
    digest = published_commitment(Path("LOCK.txt").read_text())
    held = load_heldout(heldout, nonce, digest)
    out_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    for part_dir in map(Path, sys.argv[4:]):
        summary, misses = analyse(part_dir, held.queries, held)
        name = part_dir.name
        (out_dir / f"{name}.json").write_text(json.dumps(summary, indent=1, default=str))
        (out_dir / f"{name}-misses.jsonl").write_text("".join(json.dumps(m) + "\n" for m in misses))
        print(f"{name}: {len(misses)} non-hits written")
    assert set(FINAL_TOOLS) == {"spotlight", "raycast", "floodlight"}
    return 0


if __name__ == "__main__":
    sys.exit(main())
