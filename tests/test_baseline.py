from pathlib import Path

from bench.baseline import CAMPAIGNS, baseline_plan
from bench.generate import queries_from_json

REPO = Path(__file__).resolve().parent.parent


def _ids(name: str) -> set[str]:
    return {q.id for q in queries_from_json((REPO / "data" / name).read_text())}


def test_dev_warm_runs_every_dev_query_warm_on_sparse() -> None:
    plan = baseline_plan("dev-warm", REPO / "data")
    assert (plan.env, plan.conditions, plan.runs) == ("sparse", ("warm",), 5)
    assert set(plan.query_ids) == _ids("dev-queries.json")


def test_restart_pairs_are_a_seeded_20_percent_subset_on_sparse() -> None:
    plan = baseline_plan("dev-restart", REPO / "data")
    assert plan.env == "sparse" and plan.conditions == ("ui_restart", "warm")
    assert len(plan.query_ids) == round(0.2 * len(_ids("dev-queries.json")))
    assert plan == baseline_plan("dev-restart", REPO / "data")


def test_busy_is_warm_only_on_a_25_percent_subset() -> None:
    plan = baseline_plan("dev-busy", REPO / "data")
    assert (plan.env, plan.conditions) == ("busy", ("warm",))
    assert len(plan.query_ids) == round(0.25 * len(_ids("dev-queries.json")))


def test_natural_excludes_folder_targets_which_need_planted_clones() -> None:
    plan = baseline_plan("natural", REPO / "data")
    queries = {q.id: q for q in queries_from_json((REPO / "data/natural-queries.json").read_text())}
    assert plan.query_ids and all(queries[i].intended.kind != "folder" for i in plan.query_ids)


def test_every_campaign_uses_both_tools_five_runs_and_the_3s_window() -> None:
    for name in CAMPAIGNS:
        plan = baseline_plan(name, REPO / "data")
        assert plan.tools == ("spotlight", "raycast") and plan.runs == 5
        assert plan.window_ms == 3000


def test_every_campaign_waits_300ms_after_ready_before_typing() -> None:
    for name in CAMPAIGNS:
        assert baseline_plan(name, REPO / "data").pause_ms == 300
