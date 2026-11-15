"""Seeded, counterbalanced order of (query, tool, run, condition) samples (spec §6, §13.18)."""

import itertools
import random
from dataclasses import dataclass
from typing import Literal

Condition = Literal["ui_restart", "warm"]


@dataclass(frozen=True)
class Slot:
    query_id: str
    tool: str
    run: int
    condition: Condition


def _tool_orders(tools: list[str], n: int, rng: random.Random) -> list[tuple[str, ...]]:
    """n orderings in which every tool takes each position equally often (±1)."""
    perms = list(itertools.permutations(tools))
    if len(tools) == 2:
        start = rng.randrange(2)
        return [perms[(start + i) % 2] for i in range(n)]
    cycle: list[tuple[str, ...]] = []
    while len(cycle) < n:
        block = perms[:]
        rng.shuffle(block)
        cycle.extend(block)
    return cycle[:n]


def schedule(
    query_ids: list[str],
    tools: list[str],
    runs: int,
    seed: int = 42,
    conditions: tuple[Condition, ...] = ("ui_restart", "warm"),
) -> list[Slot]:
    rng = random.Random(seed)
    slots: list[Slot] = []
    for run in range(runs):
        order = query_ids[:]
        rng.shuffle(order)
        for query_id, tool_order in zip(order, _tool_orders(tools, len(order), rng), strict=True):
            for tool in tool_order:
                slots.extend(Slot(query_id, tool, run, c) for c in conditions)
    return slots
