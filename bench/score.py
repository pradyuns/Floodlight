"""Scores one observed sample against its query (spec §5, §7, §13)."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from bench.generate import Query, Target
from bench.model import Kind, Row, Sample, Snapshot, Source
from bench.normalize import normalize

CHECKPOINTS_MS = (100, 250, 500, 1000)
WINDOW_MS = 3000
MAX_SNAPSHOT_AGE_MS = 100

Observed = bool | Literal["unobserved"]
SafeEnter = Literal["intended", "other", "none", "unreadable", "highlight_mismatch"]

# Launchers that don't expose their highlighted row (Raycast 2.12) are read with the documented
# rule "Enter opens the top row", checked against the type named by the Enter button's label.
ENTER_LABEL_KINDS: dict[str, frozenset[Kind]] = {
    "Open Application": frozenset({Kind.APP}),
    "Open System Setting": frozenset({Kind.SETTINGS_PANE}),
    "Open": frozenset({Kind.FILE, Kind.FOLDER}),
    "Open Command": frozenset({Kind.OTHER}),
    "Copy Answer": frozenset({Kind.OTHER}),
}


@dataclass(frozen=True)
class SampleScore:
    intended_at1: bool | None
    acceptable_at1: bool
    wrong_enter: dict[int, Observed]
    safe_enter: SafeEnter
    rr10: float
    t_first_appear: int | None
    t_at1: int | None
    final_observed_rank: int | None
    coverage_miss: bool


def row_matches(row: Row, target: Target) -> bool:
    if target.kind == "app":
        return row.kind == Kind.APP and normalize(row.title) == normalize(target.id)
    if target.kind in ("file", "folder"):
        expected_kind = Kind.FILE if target.kind == "file" else Kind.FOLDER
        path = PurePosixPath(target.id)
        return (
            row.kind == expected_kind
            and row.folder is not None
            and row.title == path.name
            and row.folder.rstrip("/") == str(path.parent)
        )
    return row.kind == Kind.SETTINGS_PANE and row.pane_id == target.id


def _view(rows: tuple[Row, ...], local_only: bool) -> list[Row]:
    return [r for r in rows if r.source == Source.LOCAL] if local_only else list(rows)


def _rank(rows: list[Row], targets: frozenset[Target]) -> int | None:
    for i, row in enumerate(rows, start=1):
        if any(row_matches(row, t) for t in targets):
            return i
    return None


def _snapshot_at(snapshots: list[Snapshot], t_ms: int) -> Snapshot | None:
    """The latest read that had finished by t_ms, unless what it saw may be too old."""
    known = [s for s in snapshots if s.read_end_ms <= t_ms]
    if not known or t_ms - known[-1].read_start_ms > MAX_SNAPSHOT_AGE_MS:
        return None
    return known[-1]


def _safe_enter(view: list[Row], snap: Snapshot | None, targets: frozenset[Target]) -> SafeEnter:
    action = snap.primary_action if snap else None
    if action is None or any(r.selected is not None for r in view):
        return _safe_enter_from_selection(view, targets)
    screen = snap.rows if snap else ()
    if not screen:
        return "none"
    kinds = ENTER_LABEL_KINDS.get(action)
    if kinds is None:
        return "unreadable"
    if screen[0].kind not in kinds:
        return "highlight_mismatch"
    return "intended" if any(row_matches(screen[0], t) for t in targets) else "other"


def _safe_enter_from_selection(rows: list[Row], targets: frozenset[Target]) -> SafeEnter:
    if not rows:
        return "none"
    if all(r.selected is None for r in rows):
        return "unreadable"
    selected = [r for r in rows if r.selected]
    if not selected:
        return "none"
    return "intended" if any(row_matches(selected[0], t) for t in targets) else "other"


def score_sample(
    sample: Sample, query: Query, local_only: bool = False, window_ms: int = WINDOW_MS
) -> SampleScore:
    end = sample.final_key_post_ms + window_ms
    snaps = sorted(
        (s for s in sample.snapshots if s.read_end_ms <= end and not s.field_mismatch),
        key=lambda s: s.read_end_ms,
    )
    intended = frozenset({query.intended}) if query.intended else query.acceptable
    views = [(s.read_end_ms - sample.final_key_post_ms, _view(s.rows, local_only)) for s in snaps]
    final_rows = views[-1][1] if views else []
    final_rank = _rank(final_rows, intended)

    wrong_enter: dict[int, Observed] = {}
    for cp in CHECKPOINTS_MS:
        snap = _snapshot_at(snaps, sample.final_key_post_ms + cp)
        if snap is None:
            wrong_enter[cp] = "unobserved"
        else:
            wrong_enter[cp] = _rank(_view(snap.rows, local_only), intended) != 1

    t_first_appear = next((t for t, rows in views if _rank(rows, intended) is not None), None)
    t_at1: int | None = None
    for t, rows in reversed(views):
        if _rank(rows, intended) != 1:
            break
        t_at1 = t

    return SampleScore(
        intended_at1=None if query.intended is None else final_rank == 1,
        acceptable_at1=_rank(final_rows[:1], query.acceptable) == 1,
        wrong_enter=wrong_enter,
        safe_enter=_safe_enter(final_rows, snaps[-1] if snaps else None, intended),
        rr10=1.0 / final_rank if final_rank is not None and final_rank <= 10 else 0.0,
        t_first_appear=t_first_appear,
        t_at1=t_at1,
        final_observed_rank=final_rank,
        coverage_miss=t_first_appear is None,
    )
