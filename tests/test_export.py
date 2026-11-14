from bench.export import PUBLIC_FIELDS, export_public
from bench.generate import Query, Target
from bench.model import KeyPost, Kind, Row, Sample, Snapshot, Source
from bench.report import Comparison, render_report
from bench.score import score_sample

CALC = Target("app", "Calculator")
QUERY = Query(
    "dev:full:calculator", "calculator", "full", "completed", CALC, frozenset({CALC}), False, "dev"
)


def _sample() -> Sample:
    row = Row("Calculator", Kind.APP, Source.LOCAL, None, None, None)
    snaps = [Snapshot(t, t, (row,), "calculator") for t in range(0, 4001, 50)]
    return Sample(
        "dev:full:calculator",
        "spotlight",
        "sparse",
        0,
        "warm",
        1000,
        1005,
        snaps,
        None,
        0,
        (KeyPost(1000, 1000),),
    )


def test_export_contains_only_whitelisted_fields_and_no_titles() -> None:
    sample = _sample()
    rows = export_public([(sample, QUERY, score_sample(sample, QUERY))])
    assert rows
    for row in rows:
        assert set(row) <= PUBLIC_FIELDS
        assert "title" not in row
        assert "Calculator" not in str(row.values())


def test_report_leads_with_verdict_and_always_has_losses_section() -> None:
    primary = Comparison("Floodlight - Spotlight, Intended@1", 8.0, 6.0, 11.0)
    text = render_report(primary, secondary=[], losses=[], failure_types={})
    first_line = text.splitlines()[0]
    assert "better" in first_line.lower()
    assert "## Where Floodlight loses" in text
    assert "None found" in text


def test_export_reports_whether_identity_was_unresolved() -> None:
    sample = _sample()
    (row,) = export_public([(sample, QUERY, score_sample(sample, QUERY))])
    assert row["identity_unresolved"] is False
