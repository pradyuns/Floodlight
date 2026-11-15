from collections import Counter

from bench.delivery import PAUSES_MS, classify, delivery_plan, summarize

IDS = [f"dev:full:q{i}" for i in range(40)]


def _rec(error=None, snaps=(), field_shows=None, tool="raycast", block=0, attempt=0):  # type: ignore[no-untyped-def]
    return {
        "tool": tool,
        "block": block,
        "attempt": attempt,
        "error": error,
        "field_shows_ms": field_shows,
        "snapshots": [{"field_text": t, "field_mismatch": m, "unreadable": u} for t, m, u in snaps],
    }


def test_classify_names_each_first_try_outcome() -> None:
    assert classify(_rec(field_shows=300, snaps=[("calc", False, None)])) == "delivered"
    assert classify(_rec(error="field_never_matched", snaps=[("alc", True, None)])) == "dropped"
    assert classify(_rec(error="not_ready")) == "not_ready"
    assert classify(_rec(error="ax_read_failed", snaps=[("", False, "deadline")])) == "unreadable"
    assert classify(_rec(error="field_never_matched", snaps=[("ca", False, None)])) == "timeout"
    assert classify(_rec(error="screen_locked")) == "other_error"


def test_a_drop_counts_even_when_the_field_later_shows_the_full_text() -> None:
    rec = _rec(field_shows=500, snaps=[("alc", True, None), ("calc", False, None)])
    assert classify(rec) == "dropped"


def test_plan_gives_each_tool_the_same_trials_at_every_pause() -> None:
    slots, pauses = delivery_plan(IDS, per_tool_per_pause=40, block_size=20, seed=7)
    by = Counter((s.tool, pauses[i // 20]) for i, s in enumerate(slots))
    assert set(by.values()) == {40} and len(by) == 2 * len(PAUSES_MS)
    assert len({(s.query_id, s.tool, s.run, s.condition) for s in slots}) == len(slots)


def test_plan_counterbalances_pause_order_and_tool_order() -> None:
    slots, pauses = delivery_plan(IDS, per_tool_per_pause=80, block_size=20, seed=7)
    rounds = [pauses[i : i + 4] for i in range(0, len(pauses), 4)]
    assert all(sorted(r) == sorted(PAUSES_MS) for r in rounds)
    for p in PAUSES_MS:
        assert set(Counter(r.index(p) for r in rounds).values()) == {len(rounds) // 4}
    firsts = Counter(slots[i].tool for i in range(0, len(slots), 20))
    assert firsts["spotlight"] == firsts["raycast"]
    block = slots[:20]
    assert all(block[i].tool != block[i + 1].tool for i in range(19))


def test_summary_uses_first_attempts_and_keeps_every_outcome_visible() -> None:
    raw = [
        _rec(field_shows=1, snaps=[("a", False, None)], block=0),
        _rec(error="not_ready", block=0),
        _rec(field_shows=1, snaps=[("a", False, None)], block=0, attempt=1),
        _rec(error="field_never_matched", snaps=[("x", True, None)], block=1),
    ]
    out = summarize(raw, block_pause={0: 0, 1: 150})
    assert out[("raycast", 0)] == Counter({"delivered": 1, "not_ready": 1})
    assert out[("raycast", 150)] == Counter({"dropped": 1})


def test_endurance_plan_uses_one_pause_for_every_block() -> None:
    slots, pauses = delivery_plan(IDS, per_tool_per_pause=30, block_size=20, seed=7, pauses=(150,))
    assert pauses == [150, 150, 150] and len(slots) == 60
