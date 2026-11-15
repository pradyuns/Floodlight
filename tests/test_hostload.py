from bench.hostload import HostSample, Policy, evaluate, make_blocks, parse_vm_stat, should_retry
from bench.schedule import Slot

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                3654.
Pageins:                               9000000.
Pageouts:                                12000.
Swapins:                                7256523.
Swapouts:                              10934754.
"""

POLICY = Policy(
    interval_s=5,
    max_load1=8.0,
    max_pressure_level=2,
    max_swap_pages_per_s=50.0,
    recovery_wait_s=120,
    max_retries=2,
)


def _s(
    t: float, load: float = 1.0, pressure: int = 1, si: int = 0, so: int = 0, **kw: bool
) -> HostSample:
    return HostSample(t, load, pressure, si, so, kw.get("on_ac", True), kw.get("low_power", False))


def test_vm_stat_counters_are_parsed() -> None:
    c = parse_vm_stat(VM_STAT)
    assert (c["swapins"], c["swapouts"], c["pageins"]) == (7256523, 10934754, 9000000)


def test_swap_used_alone_is_not_contention_but_swap_activity_is() -> None:
    steady = [_s(0, si=7_000_000, so=10_000_000), _s(5, si=7_000_000, so=10_000_000)]
    assert evaluate(steady, POLICY) == []
    busy = [_s(0, si=7_000_000, so=10_000_000), _s(5, si=7_000_400, so=10_000_000)]
    assert any("swap" in r for r in evaluate(busy, POLICY))


def test_load_pressure_battery_and_low_power_are_flagged() -> None:
    assert any("load" in r for r in evaluate([_s(0, load=9.5)], POLICY))
    assert any("pressure" in r for r in evaluate([_s(0, pressure=4)], POLICY))
    assert any("battery" in r for r in evaluate([_s(0, on_ac=False)], POLICY))
    assert any("low power" in r for r in evaluate([_s(0, low_power=True)], POLICY))
    assert evaluate([_s(0), _s(5)], POLICY) == []


def test_blocks_never_split_a_query_run_tool_group() -> None:
    slots = [Slot(f"q{i}", t, 0, "warm") for i in range(7) for t in ("spotlight", "raycast")]
    blocks = make_blocks(slots, target_size=5)
    assert [s for b in blocks for s in b] == slots
    for b in blocks:
        ids = [(s.query_id, s.run) for s in b]
        for key in set(ids):
            assert ids.count(key) == 2


def test_flagged_block_is_retried_up_to_the_limit_only() -> None:
    assert should_retry(attempt=0, flagged=True, policy=POLICY)
    assert should_retry(attempt=1, flagged=True, policy=POLICY)
    assert not should_retry(attempt=2, flagged=True, policy=POLICY)
    assert not should_retry(attempt=0, flagged=False, policy=POLICY)
