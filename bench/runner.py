"""Runs a schedule inside a VM clone with the Swift probe and reads the samples back."""

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any, Literal

from bench.generate import Query
from bench.model import Kind, Row, Sample, Snapshot, Source
from bench.schedule import Slot

GUEST_SHARE = "/Volumes/My Shared Files/run"


def stage_probe(binary: Path, share_dir: Path) -> Path:
    """Copies the probe under a content-hash name; the VM's shared folder caches replaced files."""
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()[:12]
    share_dir.mkdir(parents=True, exist_ok=True)
    staged = share_dir / f"probe-{digest}"
    shutil.copy2(binary, staged)
    return staged


def write_schedule(
    path: Path, slots: list[Slot], queries: dict[str, Query], window_ms: int
) -> None:
    lines = [
        json.dumps(
            {
                "query_id": s.query_id,
                "text": queries[s.query_id].text,
                "tool": s.tool,
                "run": s.run,
                "condition": s.condition,
                "mode": queries[s.query_id].mode,
                "window_ms": window_ms,
            }
        )
        for s in slots
    ]
    path.write_text("\n".join(lines) + "\n")


def _row(raw: dict[str, Any]) -> Row:
    try:
        kind, source = Kind(raw["kind"]), Source(raw["source"])
    except ValueError as e:
        raise ValueError(f"probe row has unknown kind/source: {raw}") from e
    return Row(
        title=raw["title"],
        kind=kind,
        source=source,
        folder=raw.get("folder"),
        pane_id=raw.get("pane_id"),
        selected=raw.get("selected"),
        category=raw.get("category"),
    )


def parse_results(path: Path, env: Literal["sparse", "busy"]) -> list[Sample]:
    samples: list[Sample] = []
    for line in path.read_text().splitlines():
        raw = json.loads(line)
        samples.append(
            Sample(
                query_id=raw["query_id"],
                tool=raw["tool"],
                env=env,
                run=raw["run"],
                condition=raw["condition"],
                final_key_post_ms=raw["final_key_post_ms"],
                field_shows_ms=raw.get("field_shows_ms"),
                snapshots=[
                    Snapshot(s["t_ms"], tuple(_row(r) for r in s["rows"]), s["field_text"])
                    for s in raw["snapshots"]
                ],
                error=raw.get("error"),
                attempt=raw.get("attempt", 0),
            )
        )
    return samples
