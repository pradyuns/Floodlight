import json
from pathlib import Path
from typing import Any

import pytest

from bench.final import Heldout
from bench.generate import Query, Target
from scripts.final_analysis import analyse

ALPHA, BETA, GAMMA = Target("app", "Alpha Desk"), Target("app", "Beta Note"), Target("app", "Gamma")
QUERIES = {
    q.id: q
    for q in [
        Query(
            "h:a1", "alpha desk", "full", "completed", ALPHA, frozenset({ALPHA}), False, "h", "b"
        ),
        Query("h:a2", "alp", "prefix3", "completed", ALPHA, frozenset({ALPHA}), False, "h", "b"),
        Query("h:a3", "alpah", "typo", "completed", ALPHA, frozenset({ALPHA}), False, "h", "b"),
        Query("h:b1", "beta note", "full", "completed", BETA, frozenset({BETA}), False, "h", "b"),
        Query("h:g1", "gamam", "typo", "completed", GAMMA, frozenset({GAMMA}), False, "h", "a"),
    ]
}
HELD = Heldout(QUERIES, ())
TOOLS = ("spotlight", "raycast", "floodlight")
FINAL_KEY = 500


def _rec(
    qid: str,
    tool: str,
    run: int,
    top: str,
    block: int = 0,
    attempt: int = 0,
    fresh: bool = True,
    error: str | None = None,
) -> dict[str, Any]:
    read_end = FINAL_KEY + (2950 if fresh else 400)
    return {
        "query_id": qid,
        "tool": tool,
        "run": run,
        "condition": "warm",
        "mode": "completed",
        "final_key_post_ms": FINAL_KEY,
        "max_key_lateness_ms": 0,
        "key_posts": [{"planned_ms": FINAL_KEY, "actual_ms": FINAL_KEY}],
        "field_shows_ms": FINAL_KEY + 30,
        "snapshots": [
            {
                "read_start_ms": read_end - 10,
                "read_end_ms": read_end,
                "field_text": QUERIES[qid].text,
                "field_mismatch": False,
                "rows": [{"title": top, "kind": "app", "source": "local", "selected": True}],
            }
        ],
        "error": error,
        "block": block,
        "attempt": attempt,
    }


def _part(tmp_path: Path, raw: list[dict[str, Any]], flagged_blocks: set[int]) -> Path:
    d = tmp_path / "final-warm-20990101-0000"
    d.mkdir()
    (d / "meta.json").write_text(json.dumps({"campaign": "final-warm"}))
    blocks = sorted({(r["block"], r["attempt"]) for r in raw})
    (d / "blocks.jsonl").write_text(
        "".join(
            json.dumps({"block": b, "attempt": a, "flagged": b in flagged_blocks}) + "\n"
            for b, a in blocks
        )
    )
    (d / "raw.jsonl").write_text("".join(json.dumps(r) + "\n" for r in raw))
    return d


def _all_hits(skip: set[tuple[str, str, int]] = frozenset()) -> list[dict[str, Any]]:  # type: ignore[assignment]
    return [
        _rec(qid, tool, run, q.intended.id)  # type: ignore[union-attr]
        for qid, q in QUERIES.items()
        for tool in TOOLS
        for run in range(5)
        if (qid, tool, run) not in skip
    ]


def test_apps_weigh_equally_when_they_have_different_query_counts(tmp_path: Path) -> None:
    raw = _all_hits({("h:a3", "spotlight", r) for r in range(5)})
    raw += [_rec("h:a3", "spotlight", r, "Search the Web") for r in range(5)]
    out, misses = analyse(_part(tmp_path, raw, set()), QUERIES, HELD)
    table = out["warm:stratum_b_unambiguous"]
    # Alpha: 2 of 3 queries hit; Beta: 1 of 1. Apps equal: (2/3 + 1) / 2; queries equal: 3/4.
    assert table["spotlight"]["intended_at1_app_weighted"] == pytest.approx(83.33)
    assert table["floodlight_minus_spotlight"]["diff"] == pytest.approx(16.67)
    assert table["floodlight_minus_spotlight"]["query_weighted_diff"] == pytest.approx(25.0)
    assert {(m["tool"], m["query_id"], m["outcome"]) for m in misses} == {
        ("spotlight", "h:a3", "miss")
    }


def test_last_clean_attempt_is_used_when_all_are_flagged_and_labelled_flagged(
    tmp_path: Path,
) -> None:
    raw = _all_hits({("h:a1", "floodlight", 0), ("h:b1", "floodlight", 1)})
    raw += [
        _rec("h:a1", "floodlight", 0, "Search the Web", block=7, attempt=0),
        _rec("h:a1", "floodlight", 0, "Alpha Desk", block=7, attempt=1),
        _rec("h:b1", "floodlight", 1, "Search the Web", block=8, attempt=0),
    ]
    out, _ = analyse(_part(tmp_path, raw, flagged_blocks={7, 8}), QUERIES, HELD)
    # Block 7 attempt 1 is also flagged here, so h:a1 takes the last clean one (a hit, flagged);
    # h:b1 has only a flagged miss, which is reported and labelled, not dropped.
    assert out["reported_flagged"] == 2
    assert out["warm:stratum_b_unambiguous"]["floodlight"]["outcomes"] == {
        "hit": 19,
        "miss": 1,
    }  # stratum b only: 4 queries x 5 runs


def test_missing_errored_and_unobserved_slots_count_as_non_hits(tmp_path: Path) -> None:
    raw = _all_hits({("h:a1", "raycast", 0), ("h:a2", "raycast", 0), ("h:b1", "raycast", 0)})
    raw += [
        _rec("h:a2", "raycast", 0, "Alpha Desk", error="timeout"),
        _rec("h:b1", "raycast", 0, "Beta Note", fresh=False),
    ]
    out, misses = analyse(_part(tmp_path, raw, set()), QUERIES, HELD)
    assert out["kept_errors"] == {"raycast": 2}
    assert out["error_gate"] == "inconclusive"  # 2 of 25 raycast slots = 8%, limit 5%
    assert out["warm:stratum_b_unambiguous"]["raycast"]["outcomes"] == {
        "hit": 17,
        "kept_error": 2,
        "unobserved": 1,
    }
    assert out["warm:stratum_b_unambiguous"]["raycast"]["intended_at1_app_weighted"] == (
        pytest.approx(100 * (13 / 15 + 4 / 5) / 2, abs=0.01)  # run 0 only
    )
    assert {m["outcome"] for m in misses} == {"kept_error", "unobserved"}
