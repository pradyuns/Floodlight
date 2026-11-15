"""Baseline campaigns (analysis plan, "Baseline order"): Spotlight vs Raycast, 5 runs each,
fixed seeds so the published checkout reproduces exactly which samples run."""

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from bench.generate import Query, queries_from_json
from bench.schedule import Condition

SNAPSHOTS = {"sparse": "bench-ready-2026-11-14b", "busy": "bench-busy-2026-11-14b"}
TOOLS = ("spotlight", "raycast")
RUNS = 5
WINDOW_MS = 3000
SCHEDULE_SEED = 42
SUBSET_SEED = 2026
# Pause between "ready" and the first key, the same for every tool: chosen by the unscored
# delivery calibration of 2026-11-15 (analysis plan item 28).
PAUSE_MS = 300
CAMPAIGNS = ("dev-warm", "dev-restart", "natural", "dev-busy")


@dataclass(frozen=True)
class Plan:
    name: str
    env: Literal["sparse", "busy"]
    query_file: str
    query_ids: tuple[str, ...]
    conditions: tuple[Condition, ...]
    tools: tuple[str, ...] = TOOLS
    runs: int = RUNS
    window_ms: int = WINDOW_MS
    schedule_seed: int = SCHEDULE_SEED
    pause_ms: int = PAUSE_MS


def _load(data_dir: Path, name: str) -> list[Query]:
    return queries_from_json((data_dir / name).read_text())


def _subset(ids: list[str], share: float, tag: str) -> tuple[str, ...]:
    pool = sorted(ids)
    return tuple(
        sorted(random.Random(f"{SUBSET_SEED}:{tag}").sample(pool, round(share * len(pool))))
    )


def baseline_plan(name: str, data_dir: Path) -> Plan:
    dev = [q.id for q in _load(data_dir, "dev-queries.json")]
    if name == "dev-warm":
        return Plan(name, "sparse", "dev-queries.json", tuple(sorted(dev)), ("warm",))
    if name == "dev-restart":
        return Plan(
            name, "sparse", "dev-queries.json", _subset(dev, 0.2, name), ("ui_restart", "warm")
        )
    if name == "dev-busy":
        return Plan(name, "busy", "dev-queries.json", _subset(dev, 0.25, name), ("warm",))
    if name == "natural":
        natural = _load(data_dir, "natural-queries.json")
        ids = sorted(q.id for q in natural if q.intended and q.intended.kind != "folder")
        return Plan(name, "sparse", "natural-queries.json", tuple(ids), ("warm",))
    raise ValueError(f"unknown campaign {name!r}; expected one of {CAMPAIGNS}")
