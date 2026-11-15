"""Monitored host-load policy for timed runs (DECISIONS 2026-11-14): light host use is allowed;
contention is judged from load, memory pressure and swap *activity*. A threshold crossing never
interrupts a sample: the block is kept, flagged and retried under a fixed rule."""

import itertools
import os
import re
import subprocess
import time
from dataclasses import dataclass

from bench.schedule import Slot


@dataclass(frozen=True)
class Policy:
    interval_s: float
    max_load1: float
    max_pressure_level: int  # kern.memorystatus_vm_pressure_level: 1 normal, 2 warn, 4 critical
    max_swap_pages_per_s: float
    recovery_wait_s: float
    max_retries: int
    flag_battery: bool = True  # power source is always recorded; this decides if it flags


# Locked values (docs/analysis-plan.md, "Pilot-derived settings").
LOCKED_POLICY = Policy(
    interval_s=5,
    max_load1=10.0,
    max_pressure_level=1,
    max_swap_pages_per_s=500,
    recovery_wait_s=120,
    max_retries=2,
    flag_battery=False,
)


@dataclass(frozen=True)
class HostSample:
    t: float
    load1: float
    pressure_level: int
    swapins: int
    swapouts: int
    on_ac: bool
    low_power: bool


def parse_vm_stat(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        m = re.match(r"^([A-Za-z ]+):\s+(\d+)\.$", line.strip())
        if m:
            out[m.group(1).lower().replace(" ", "_")] = int(m.group(2))
    return out


def _run(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=True).stdout


def read_host_sample() -> HostSample:
    counters = parse_vm_stat(_run(["vm_stat"]))
    pressure = int(_run(["sysctl", "-n", "kern.memorystatus_vm_pressure_level"]).strip())
    low_power = re.search(r"lowpowermode\s+1", _run(["pmset", "-g"])) is not None
    return HostSample(
        time.monotonic(),
        os.getloadavg()[0],
        pressure,
        counters["swapins"],
        counters["swapouts"],
        "AC Power" in _run(["pmset", "-g", "batt"]),
        low_power,
    )


def evaluate(samples: list[HostSample], policy: Policy) -> list[str]:
    """Reasons the host was contended during these samples; empty means within policy."""
    reasons: list[str] = []
    for s in samples:
        if s.load1 > policy.max_load1:
            reasons.append(f"load {s.load1:.2f} > {policy.max_load1}")
        if s.pressure_level > policy.max_pressure_level:
            reasons.append(f"memory pressure level {s.pressure_level}")
        if policy.flag_battery and not s.on_ac:
            reasons.append("on battery")
        if s.low_power:
            reasons.append("low power mode on")
    for a, b in itertools.pairwise(samples):
        rate = ((b.swapins - a.swapins) + (b.swapouts - a.swapouts)) / max(b.t - a.t, 1e-9)
        if rate > policy.max_swap_pages_per_s:
            reasons.append(f"swap activity {rate:.0f} pages/s")
    return reasons


def make_blocks(slots: list[Slot], target_size: int) -> list[list[Slot]]:
    """Consecutive blocks of about target_size, never splitting one (query, run) tool group."""
    blocks: list[list[Slot]] = []
    current: list[Slot] = []
    for i, slot in enumerate(slots):
        current.append(slot)
        nxt = slots[i + 1] if i + 1 < len(slots) else None
        same_group = nxt is not None and (nxt.query_id, nxt.run) == (slot.query_id, slot.run)
        if len(current) >= target_size and not same_group:
            blocks.append(current)
            current = []
    if current:
        blocks.append(current)
    return blocks


def should_retry(attempt: int, flagged: bool, policy: Policy) -> bool:
    return flagged and attempt < policy.max_retries
