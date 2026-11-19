import json
from pathlib import Path

import pytest

from scripts.export_final import export_part
from scripts.verify_public import primary_and_timing
from tests.test_final_analysis import QUERIES, _all_hits, _part, _rec


def test_recomputes_primary_and_matched_timing_from_exported_samples(tmp_path: Path) -> None:
    raw = [
        *_all_hits({("h:a3", "spotlight", r) for r in range(5)}),
        *(_rec("h:a3", "spotlight", r, "Search the Web") for r in range(5)),
    ]
    part = _part(tmp_path, raw, set())
    (part / "meta.json").write_text(json.dumps({"campaign": "final-warm", "env": "sparse"}))
    export_part(part, QUERIES, tmp_path / "out")
    samples = [json.loads(x) for x in (tmp_path / "out/samples.jsonl").read_text().splitlines()]

    out = primary_and_timing(samples, QUERIES)

    # Stratum b: Alpha 2 of 3 queries for Spotlight, Beta 1 of 1; Gamma is stratum a (excluded).
    assert out["spotlight"]["hits"] == 15 and out["spotlight"]["n"] == 20
    assert out["spotlight"]["app_weighted"] == pytest.approx(100 * (2 / 3 + 1) / 2)
    assert out["floodlight_minus_spotlight"]["diff"] == pytest.approx(100 * (1 / 3) / 2)
    # h:a3 is missed by Spotlight, so only the other 3 stratum-b queries are matched.
    assert out["matched_queries"] == 3
    assert out["floodlight"]["t_at1_p50"] == 2950


def _warm_samples(tmp_path: Path) -> list[dict]:  # type: ignore[type-arg]
    part = _part(tmp_path, _all_hits(), set())
    (part / "meta.json").write_text(json.dumps({"campaign": "final-warm", "env": "sparse"}))
    export_part(part, QUERIES, tmp_path / "out")
    return [json.loads(x) for x in (tmp_path / "out/samples.jsonl").read_text().splitlines()]


def test_rejects_a_missing_primary_sample(tmp_path: Path) -> None:
    samples = _warm_samples(tmp_path)
    samples = [s for s in samples if not (s["query_id"] == "h:a3" and s["tool"] == "spotlight")]
    with pytest.raises(ValueError, match="missing"):
        primary_and_timing(samples, QUERIES)


def test_rejects_a_duplicate_primary_sample(tmp_path: Path) -> None:
    samples = _warm_samples(tmp_path)
    with pytest.raises(ValueError, match="duplicate"):
        primary_and_timing([*samples, samples[0]], QUERIES)
