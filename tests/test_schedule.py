from collections import Counter

from bench.schedule import Slot, schedule

QUERIES = [f"q{i}" for i in range(60)]


def _orders(slots: list[Slot], run: int) -> dict[str, list[str]]:
    orders: dict[str, list[str]] = {}
    for s in slots:
        if s.run == run and s.condition == "ui_restart":
            orders.setdefault(s.query_id, []).append(s.tool)
    return orders


def test_three_tools_take_each_position_equally_often() -> None:
    slots = schedule(QUERIES, ["spotlight", "raycast", "floodlight"], runs=1, seed=42)
    orders = _orders(slots, 0)
    for position in range(3):
        counts = Counter(order[position] for order in orders.values())
        assert max(counts.values()) - min(counts.values()) <= 1


def test_two_tools_alternate_ab_ba() -> None:
    slots = schedule(QUERIES, ["spotlight", "raycast"], runs=1, seed=42)
    firsts = [order[0] for order in _orders(slots, 0).values()]
    assert Counter(firsts) == {"spotlight": 30, "raycast": 30}


def test_restart_and_warm_pair_is_never_split() -> None:
    slots = schedule(QUERIES, ["spotlight", "raycast", "floodlight"], runs=2, seed=42)
    for i, s in enumerate(slots):
        if s.condition == "ui_restart":
            nxt = slots[i + 1]
            assert (nxt.query_id, nxt.tool, nxt.run, nxt.condition) == (
                s.query_id,
                s.tool,
                s.run,
                "warm",
            )


def test_every_query_tool_run_is_scheduled_exactly_once_per_condition() -> None:
    tools = ["spotlight", "raycast", "floodlight"]
    slots = schedule(QUERIES, tools, runs=5, seed=42)
    assert len(slots) == len(QUERIES) * len(tools) * 5 * 2
    assert len(set(slots)) == len(slots)


def test_schedule_is_deterministic_for_a_seed() -> None:
    a = schedule(QUERIES, ["spotlight", "raycast"], runs=2, seed=42)
    assert a == schedule(QUERIES, ["spotlight", "raycast"], runs=2, seed=42)
    assert a != schedule(QUERIES, ["spotlight", "raycast"], runs=2, seed=43)


def test_warm_only_schedule_has_no_ui_restarts_and_same_tool_order() -> None:
    both = schedule(["a", "b", "c"], ["spotlight", "raycast"], runs=2, seed=3)
    warm = schedule(["a", "b", "c"], ["spotlight", "raycast"], runs=2, seed=3, conditions=("warm",))
    assert {s.condition for s in warm} == {"warm"}
    assert warm == [s for s in both if s.condition == "warm"]
