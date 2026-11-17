import json

import pytest

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


def test_block_command_passes_the_block_pause_only_when_set() -> None:
    from bench.campaign import probe_command

    assert "--settle-ms" not in probe_command("/io", "s.jsonl", "r.jsonl", None)
    assert "--settle-ms 300 " in probe_command("/io", "s.jsonl", "r.jsonl", 300)


def test_block_pauses_must_match_the_blocks() -> None:
    from bench.campaign import check_block_pauses
    from bench.schedule import Slot

    blocks = [[Slot("q", "spotlight", 0, "warm")], [Slot("q", "raycast", 1, "warm")]]
    check_block_pauses(blocks, [0, 150])
    with pytest.raises(ValueError, match="2 blocks but 3 pauses"):
        check_block_pauses(blocks, [0, 150, 300])


def test_locked_policy_records_battery_but_does_not_flag_it() -> None:
    from bench.hostload import LOCKED_POLICY, HostSample, evaluate

    on_battery = HostSample(0.0, 1.0, 1, 0, 0, on_ac=False, low_power=False)
    low_power = HostSample(0.0, 1.0, 1, 0, 0, on_ac=False, low_power=True)
    assert evaluate([on_battery], LOCKED_POLICY) == []
    assert any("low power" in r for r in evaluate([low_power], LOCKED_POLICY))


def test_disk_guard_stops_below_5_gb_free_on_host_or_guest() -> None:
    from bench.campaign import disk_guard

    gb = 1024**3
    df = "Filesystem 1024-blocks Used Available Capacity Mounted on\n/dev/disk3s1s1 1 1 {} 1% /\n"
    plenty = df.format(20 * gb // 1024)
    assert disk_guard(14 * gb, plenty) is None
    assert disk_guard(4 * gb, plenty) == "host 4.0 GB free (< 5 GB)"
    assert disk_guard(14 * gb, df.format(3 * gb // 1024)) == "guest 3.0 GB free (< 5 GB)"
