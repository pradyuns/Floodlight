import json
from pathlib import Path

import pytest

from bench.generate import Query, Target
from bench.model import Kind, Source
from bench.runner import parse_results, stage_probe, write_schedule
from bench.schedule import Slot

CALC = Target("app", "Calculator")
QUERY = Query(
    "dev:full:calculator", "calculator", "full", "completed", CALC, frozenset({CALC}), False, "dev"
)

PROBE_LINE = {
    "query_id": "dev:full:calculator",
    "tool": "spotlight",
    "run": 0,
    "condition": "warm",
    "mode": "completed",
    "final_key_post_ms": 723,
    "max_key_lateness_ms": 3,
    "key_posts": [
        {"planned_ms": i * 80, "actual_ms": i * 80 + (3 if i == 9 else 0)} for i in range(10)
    ],
    "field_shows_ms": 900,
    "snapshots": [
        {
            "read_start_ms": 860,
            "read_end_ms": 900,
            "field_text": "calculator",
            "field_mismatch": False,
            "rows": [
                {
                    "title": "Calculator",
                    "kind": "app",
                    "source": "local",
                    "selected": True,
                    "category": "com.apple.applications",
                },
                {
                    "title": "Online Calculator",
                    "kind": "other",
                    "source": "web",
                    "selected": False,
                    "category": "com.apple.parsec.web_index",
                },
            ],
        }
    ],
    "error": None,
    "attempt": 0,
}


def test_schedule_file_has_one_line_per_slot_with_query_text(tmp_path: Path) -> None:
    slots = [
        Slot("dev:full:calculator", "spotlight", 0, "ui_restart"),
        Slot("dev:full:calculator", "spotlight", 0, "warm"),
    ]
    path = tmp_path / "schedule.jsonl"
    write_schedule(path, slots, {QUERY.id: QUERY}, window_ms=3000)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert [line["condition"] for line in lines] == ["ui_restart", "warm"]
    assert lines[0]["text"] == "calculator"
    assert lines[0]["window_ms"] == 3000
    assert lines[0]["mode"] == "completed"


def test_parse_results_builds_samples_with_typed_rows(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(PROBE_LINE) + "\n")
    (sample,) = parse_results(path, env="sparse")
    assert sample.env == "sparse"
    assert sample.final_key_post_ms == 723
    rows = sample.snapshots[0].rows
    assert rows[0].kind == Kind.APP and rows[0].selected is True
    assert rows[1].source == Source.WEB
    assert rows[1].category == "com.apple.parsec.web_index"


def test_parse_results_rejects_unknown_row_kind(tmp_path: Path) -> None:
    bad = json.loads(json.dumps(PROBE_LINE))
    bad["snapshots"][0]["rows"][0]["kind"] = "gadget"
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(bad) + "\n")
    try:
        parse_results(path, env="sparse")
    except ValueError as e:
        assert "gadget" in str(e)
    else:
        raise AssertionError("unknown kind must fail loudly")


def test_stage_probe_names_binary_by_content_hash(tmp_path: Path) -> None:
    binary = tmp_path / "probe"
    binary.write_bytes(b"probe-v1")
    staged = stage_probe(binary, tmp_path / "share")
    assert staged.name.startswith("probe-") and len(staged.name) == len("probe-") + 12
    assert staged.read_bytes() == b"probe-v1"
    binary.write_bytes(b"probe-v2")
    assert stage_probe(binary, tmp_path / "share").name != staged.name


def test_parse_results_keeps_the_enter_action_label(tmp_path: Path) -> None:
    line = json.loads(json.dumps(PROBE_LINE))
    line["snapshots"][0]["primary_action"] = "Open Application"
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(line) + "\n")
    (sample,) = parse_results(path, env="sparse")
    assert sample.snapshots[0].primary_action == "Open Application"


def test_parse_results_keeps_read_and_key_timing(tmp_path: Path) -> None:
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(PROBE_LINE) + "\n")
    (sample,) = parse_results(path, env="sparse")
    snap = sample.snapshots[0]
    assert (snap.read_start_ms, snap.read_end_ms) == (860, 900)
    assert sample.key_posts[-1].planned_ms == 720
    assert sample.key_posts[-1].actual_ms == 723
    assert sample.max_key_lateness_ms == 3


def test_parse_results_rejects_output_from_a_probe_without_read_timing(tmp_path: Path) -> None:
    old = json.loads(json.dumps(PROBE_LINE))
    snap = old["snapshots"][0]
    snap["t_ms"] = snap.pop("read_start_ms")
    del snap["read_end_ms"]
    del old["key_posts"]
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(old) + "\n")
    with pytest.raises(ValueError, match=r"read_start_ms.*re-run"):
        parse_results(path, env="sparse")


@pytest.mark.parametrize(
    ("field", "value"), [("final_key_post_ms", 720), ("max_key_lateness_ms", 0)]
)
def test_parse_results_rejects_timing_that_contradicts_the_key_posts(
    tmp_path: Path, field: str, value: int
) -> None:
    bad = json.loads(json.dumps(PROBE_LINE))
    bad[field] = value
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(bad) + "\n")
    with pytest.raises(ValueError, match=field):
        parse_results(path, env="sparse")


def test_parse_results_keeps_flagged_mismatched_field_readings(tmp_path: Path) -> None:
    line = json.loads(json.dumps(PROBE_LINE))
    line["snapshots"].append(
        {**line["snapshots"][0], "rows": [], "field_text": "alculator", "field_mismatch": True}
    )
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(line) + "\n")
    (sample,) = parse_results(path, env="sparse")
    assert [s.field_mismatch for s in sample.snapshots] == [False, True]


def test_parse_results_keeps_unreadable_reads_apart_from_empty_fields(tmp_path: Path) -> None:
    line = json.loads(json.dumps(PROBE_LINE))
    blank = {**line["snapshots"][0], "rows": [], "field_text": ""}
    line["snapshots"] += [blank, {**blank, "unreadable": "field:ax_error_-25204"}]
    path = tmp_path / "samples.jsonl"
    path.write_text(json.dumps(line) + "\n")
    (sample,) = parse_results(path, env="sparse")
    assert [s.unreadable for s in sample.snapshots] == [None, None, "field:ax_error_-25204"]
