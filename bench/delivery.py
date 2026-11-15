"""Input-delivery check (analysis plan item 28): how often a launcher shows the typed text, by
the pause between "ready" and the first key. Unscored; uses first attempts only."""

import random
from collections import Counter
from typing import Any, Literal

from bench.schedule import Slot

PAUSES_MS = (0, 150, 300, 500)
TOOLS = ("spotlight", "raycast")
# Williams square for four levels: each pause takes each position once per four rounds, and
# each pause follows each other pause once, so slow drift over the run can't favour one pause.
_WILLIAMS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))

Outcome = Literal["delivered", "dropped", "not_ready", "unreadable", "timeout", "other_error"]


def classify(rec: dict[str, Any]) -> Outcome:
    """A drop is a readable field showing text other than what was typed; unverified input is
    never counted as delivered."""
    snaps = rec["snapshots"]
    if any(s["field_mismatch"] and s.get("unreadable") is None for s in snaps):
        return "dropped"
    if rec.get("error") == "not_ready":
        return "not_ready"
    if rec.get("field_shows_ms") is not None:
        return "delivered"
    if rec.get("error") not in (None, "field_never_matched", "ax_read_failed"):
        return "other_error"
    if all(s.get("unreadable") is not None for s in snaps):
        return "unreadable"
    return "timeout"


def delivery_plan(
    query_ids: list[str],
    per_tool_per_pause: int,
    block_size: int,
    seed: int,
    pauses: tuple[int, ...] = PAUSES_MS,
) -> tuple[list[Slot], list[int]]:
    """Slots in run order and the pause for each block. Each block alternates the tools; blocks
    alternate which tool goes first; pause order follows the Williams square."""
    per_block = block_size // len(TOOLS)
    if block_size % len(TOOLS) or per_tool_per_pause % per_block:
        raise ValueError("block size must split evenly between tools and into the trial count")
    blocks_per_pause = per_tool_per_pause // per_block
    if len(pauses) == 1:
        square: tuple[tuple[int, ...], ...] = ((0,),)
    elif len(pauses) == len(_WILLIAMS):
        square = _WILLIAMS
    else:
        raise ValueError(f"need 1 or {len(_WILLIAMS)} pauses, got {len(pauses)}")
    if blocks_per_pause % len(square):
        raise ValueError(f"blocks per pause must be a multiple of {len(square)}")
    rng = random.Random(seed)
    pool = sorted(query_ids)
    block_pauses = [pauses[i] for r in range(blocks_per_pause) for i in square[r % len(square)]]
    slots: list[Slot] = []
    for b in range(len(block_pauses)):
        order = TOOLS if b % 2 == 0 else TOOLS[::-1]
        for k in range(block_size):
            slots.append(Slot(rng.choice(pool), order[k % 2], len(slots), "warm"))
    return slots, block_pauses


def summarize(
    raw: list[dict[str, Any]], block_pause: dict[int, int]
) -> dict[tuple[str, int], Counter[str]]:
    """First-attempt outcome counts per (tool, pause)."""
    out: dict[tuple[str, int], Counter[str]] = {}
    for rec in raw:
        if rec["attempt"] != 0:
            continue
        key = (rec["tool"], block_pause[rec["block"]])
        out.setdefault(key, Counter())[classify(rec)] += 1
    return out
