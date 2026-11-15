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


MAX_QUARTER_RATE = 0.01
MAX_QUARTER_CLIMB = 0.01
UNVERIFIED = frozenset({"not_ready", "unreadable", "timeout", "other_error"})


def quarter_gate(slots: list[Slot], raw: list[dict[str, Any]]) -> str | None:
    """Stop rule for a scored run (analysis plan item 28). Each tool's scheduled slots are split
    into quarters in run order; once a quarter's slots have all been reached, its first attempts
    must show ≤ 1% dropped and ≤ 1% unverified (a missing first attempt counts as unverified),
    and its drop rate may not exceed quarter 1's by more than 1 point. Returns the first
    breach, or None."""
    first = {
        (r["query_id"], r["tool"], r["run"], r["condition"]): classify(r)
        for r in raw
        if r["attempt"] == 0
    }
    for tool in sorted({s.tool for s in slots}):
        mine = [(s.query_id, s.tool, s.run, s.condition) for s in slots if s.tool == tool]
        reached = max((i for i, k in enumerate(mine) if k in first), default=-1)
        q1_drop: float | None = None
        for q in range(4):
            part = mine[q * len(mine) // 4 : (q + 1) * len(mine) // 4]
            if not part or reached < q * len(mine) // 4 + len(part) - 1:
                break
            outcomes = [first.get(k, "other_error") for k in part]
            drop = outcomes.count("dropped") / len(part)
            unverified = sum(o in UNVERIFIED for o in outcomes) / len(part)
            q1_drop = drop if q1_drop is None else q1_drop
            if drop > MAX_QUARTER_RATE:
                return f"{tool} quarter {q + 1}: dropped {100 * drop:.1f}%"
            if unverified > MAX_QUARTER_RATE:
                return f"{tool} quarter {q + 1}: unverified {100 * unverified:.1f}%"
            if drop - q1_drop > MAX_QUARTER_CLIMB:
                return f"{tool} quarter {q + 1}: dropped {100 * (drop - q1_drop):.1f} pts above Q1"
    return None
