from collections.abc import Iterator

from bench.vm import VM, SettleResult


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _vm_with_counts(counts: Iterator[str], clock: FakeClock) -> VM:
    def ssh(_cmd: str, _timeout: float) -> str:
        return next(counts)

    return VM("t", "base", ssh_fn=ssh, clock=clock.time, sleep=clock.sleep)


def test_index_settles_when_count_is_stable_for_three_checks() -> None:
    clock = FakeClock()
    vm = _vm_with_counts(iter(["10", "50", "80", "80", "80", "80"]), clock)
    assert vm.wait_index_settled(timeout_s=600) == SettleResult(settled=True, count=80)


def test_index_timeout_returns_unsettled_instead_of_raising() -> None:
    clock = FakeClock()
    growing = (str(n) for n in range(10_000))
    vm = _vm_with_counts(growing, clock)
    result = vm.wait_index_settled(timeout_s=60)
    assert result.settled is False
    assert clock.now <= 70


def test_coverage_marks_unindexed_target_false() -> None:
    def ssh(_cmd: str, _timeout: float) -> str:
        return "/System/Applications/Chess.app\n/System/Cryptexes/App/Safari.app\n"

    clock = FakeClock()
    vm = VM("t", "base", ssh_fn=ssh, clock=clock.time, sleep=clock.sleep)
    coverage = vm.indexed_paths()
    assert "/System/Applications/Chess.app" in coverage
    assert "/System/Applications/Stocks.app" not in coverage
