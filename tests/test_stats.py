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


def _score(at1: bool | None, unresolved: bool = False):  # type: ignore[no-untyped-def]
    from bench.score import SampleScore

    return SampleScore(at1, False, {}, "none", 0.0, None, None, None, False, unresolved)


def test_unresolved_samples_stay_in_the_denominator_with_their_own_rate() -> None:
    from bench.stats import top1_rates

    scores = [_score(True), _score(False), _score(None, True), _score(None, True)]
    rates = top1_rates(scores)
    assert rates.n == 4
    assert (rates.hit, rates.miss, rates.unresolved) == (0.25, 0.25, 0.5)


def test_top1_rates_reject_samples_without_an_intended_target() -> None:
    from bench.stats import top1_rates

    with pytest.raises(ValueError, match="no intended target"):
        top1_rates([_score(None)])


def test_unobserved_samples_stay_in_the_denominator_apart_from_unresolved() -> None:
    from bench.score import SampleScore
    from bench.stats import top1_rates

    unobserved = SampleScore(
        None, False, {}, "unobserved", 0.0, None, None, None, False, False, True
    )
    rates = top1_rates([_score(True), _score(False), _score(None, True), unobserved])
    assert (rates.hit, rates.miss, rates.unresolved, rates.unobserved) == (0.25, 0.25, 0.25, 0.25)


def test_unobserved_check_uses_the_error_rule_on_scheduled_slots() -> None:
    from bench.stats import unobserved_check

    assert unobserved_check(2510, {"spotlight": 120, "raycast": 100}) == "ok"
    assert unobserved_check(2510, {"spotlight": 214, "raycast": 0}) == "inconclusive"
