"""Whitelisted public export: ids, ranks, timings and kinds only, never free-text titles."""

from typing import Any

from bench.generate import Query
from bench.model import Sample
from bench.score import SampleScore

PUBLIC_FIELDS = frozenset(
    {
        "query_id",
        "suite",
        "rule",
        "mode",
        "query_length",
        "ambiguous",
        "tool",
        "env",
        "run",
        "condition",
        "attempt",
        "error",
        "intended_at1",
        "acceptable_at1",
        "wrong_enter_100",
        "wrong_enter_250",
        "wrong_enter_500",
        "wrong_enter_1000",
        "safe_enter",
        "rr10",
        "t_first_appear",
        "t_at1",
        "final_observed_rank",
        "coverage_miss",
        "identity_unresolved",
        "final_unobserved",
    }
)


def export_public(items: list[tuple[Sample, Query, SampleScore]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample, query, score in items:
        row: dict[str, Any] = {
            "query_id": query.id,
            "suite": query.suite,
            "rule": query.rule,
            "mode": query.mode,
            "query_length": len(query.text),
            "ambiguous": query.ambiguous,
            "tool": sample.tool,
            "env": sample.env,
            "run": sample.run,
            "condition": sample.condition,
            "attempt": sample.attempt,
            "error": sample.error is not None,
            "intended_at1": score.intended_at1,
            "acceptable_at1": score.acceptable_at1,
            "safe_enter": score.safe_enter,
            "rr10": score.rr10,
            "t_first_appear": score.t_first_appear,
            "t_at1": score.t_at1,
            "final_observed_rank": score.final_observed_rank,
            "coverage_miss": score.coverage_miss,
            "identity_unresolved": score.identity_unresolved,
            "final_unobserved": score.final_unobserved,
        }
        for cp, value in score.wrong_enter.items():
            row[f"wrong_enter_{cp}"] = value
        assert set(row) <= PUBLIC_FIELDS
        rows.append(row)
    return rows
