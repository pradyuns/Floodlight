from bench.generate import Query, Target
from bench.model import Kind, Row, Sample, Snapshot, Source
from bench.score import row_matches, score_sample

CALC = Target("app", "Calculator")


def _row(title: str, kind: Kind = Kind.APP, source: Source = Source.LOCAL, **kw: object) -> Row:
    return Row(title=title, kind=kind, source=source, **kw)  # type: ignore[arg-type]


def _query(intended: Target | None = CALC, acceptable: frozenset[Target] | None = None) -> Query:
    acc = acceptable if acceptable is not None else frozenset({CALC})
    return Query("q1", "calculator", "full", "completed", intended, acc, len(acc) > 1, "dev")


def _sample(snaps: list[tuple[int, list[Row]]], final_key: int = 1000) -> Sample:
    return Sample(
        query_id="q1",
        tool="spotlight",
        env="sparse",
        run=0,
        condition="warm",
        final_key_post_ms=final_key,
        field_shows_ms=final_key + 5,
        snapshots=[Snapshot(t, tuple(rows), "calculator") for t, rows in snaps],
        error=None,
        attempt=0,
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


def test_file_row_without_folder_shown_is_not_a_match() -> None:
    target = Target("file", "/Users/bench/Projects/test.py")
    assert not row_matches(_row("test.py", Kind.FILE, folder=None), target)
    assert row_matches(_row("test.py", Kind.FILE, folder="/Users/bench/Projects"), target)


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
    s = _sample([(1500, rows)])
    snap = s.snapshots[0]
    return Sample(
        **{**s.__dict__, "snapshots": [Snapshot(snap.t_ms, snap.rows, snap.field_text, action)]}
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
