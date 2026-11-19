import json
from pathlib import Path

import pytest

from scripts.export_final import export_part
from tests.test_final_analysis import QUERIES, _all_hits, _part, _rec


def _files(out: Path) -> str:
    return "".join(p.read_text() for p in sorted(out.iterdir()))


def test_export_has_outcomes_but_no_titles_paths_or_host_readings(tmp_path: Path) -> None:
    raw = [*_all_hits({("h:a3", "spotlight", 0)}), _rec("h:a3", "spotlight", 0, "Search the Web")]
    part = _part(tmp_path, raw, set())
    blocks = [json.loads(x) for x in (part / "blocks.jsonl").read_text().splitlines()]
    (part / "blocks.jsonl").write_text(
        "".join(
            json.dumps({**b, "host": [{"load1": 3.2}], "guest_load_before": "x"}) + "\n"
            for b in blocks
        )
    )
    (part / "meta.json").write_text(
        json.dumps({"campaign": "final-warm", "env": "sparse", "share": "/Users/someone/x"})
    )
    counts = export_part(part, QUERIES, tmp_path / "out")

    text = _files(tmp_path / "out")
    for private in ("Search the Web", "Alpha Desk", "/Users", "load1", "guest_load"):
        assert private not in text
    samples = [json.loads(x) for x in (tmp_path / "out/samples.jsonl").read_text().splitlines()]
    assert counts["samples.jsonl"] == len(QUERIES) * 3 * 5
    miss = [
        s for s in samples if s["query_id"] == "h:a3" and s["tool"] == "spotlight" and s["run"] == 0
    ]
    assert miss[0]["intended_at1"] is False and miss[0]["final_observed_rank"] is None


def test_stopped_part_exports_attempt_outcomes_without_scored_samples(tmp_path: Path) -> None:
    raw = [
        _rec("h:a1", "raycast", 0, "Alpha Desk"),
        {
            **_rec("h:a2", "raycast", 0, "Alpha Desk"),
            "error": "not_ready",
            "snapshots": [],
            "field_shows_ms": None,
            "prep_ms": 10012,
            "failed_rechecks": 3,
        },
    ]
    part = _part(tmp_path, raw, set())
    (part / "meta.json").write_text(json.dumps({"campaign": "final-restart", "env": "sparse"}))
    (part / "stopped.txt").write_text("stop rule after block 0: raycast quarter 1\n")
    export_part(part, QUERIES, tmp_path / "out")

    assert not (tmp_path / "out/samples.jsonl").exists()
    attempts = [json.loads(x) for x in (tmp_path / "out/attempts.jsonl").read_text().splitlines()]
    assert [(a["outcome"], a["prep_ms"]) for a in attempts] == [
        ("delivered", None),
        ("not_ready", 10012),
    ]
    assert json.loads((tmp_path / "out/meta.json").read_text())["stopped"].startswith("stop rule")


def test_refuses_to_export_over_an_existing_directory(tmp_path: Path) -> None:
    part = _part(tmp_path, _all_hits(), set())
    (part / "meta.json").write_text(json.dumps({"campaign": "final-warm", "env": "sparse"}))
    (tmp_path / "out").mkdir()
    with pytest.raises(FileExistsError):
        export_part(part, QUERIES, tmp_path / "out")
