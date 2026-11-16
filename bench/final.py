"""Final held-out campaign (analysis plan, Execution order 4-6): all three tools, preset repeats.

The held-out file is opened only after it matches the published commitment. Nothing here prints
query text or planted names: only counts and the digest."""

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from bench.baseline import PAUSE_MS, RUNS, SCHEDULE_SEED, SUBSET_SEED, WINDOW_MS, Plan
from bench.generate import Query, queries_from_json
from bench.heldout import verify_commitment
from bench.schedule import Condition

FINAL_TOOLS = ("spotlight", "raycast", "floodlight")
PARTS = ("final-warm", "final-restart", "final-busy")
SUBSET_SHARE = 0.25
GUEST_PLANTER_DIR = "/private/tmp/fx"


@dataclass(frozen=True)
class Heldout:
    queries: dict[str, Query]
    planted_names: tuple[str, ...]

    def summary(self) -> dict[str, Any]:
        strata: dict[str, int] = {}
        for q in self.queries.values():
            strata[q.stratum or "?"] = strata.get(q.stratum or "?", 0) + 1
        return {"queries": len(self.queries), "strata": strata, "planted": len(self.planted_names)}


def load_heldout(file: Path, nonce: Path, digest: str) -> Heldout:
    data = file.read_bytes()
    if not verify_commitment(digest, nonce.read_bytes(), data):
        raise SystemExit("refusing: held-out file and nonce don't match the published commitment")
    raw = json.loads(data)
    rows = raw["strata"]["a"] + raw["strata"]["b"]
    queries = {q.id: q for q in queries_from_json(json.dumps(rows))}
    return Heldout(queries, tuple(raw["planted_names"]))


def _subset(ids: list[str], part: str) -> list[str]:
    """Seeded by the part name, so each part's subset is fixed before any result exists."""
    return sorted(
        random.Random(f"{SUBSET_SEED}:{part}").sample(ids, round(SUBSET_SHARE * len(ids)))
    )


def final_plan(part: str, held: Heldout) -> Plan:
    ids = sorted(held.queries)
    env: Literal["sparse", "busy"]
    conditions: tuple[Condition, ...]
    if part == "final-warm":
        env, conditions = "sparse", ("warm",)
    elif part == "final-restart":
        ids = _subset(ids, part)
        env, conditions = "sparse", ("ui_restart", "warm")
    elif part == "final-busy":
        ids = _subset(ids, part)
        env, conditions = "busy", ("warm",)
    else:
        raise ValueError(f"unknown part {part!r}; expected one of {PARTS}")
    return Plan(
        part,
        env,
        "heldout",
        tuple(ids),
        conditions,
        tools=FINAL_TOOLS,
        runs=RUNS,
        window_ms=WINDOW_MS,
        schedule_seed=SCHEDULE_SEED,
        pause_ms=PAUSE_MS,
    )


def plant_command(names_path: str) -> str:
    """Guest command that plants one app per name in the file; the planter prints counts only."""
    return f"cd {GUEST_PLANTER_DIR} && ./make_planted.sh ./planted /Applications < '{names_path}'"
