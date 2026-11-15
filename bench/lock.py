"""LOCK.txt: sha256 of everything that affects queries, answers, scoring and analysis (spec §9).
The runner refuses to run when any locked file differs from its recorded hash."""

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

LOCK_FILE = "LOCK.txt"
LOCKED_GLOBS = (
    "data/*.json",
    "bench/generate.py",
    "bench/normalize.py",
    "bench/score.py",
    "bench/stats.py",
    "bench/schedule.py",
    "bench/truth.py",
    "bench/names.py",
    "bench/heldout.py",
    "bench/inventory.py",
    "bench/hostload.py",
    "bench/campaign.py",
    "bench/runner.py",
    "corpus/*.py",
    "fixtures/plan.py",
    "fixtures/make_files.py",
    "docs/analysis-plan.md",
    "pyproject.toml",
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class LockMismatch(Exception):
    pass


def locked_paths(root: Path) -> list[Path]:
    paths = {p for g in LOCKED_GLOBS for p in root.glob(g) if p.is_file()}
    return sorted(p for p in paths if ".local." not in p.name)


def _entries(files: Iterable[Path], root: Path) -> list[str]:
    return sorted(
        f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {f.relative_to(root).as_posix()}"
        for f in files
    )


def compute_lock(files: Iterable[Path], root: Path) -> str:
    return "\n".join(_entries(files, root)) + "\n"


def write_lock(files: Iterable[Path], root: Path, commitment: str) -> Path:
    if not _DIGEST.match(commitment):
        raise ValueError("held-out commitment must be 64 hex characters")
    files = list(files)
    for f in files:
        if f.name == "analysis-plan.md" and "TBD" in f.read_text():
            raise ValueError("analysis plan still has TBD settings; fill them from the pilot first")
    out = root / LOCK_FILE
    out.write_text(compute_lock(files, root) + f"heldout_commitment {commitment}\n")
    return out


def verify_lock(root: Path) -> None:
    lines = (root / LOCK_FILE).read_text().splitlines()
    problems: list[str] = []
    for line in lines:
        if line.startswith("heldout_commitment "):
            continue
        digest, rel = line.split("  ", 1)
        path = root / rel
        if not path.is_file():
            problems.append(f"missing: {rel}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            problems.append(f"changed: {rel}")
    if problems:
        raise LockMismatch("locked files differ from LOCK.txt: " + ", ".join(problems))
