import json
from pathlib import Path

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
    "final_key_post_ms": 720,
    "field_shows_ms": 900,
    "snapshots": [
        {
            "t_ms": 900,
            "field_text": "calculator",
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
    assert sample.final_key_post_ms == 720
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
