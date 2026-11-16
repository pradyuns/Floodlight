"""Final held-out campaign (analysis plan, Execution order 4-6): all three tools, preset repeats.

The held-out file is opened only after it matches the published commitment. Nothing here prints
query text or planted names: only counts and the digest."""

import contextlib
import json
import random
import re
import shlex
import time
from collections.abc import Callable
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
GUEST_NAMES = "/Volumes/My Shared Files/run/planted.txt"
URL = "http://192.168.64.1:8765"
LRM = "\u200e"

Sh = Callable[..., str]


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


def _plain(name: str) -> str:
    return name.replace(LRM, "")


def plant_and_restart(
    sh: Sh,
    sudo: Sh,
    io: Path,
    names: tuple[str, ...],
    sleep: Callable[[float], None] = time.sleep,
    index_timeout_s: float = 600,
) -> dict[str, int]:
    """Plant the secret apps, wait until Spotlight has indexed them, then reboot so every launcher
    starts with them present (the established fixture procedure). Names reach the guest only
    through a file in the run share, deleted right after planting."""
    names_file = io / "planted.txt"
    names_file.write_text("".join(n + "\n" for n in names))
    names_file.chmod(0o600)
    try:
        sh(
            f"mkdir -p {GUEST_PLANTER_DIR} && cd {GUEST_PLANTER_DIR} && for f in planted "
            f"make_planted.sh; do curl -sf -o $f {URL}/$f; done && chmod +x planted make_planted.sh"
        )
        out = sudo(plant_command(GUEST_NAMES))
    finally:
        names_file.unlink(missing_ok=True)
    m = re.search(r"planted=(\d+) failed=(\d+)", out)
    if not m or int(m.group(1)) != len(names) or int(m.group(2)):
        raise RuntimeError(f"planting failed: {m.group(0) if m else 'no count'} of {len(names)}")
    waited = 0.0
    while True:
        indexed = sum(
            int(
                sh(
                    f"mdfind -count {shlex.quote(f'kMDItemDisplayName == {json.dumps(_plain(n))}')}"
                ).split()[-1]
            )
            >= 1
            for n in names
        )
        if indexed == len(names):
            break
        if waited >= index_timeout_s:
            raise RuntimeError(f"Spotlight indexed {indexed} of {len(names)} planted apps")
        sleep(15)
        waited += 15
    with contextlib.suppress(RuntimeError):
        sudo("shutdown -r now")
    sleep(60)
    for _ in range(60):
        try:
            if "up" in sh(
                "pgrep -x Raycast >/dev/null && pgrep -x Spotlight >/dev/null "
                "&& pgrep -x Floodlight >/dev/null && echo up",
                20,
            ):
                break
        except Exception:
            pass
        sleep(10)
    else:
        raise RuntimeError("launchers did not come back after the reboot")
    sleep(90)
    return {"planted": int(m.group(1)), "failed": int(m.group(2))}


def ready_check(
    sh: Sh,
    names: tuple[str, ...],
    tools: tuple[str, ...] = FINAL_TOOLS,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, int]:
    """Every tool must list every planted app, as an app with its name, before any query.
    Reports counts only."""
    seen = dict.fromkeys(tools, 0)
    for name in names:
        plain = _plain(name)
        for tool in tools:
            for _ in range(3):
                raw = sh(
                    f"~/probe dump --tool {tool} --query {shlex.quote(plain.lower())} 2>&1; "
                    'echo "exit=$?"'
                )
                body, _, status = raw.strip().rpartition("\n")
                if status == "exit=0":
                    rows = json.loads(body)
                    seen[tool] += any(
                        r.get("kind") == "app" and _plain(r.get("title", "")) == plain for r in rows
                    )
                    break
                sleep(10)
    if any(c < len(names) for c in seen.values()):
        raise RuntimeError(f"not every planted app is listed: {seen} of {len(names)}")
    return seen
