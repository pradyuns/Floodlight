"""App-clustered, paired statistics and the ±5-point verdict rule (spec §8, §13.10)."""

import random
import statistics
from collections import defaultdict
from typing import Literal

Verdict = Literal["better", "worse", "similar", "inconclusive"]
MARGIN_POINTS = 5.0
MAX_ERROR_RATE = 0.05
MAX_ERROR_GAP = 0.02


def verdict(lo: float, hi: float, margin: float = MARGIN_POINTS) -> Verdict:
    if lo > margin:
        return "better"
    if hi < -margin:
        return "worse"
    if lo >= -margin and hi <= margin:
        return "similar"
    return "inconclusive"


def app_means(values: list[tuple[str, str, float]]) -> dict[str, float]:
    """(app, query_id, value) rows -> per-app mean of per-query means."""
    per_query: dict[tuple[str, str], list[float]] = defaultdict(list)
    for app, query_id, value in values:
        per_query[(app, query_id)].append(value)
    per_app: dict[str, list[float]] = defaultdict(list)
    for (app, _), repeats in per_query.items():
        per_app[app].append(statistics.fmean(repeats))
    return {app: statistics.fmean(qs) for app, qs in per_app.items()}


def weighted_mean(values: list[tuple[str, str, float]], by: Literal["app", "query"]) -> float:
    if by == "app":
        return statistics.fmean(app_means(values).values())
    per_query: dict[tuple[str, str], list[float]] = defaultdict(list)
    for app, query_id, value in values:
        per_query[(app, query_id)].append(value)
    return statistics.fmean(statistics.fmean(v) for v in per_query.values())


def _percentile(sorted_values: list[float], p: float) -> float:
    index = min(len(sorted_values) - 1, max(0, round(p * (len(sorted_values) - 1))))
    return sorted_values[index]


def paired_cluster_bootstrap(
    a: dict[str, float], b: dict[str, float], n: int = 10_000, seed: int = 42
) -> tuple[float, float, float]:
    """Difference a-b in percentage points with a 95% interval, resampling apps (paired)."""
    apps = sorted(set(a) & set(b))
    diffs = [a[x] - b[x] for x in apps]
    estimate = 100 * statistics.fmean(diffs)
    rng = random.Random(seed)
    boots = sorted(100 * statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(n))
    return estimate, _percentile(boots, 0.025), _percentile(boots, 0.975)


def paired_stratified_bootstrap(
    a: dict[str, float],
    b: dict[str, float],
    strata: dict[str, str],
    n: int = 10_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """Equal-weight average over strata of per-stratum paired differences (percentage points)."""
    groups: dict[str, list[float]] = defaultdict(list)
    for app in sorted(set(a) & set(b)):
        groups[strata[app]].append(a[app] - b[app])
    names = sorted(groups)
    estimate = 100 * statistics.fmean(statistics.fmean(groups[g]) for g in names)
    rng = random.Random(seed)
    boots = sorted(
        100
        * statistics.fmean(
            statistics.fmean(rng.choices(groups[g], k=len(groups[g]))) for g in names
        )
        for _ in range(n)
    )
    return estimate, _percentile(boots, 0.025), _percentile(boots, 0.975)


def run_spread(per_run: dict[int, float]) -> float:
    """Max minus min of a metric across runs, in percentage points."""
    return 100 * (max(per_run.values()) - min(per_run.values()))


def first_top1_prefix_len(at1_by_prefix: list[bool]) -> int | None:
    return next((k for k, ok in enumerate(at1_by_prefix, start=1) if ok), None)


def prefix_stability(at1_by_prefix: list[bool]) -> float:
    k = first_top1_prefix_len(at1_by_prefix)
    if k is None:
        return 0.0
    tail = at1_by_prefix[k - 1 :]
    return sum(tail) / len(tail)


def error_check(
    scheduled_per_tool: int, errors_by_tool: dict[str, int]
) -> Literal["ok", "inconclusive"]:
    rates = [e / scheduled_per_tool for e in errors_by_tool.values()]
    if max(rates) > MAX_ERROR_RATE or max(rates) - min(rates) > MAX_ERROR_GAP:
        return "inconclusive"
    return "ok"
