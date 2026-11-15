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
