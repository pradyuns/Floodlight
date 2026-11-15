import subprocess
from pathlib import Path

import pytest

from bench.generate import Query, Target
from bench.model import KeyPost, Kind, Row, Sample, Snapshot, Source
from bench.score import Identity, identify, row_matches, score_sample
from bench.truth import GroundTruth, ground_truth_command

CALC = Target("app", "Calculator")


def _row(title: str, kind: Kind = Kind.APP, source: Source = Source.LOCAL, **kw: object) -> Row:
    return Row(title=title, kind=kind, source=source, **kw)  # type: ignore[arg-type]


def _query(intended: Target | None = CALC, acceptable: frozenset[Target] | None = None) -> Query:
    acc = acceptable if acceptable is not None else frozenset({CALC})
    return Query("q1", "calculator", "full", "completed", intended, acc, len(acc) > 1, "dev")


def _sample(snaps: list[tuple[int, list[Row]]], final_key: int = 1000) -> Sample:
    return _timed_sample([(t, t, rows) for t, rows in snaps], final_key)


def _timed_sample(snaps: list[tuple[int, int, list[Row]]], final_key: int = 1000) -> Sample:
    return Sample(
        query_id="q1",
        tool="spotlight",
        env="sparse",
        run=0,
        condition="warm",
        final_key_post_ms=final_key,
        field_shows_ms=final_key + 5,
        snapshots=[Snapshot(a, b, tuple(rows), "calculator") for a, b, rows in snaps],
        error=None,
        attempt=0,
        key_posts=(KeyPost(final_key, final_key),),
    )


def _every_50ms(until: int, rows_at: dict[int, list[Row]]) -> list[tuple[int, list[Row]]]:
    out: list[tuple[int, list[Row]]] = []
    current: list[Row] = []
    for t in range(0, until + 1, 50):
        current = rows_at.get(t, current)
        out.append((t, current))
    return out


def test_wrong_enter_at_250ms_counts_even_if_it_settles_correctly_later() -> None:
    svg = _row("calculator.svg", Kind.FILE, folder="/x")
    snaps = _every_50ms(4000, {0: [svg], 1600: [_row("Calculator"), svg]})
    score = score_sample(_sample(snaps), _query())
    assert score.wrong_enter[250] is True
    assert score.intended_at1 is True
    assert score.t_at1 == 600


def test_checkpoint_without_a_recent_snapshot_is_unobserved() -> None:
    snaps = [(0, [_row("Calculator")]), (1000, [_row("Calculator")]), (4000, [_row("Calculator")])]
    score = score_sample(_sample(snaps), _query())
    assert score.wrong_enter[250] == "unobserved"


def test_web_row_is_skipped_in_local_only_view() -> None:
    web = _row("Calculator", Kind.OTHER, Source.WEB)
    snaps = _every_50ms(4000, {0: [web, _row("Calculator")]})
    assert score_sample(_sample(snaps), _query(), local_only=False).final_observed_rank == 2
    assert score_sample(_sample(snaps), _query(), local_only=True).final_observed_rank == 1


DOCS_A = "/Users/bench/Projects/alpha/docs/guide.md"
DOCS_B = "/Users/bench/Projects/beta/docs/guide.md"
ZK = "/Users/bench/Documents/zk-114/test.py"


def _truth(*entries: tuple[str, str]) -> GroundTruth:
    return GroundTruth.from_find_output("".join(f"{k} {p}\n" for k, p in entries))


def test_full_parent_path_shown_identifies_the_file_without_ground_truth() -> None:
    target = Target("file", ZK)
    assert (
        identify(_row("test.py", Kind.FILE, folder="/Users/bench/Documents/zk-114"), target, None)
        is Identity.MATCH
    )
    assert (
        identify(_row("test.py", Kind.FILE, folder="/elsewhere/zk-114"), target, None)
        is Identity.NO_MATCH
    )


def test_parent_name_shown_matches_when_only_one_such_file_exists() -> None:
    truth = _truth(("f", ZK), ("f", "/Users/bench/Downloads/test.py"))
    target = Target("file", ZK)
    assert row_matches(_row("test.py", Kind.FILE, folder="zk-114"), target, truth)
    assert (
        identify(_row("test.py", Kind.FILE, folder="Documents"), target, truth) is Identity.NO_MATCH
    )


def test_same_name_under_two_parents_with_the_same_folder_name_is_unresolved() -> None:
    truth = _truth(("f", DOCS_A), ("f", DOCS_B))
    row = _row("guide.md", Kind.FILE, folder="docs")
    assert identify(row, Target("file", DOCS_A), truth) is Identity.UNRESOLVED
    assert not row_matches(row, Target("file", DOCS_A), truth)


def test_row_without_location_matches_only_a_name_unique_in_ground_truth() -> None:
    target = Target("folder", "/Users/bench/Documents/abc-101")
    row = _row("abc-101", Kind.FOLDER, folder=None)
    assert (
        identify(row, target, _truth(("d", target.id), ("f", "/Users/bench/abc-101")))
        is Identity.MATCH
    )
    shared = _truth(("d", target.id), ("d", "/Users/bench/Downloads/abc-101"))
    assert identify(row, target, shared) is Identity.UNRESOLVED
    assert identify(_row("abc-102", Kind.FOLDER, folder=None), target, shared) is Identity.NO_MATCH


def test_partial_location_without_ground_truth_is_unresolved() -> None:
    target = Target("file", ZK)
    assert (
        identify(_row("test.py", Kind.FILE, folder="zk-114"), target, None) is Identity.UNRESOLVED
    )
    assert identify(_row("test.py", Kind.FILE, folder=None), target, None) is Identity.UNRESOLVED


def test_ground_truth_missing_the_target_fails_loudly() -> None:
    with pytest.raises(ValueError, match="not in ground truth"):
        identify(
            _row("test.py", Kind.FILE, folder="zk-114"), Target("file", ZK), _truth(("f", DOCS_A))
        )


def test_unresolved_top_row_is_neither_a_hit_nor_a_wrong_enter() -> None:
    target = Target("file", DOCS_A)
    q = Query("q1", "guide.md", "full", "completed", target, frozenset({target}), False, "files")
    snaps = _every_50ms(4000, {0: [_row("guide.md", Kind.FILE, folder="docs", selected=True)]})
    score = score_sample(_sample(snaps), q, truth=_truth(("f", DOCS_A), ("f", DOCS_B)))
    assert score.identity_unresolved is True
    assert score.intended_at1 is None
    assert score.wrong_enter[250] == "unresolved"
    assert score.safe_enter == "unresolved"
    assert score.coverage_miss is False


def test_ground_truth_command_skips_hidden_and_library_folders(tmp_path: Path) -> None:
    for rel in (
        "Documents/x/guide.md",
        ".hidden/guide.md",
        "Library/guide.md",
        "docs/guide.md/keep",
    ):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("x")
    out = subprocess.run(
        [
            "sh",
            "-c",
            ground_truth_command(
                ["guide.md"], roots=(str(tmp_path),), private=(f"{tmp_path}/Library",)
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    truth = GroundTruth.from_find_output(out)
    assert truth.candidates(Kind.FILE, "guide.md") == frozenset(
        {f"{tmp_path}/Documents/x/guide.md"}
    )
    assert truth.candidates(Kind.FOLDER, "guide.md") == frozenset({f"{tmp_path}/docs/guide.md"})


def test_settings_rows_match_by_pane_id_not_title() -> None:
    target = Target("settings_pane", "wifi")
    assert row_matches(_row("Anything", Kind.SETTINGS_PANE, pane_id="wifi"), target)
    assert not row_matches(_row("Wi-Fi", Kind.SETTINGS_PANE, pane_id="bluetooth"), target)


def test_never_appeared_has_no_latency_and_is_a_coverage_miss() -> None:
    snaps = _every_50ms(4000, {0: [_row("Chess")]})
    score = score_sample(_sample(snaps), _query())
    assert score.t_at1 is None
    assert score.t_first_appear is None
    assert score.coverage_miss is True
    assert score.rr10 == 0.0


def test_safe_enter_reads_the_selected_row() -> None:
    rows = [_row("Calendar", selected=False), _row("Calculator", selected=True)]
    score = score_sample(_sample(_every_50ms(4000, {0: rows})), _query())
    assert score.safe_enter == "intended"
    assert score.intended_at1 is False


def test_safe_enter_unreadable_when_selection_is_not_exposed() -> None:
    score = score_sample(_sample(_every_50ms(4000, {0: [_row("Calculator")]})), _query())
    assert score.safe_enter == "unreadable"


def test_ambiguous_query_counts_any_acceptable_app_at_1() -> None:
    cal = Target("app", "Calendar")
    query = _query(acceptable=frozenset({CALC, cal}))
    score = score_sample(_sample(_every_50ms(4000, {0: [_row("Calendar")]})), query)
    assert score.acceptable_at1 is True
    assert score.intended_at1 is False


def _labelled(rows: list[Row], action: str | None) -> Sample:
    s = _sample([(3950, rows)])
    snap = s.snapshots[0]
    return Sample(
        **{
            **s.__dict__,
            "snapshots": [
                Snapshot(snap.read_start_ms, snap.read_end_ms, snap.rows, snap.field_text, action)
            ],
        }
    )


def test_safe_enter_assumes_top_row_when_enter_label_matches_its_type() -> None:
    rows = [_row("Calculator"), _row("Calculator History", Kind.OTHER)]
    score = score_sample(_labelled(rows, "Open Application"), _query())
    assert score.safe_enter == "intended"


def test_safe_enter_flags_highlight_mismatch_when_label_disagrees_with_top_row() -> None:
    rows = [_row("Calculator"), _row("Calculator History", Kind.OTHER)]
    score = score_sample(_labelled(rows, "Open Command"), _query())
    assert score.safe_enter == "highlight_mismatch"


def test_safe_enter_top_row_rule_uses_the_screen_order_not_the_local_only_view() -> None:
    rows = [_row("Google Search", Kind.OTHER, Source.WEB), _row("Calculator")]
    score = score_sample(_labelled(rows, "Open Command"), _query(), local_only=True)
    assert score.safe_enter == "other"


def test_safe_enter_unknown_enter_label_is_unreadable() -> None:
    score = score_sample(_labelled([_row("Calculator")], "Reveal in Finder"), _query())
    assert score.safe_enter == "unreadable"


def test_rows_are_not_credited_before_the_read_that_saw_them_finished() -> None:
    svg = _row("calculator.svg", Kind.FILE, folder="/x")
    snaps = [(t, t, [svg]) for t in range(0, 1200, 50)]
    snaps.append((1200, 1300, [_row("Calculator"), svg]))
    snaps += [(t, t, [_row("Calculator"), svg]) for t in range(1350, 4001, 50)]
    score = score_sample(_timed_sample(snaps), _query())
    assert score.wrong_enter[250] is True
    assert score.wrong_enter[500] is False
    assert score.t_first_appear == 300
    assert score.t_at1 == 300


def test_checkpoint_is_unobserved_when_the_latest_finished_read_started_too_long_ago() -> None:
    snaps = [(1100, 1140, [_row("Calculator")]), (1200, 1300, [_row("Calculator")])]
    score = score_sample(_timed_sample(snaps), _query())
    assert score.wrong_enter[250] == "unobserved"


def test_mismatched_field_reading_never_counts_at_a_checkpoint() -> None:
    good = Snapshot(990, 995, (_row("Calculator"),), "calculator")
    flagged = Snapshot(1050, 1060, (), "alculator", field_mismatch=True)
    final = Snapshot(3950, 3955, (_row("Calculator"),), "calculator")
    flagged_final = Snapshot(3960, 3970, (), "alculator", field_mismatch=True)
    s = _sample([(0, [])])
    sample = Sample(**{**s.__dict__, "snapshots": [good, flagged, final, flagged_final]})
    score = score_sample(sample, _query())
    assert score.wrong_enter[100] == "unobserved"
    assert score.intended_at1 is True


def _snap(
    start: int, end: int, rows: list[Row], field: str = "calculator", **kw: object
) -> Snapshot:
    return Snapshot(start, end, tuple(rows), field, **kw)  # type: ignore[arg-type]


def _with(snaps: list[Snapshot], final_key: int = 1000) -> Sample:
    base = _sample([], final_key)
    return Sample(**{**base.__dict__, "snapshots": snaps})


def test_final_outcome_is_unobserved_without_a_read_started_in_the_last_100ms() -> None:
    score = score_sample(_with([_snap(3000, 3010, [_row("Calculator")])]), _query())
    assert score.final_unobserved is True
    assert score.intended_at1 is None and score.final_observed_rank is None
    assert score.safe_enter == "unobserved" and score.coverage_miss is False


def test_read_spanning_the_cutoff_never_fills_the_gap() -> None:
    score = score_sample(_with([_snap(3950, 4010, [_row("Calculator")])]), _query())
    assert score.final_unobserved is True


def test_unreadable_reads_are_ignored_rather_than_scored_as_empty() -> None:
    snaps = [
        _snap(3920, 3930, [_row("Calculator")]),
        _snap(3950, 3990, [], field="", unreadable="field:ax_error_-25204"),
    ]
    score = score_sample(_with(snaps), _query())
    assert score.final_unobserved is False and score.intended_at1 is True


def test_only_unreadable_reads_near_the_cutoff_leave_the_outcome_unobserved() -> None:
    snaps = [
        _snap(3000, 3010, [_row("Calculator")]),
        _snap(3950, 3990, [], field="", unreadable="deadline"),
    ]
    assert score_sample(_with(snaps), _query()).final_unobserved is True


def test_a_readable_empty_field_at_the_cutoff_is_a_real_miss() -> None:
    score = score_sample(_with([_snap(3950, 3960, [], field="")]), _query())
    assert score.final_unobserved is False and score.intended_at1 is False


def test_unreadable_read_at_a_checkpoint_is_unobserved_not_wrong() -> None:
    snaps = [
        _snap(1080, 1090, [_row("Calculator")]),
        _snap(1095, 1099, [], field="", unreadable="deadline"),
    ]
    snaps += [_snap(3950, 3960, [_row("Calculator")])]
    score = score_sample(_with(snaps), _query())
    assert score.wrong_enter[100] is False
    snaps = [
        _snap(1095, 1099, [], field="", unreadable="deadline"),
        _snap(3950, 3960, [_row("Calculator")]),
    ]
    assert score_sample(_with(snaps), _query()).wrong_enter[100] == "unobserved"


def test_app_rows_match_by_any_name_from_the_apps_own_bundle() -> None:
    print_center = Target("app", "Print Center")
    assert row_matches(_row("Print Centre"), print_center)
    assert row_matches(_row("Playground"), Target("app", "Image Playground"))
    assert not row_matches(_row("Print"), print_center)
    assert not row_matches(_row("Print Centre", Kind.OTHER), print_center)
