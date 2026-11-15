import json

from bench.campaign import _stuck_tool
from bench.schedule import Slot


def _lines(tool_errors: list[tuple[str, str | None]]) -> list[str]:
    return [json.dumps({"tool": t, "error": e}) for t, e in tool_errors]


def test_a_tool_failing_every_sample_in_a_block_is_stuck() -> None:
    block = [Slot(f"q{i}", t, 0, "warm") for i in range(6) for t in ("spotlight", "raycast")]
    lines = _lines([("spotlight", "not_ready"), ("raycast", None)] * 6)
    assert _stuck_tool(block, lines) == "spotlight"


def test_scattered_errors_are_not_stuck() -> None:
    block = [Slot(f"q{i}", t, 0, "warm") for i in range(6) for t in ("spotlight", "raycast")]
    lines = _lines([("spotlight", "not_ready"), ("raycast", "field_never_matched")] * 5)
    lines += _lines([("spotlight", None), ("raycast", None)])
    assert _stuck_tool(block, lines) is None


def test_errored_slots_are_requeued_with_their_original_order() -> None:
    from bench.campaign import errored_slots

    block = [Slot(f"q{i}", t, 0, "warm") for i in range(3) for t in ("spotlight", "raycast")]
    lines = [
        json.dumps(
            {
                "query_id": s.query_id,
                "tool": s.tool,
                "run": 0,
                "condition": "warm",
                "error": "not_ready" if (s.query_id, s.tool) == ("q1", "raycast") else None,
            }
        )
        for s in block
    ]
    assert errored_slots(block, lines) == [Slot("q1", "raycast", 0, "warm")]


def test_locked_policy_matches_the_analysis_plan() -> None:
    from bench.hostload import LOCKED_POLICY

    assert (LOCKED_POLICY.interval_s, LOCKED_POLICY.max_load1) == (5, 10.0)
    assert LOCKED_POLICY.max_pressure_level == 1
    assert LOCKED_POLICY.max_swap_pages_per_s == 500
    assert (LOCKED_POLICY.recovery_wait_s, LOCKED_POLICY.max_retries) == (120, 2)


def test_probe_name_must_match_its_full_sha256() -> None:
    import hashlib

    import pytest

    from bench.campaign import probe_digest

    data = b"probe binary bytes"
    full = hashlib.sha256(data).hexdigest()
    assert probe_digest(f"probe-{full[:12]}", data) == full
    with pytest.raises(ValueError, match="does not match"):
        probe_digest("probe-000000000000", data)
