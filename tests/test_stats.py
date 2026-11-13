import pytest

from bench.stats import (
    error_check,
    first_top1_prefix_len,
    paired_cluster_bootstrap,
    paired_stratified_bootstrap,
    prefix_stability,
    verdict,
    weighted_mean,
)


@pytest.mark.parametrize(
    ("lo", "hi", "expected"),
    [(6, 12, "better"), (2, 14, "inconclusive"), (-3, 4, "similar"), (-12, -6, "worse")],
)
def test_verdict_uses_five_point_margin(lo: float, hi: float, expected: str) -> None:
    assert verdict(lo, hi) == expected


def test_app_weighting_differs_from_query_weighting() -> None:
    values = [("A", "a1", 1.0), ("A", "a2", 1.0), ("A", "a3", 1.0), ("B", "b1", 0.0)]
    assert weighted_mean(values, by="app") == pytest.approx(0.5)
    assert weighted_mean(values, by="query") == pytest.approx(0.75)


def test_repeats_are_averaged_per_query_first() -> None:
    values = [("A", "a1", 1.0), ("A", "a1", 0.0), ("A", "a2", 1.0)]
    assert weighted_mean(values, by="app") == pytest.approx(0.75)


def test_bootstrap_of_identical_tools_is_zero_width_at_zero() -> None:
    a = {"A": 0.5, "B": 1.0, "C": 0.0}
    diff, lo, hi = paired_cluster_bootstrap(a, dict(a), n=500)
    assert (diff, lo, hi) == (0.0, 0.0, 0.0)


def test_bootstrap_reports_percentage_points_and_contains_the_estimate() -> None:
    a = {f"app{i}": 1.0 if i % 2 else 0.5 for i in range(40)}
    b = {k: v - 0.1 for k, v in a.items()}
    diff, lo, hi = paired_cluster_bootstrap(a, b, n=500)
    assert diff == pytest.approx(10.0)
    assert lo <= diff <= hi


def test_stratified_bootstrap_weights_strata_equally() -> None:
    a = {"b1": 1.0, "b2": 1.0, "b3": 1.0, "t1": 0.0}
    b = {"b1": 0.0, "b2": 0.0, "b3": 0.0, "t1": 0.0}
    strata = {"b1": "builtin", "b2": "builtin", "b3": "builtin", "t1": "third_party"}
    diff, _, _ = paired_stratified_bootstrap(a, b, strata, n=200)
    assert diff == pytest.approx(50.0)


def test_flip_flop_prefix_gives_first_length_one_and_two_thirds_stability() -> None:
    at1 = [True, False, True]
    assert first_top1_prefix_len(at1) == 1
    assert prefix_stability(at1) == pytest.approx(2 / 3)


def test_never_top1_has_no_prefix_length() -> None:
    assert first_top1_prefix_len([False, False]) is None


def test_error_check_flags_high_or_uneven_error_rates() -> None:
    assert error_check(1000, {"spotlight": 10, "raycast": 20}) == "ok"
    assert error_check(1000, {"spotlight": 60, "raycast": 60}) == "inconclusive"
    assert error_check(1000, {"spotlight": 0, "raycast": 30}) == "inconclusive"
