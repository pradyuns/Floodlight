"""Scores one observed sample against its query (spec §5, §7, §13)."""

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from typing import Literal

from bench.generate import Query, Target
from bench.model import Kind, Row, Sample, Snapshot, Source
from bench.normalize import normalize
from bench.truth import GroundTruth

CHECKPOINTS_MS = (100, 250, 500, 1000)
WINDOW_MS = 3000
MAX_SNAPSHOT_AGE_MS = 100

Observed = bool | Literal["unobserved", "unresolved"]
SafeEnter = Literal[
    "intended", "other", "none", "unreadable", "highlight_mismatch", "unresolved", "unobserved"
]

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
    acceptable_at1: bool | None
    wrong_enter: dict[int, Observed]
    safe_enter: SafeEnter
    rr10: float
    t_first_appear: int | None
    t_at1: int | None
    final_observed_rank: int | None
    coverage_miss: bool
    identity_unresolved: bool  # the first candidate row's file/folder identity can't be pinned down
    # No readable read started within MAX_SNAPSHOT_AGE_MS of the window's end and finished by it:
    # what the screen showed at the cutoff is unknown, so the outcome is neither hit nor miss.
    final_unobserved: bool = False


class Identity(Enum):
    MATCH = "match"
    NO_MATCH = "no_match"
    UNRESOLVED = "unresolved"


def _yes(match: bool) -> Identity:
    return Identity.MATCH if match else Identity.NO_MATCH


def identify(row: Row, target: Target, truth: GroundTruth | None) -> Identity:
    """Whether a row is the target. A file or folder row that shows its full parent path is
    identified by it; one showing only the parent folder's name, or no location, is the target
    only if the ground truth has no other path it could be."""
    if target.kind == "app":
        return _yes(row.kind == Kind.APP and normalize(row.title) == normalize(target.id))
    if target.kind == "settings_pane":
        return _yes(row.kind == Kind.SETTINGS_PANE and row.pane_id == target.id)
    expected_kind = Kind.FILE if target.kind == "file" else Kind.FOLDER
    path = PurePosixPath(target.id)
    if row.kind != expected_kind or row.title != path.name:
        return Identity.NO_MATCH
    shown = None if row.folder is None else row.folder.rstrip("/")
    if shown is not None and "/" in shown:
        return _yes(shown == str(path.parent))
    if shown is not None and shown != path.parent.name:
        return Identity.NO_MATCH
    if truth is None:
        return Identity.UNRESOLVED
    candidates = truth.candidates(expected_kind, path.name)
    if target.id not in candidates:
        raise ValueError(f"target {target.id} not in ground truth")
    if shown is not None:
        candidates = frozenset(p for p in candidates if PurePosixPath(p).parent.name == shown)
    return Identity.MATCH if candidates == {target.id} else Identity.UNRESOLVED


def row_matches(row: Row, target: Target, truth: GroundTruth | None = None) -> bool:
    return identify(row, target, truth) is Identity.MATCH


def _identity(row: Row, targets: frozenset[Target], truth: GroundTruth | None) -> Identity:
    found = {identify(row, t, truth) for t in targets}
    if Identity.MATCH in found:
        return Identity.MATCH
    return Identity.UNRESOLVED if Identity.UNRESOLVED in found else Identity.NO_MATCH


def _first_candidate(
    rows: list[Row], targets: frozenset[Target], truth: GroundTruth | None
) -> Identity | None:
    """Identity of the first row that is, or may be, a target."""
    for row in rows:
        found = _identity(row, targets, truth)
        if found is not Identity.NO_MATCH:
            return found
    return None


def _view(rows: tuple[Row, ...], local_only: bool) -> list[Row]:
    return [r for r in rows if r.source == Source.LOCAL] if local_only else list(rows)


def _rank(rows: list[Row], targets: frozenset[Target], truth: GroundTruth | None) -> int | None:
    for i, row in enumerate(rows, start=1):
        if any(row_matches(row, t, truth) for t in targets):
            return i
    return None


def _snapshot_at(snapshots: list[Snapshot], t_ms: int) -> Snapshot | None:
    """The latest read that had finished by t_ms, unless what it saw may be too old."""
    known = [s for s in snapshots if s.read_end_ms <= t_ms]
    if not known or t_ms - known[-1].read_start_ms > MAX_SNAPSHOT_AGE_MS:
        return None
    return known[-1]


def _enter_outcome(row: Row, targets: frozenset[Target], truth: GroundTruth | None) -> SafeEnter:
    found = _identity(row, targets, truth)
    if found is Identity.UNRESOLVED:
        return "unresolved"
    return "intended" if found is Identity.MATCH else "other"


def _safe_enter(
    view: list[Row], snap: Snapshot | None, targets: frozenset[Target], truth: GroundTruth | None
) -> SafeEnter:
    action = snap.primary_action if snap else None
    if action is None or any(r.selected is not None for r in view):
        return _safe_enter_from_selection(view, targets, truth)
    screen = snap.rows if snap else ()
    if not screen:
        return "none"
    kinds = ENTER_LABEL_KINDS.get(action)
    if kinds is None:
        return "unreadable"
    if screen[0].kind not in kinds:
        return "highlight_mismatch"
    return _enter_outcome(screen[0], targets, truth)


def _safe_enter_from_selection(
    rows: list[Row], targets: frozenset[Target], truth: GroundTruth | None
) -> SafeEnter:
    if not rows:
        return "none"
    if all(r.selected is None for r in rows):
        return "unreadable"
    selected = [r for r in rows if r.selected]
    if not selected:
        return "none"
    return _enter_outcome(selected[0], targets, truth)


def score_sample(
    sample: Sample,
    query: Query,
    local_only: bool = False,
    window_ms: int = WINDOW_MS,
    truth: GroundTruth | None = None,
) -> SampleScore:
    end = sample.final_key_post_ms + window_ms
    snaps = sorted(
        (
            s
            for s in sample.snapshots
            if s.read_end_ms <= end and not s.field_mismatch and s.unreadable is None
        ),
        key=lambda s: s.read_end_ms,
    )
    intended = frozenset({query.intended}) if query.intended else query.acceptable
    views = [(s.read_end_ms - sample.final_key_post_ms, _view(s.rows, local_only)) for s in snaps]
    final_snap = _snapshot_at(snaps, end)
    if final_snap is None:
        return _unobserved(sample, snaps, intended, local_only, truth)
    final_rows = _view(final_snap.rows, local_only)
    final_rank = _rank(final_rows, intended, truth)
    unresolved = _first_candidate(final_rows, intended, truth) is Identity.UNRESOLVED

    wrong_enter = _wrong_enter(sample, snaps, intended, local_only, truth)
    t_first_appear = next(
        (t for t, rows in views if _rank(rows, intended, truth) is not None), None
    )
    t_at1: int | None = None
    for t, rows in reversed(views):
        if _rank(rows, intended, truth) != 1:
            break
        t_at1 = t

    return SampleScore(
        intended_at1=None if query.intended is None or unresolved else final_rank == 1,
        acceptable_at1=_rank(final_rows[:1], query.acceptable, truth) == 1,
        wrong_enter=wrong_enter,
        safe_enter=_safe_enter(final_rows, final_snap, intended, truth),
        rr10=1.0 / final_rank if final_rank is not None and final_rank <= 10 else 0.0,
        t_first_appear=t_first_appear,
        t_at1=t_at1,
        final_observed_rank=final_rank,
        coverage_miss=not any(_first_candidate(rows, intended, truth) for _, rows in views),
        identity_unresolved=unresolved,
    )


def _unobserved(
    sample: Sample,
    snaps: list[Snapshot],
    intended: frozenset[Target],
    local_only: bool,
    truth: GroundTruth | None,
) -> SampleScore:
    return SampleScore(
        intended_at1=None,
        acceptable_at1=None,
        wrong_enter=_wrong_enter(sample, snaps, intended, local_only, truth),
        safe_enter="unobserved",
        rr10=0.0,
        t_first_appear=None,
        t_at1=None,
        final_observed_rank=None,
        coverage_miss=False,
        identity_unresolved=False,
        final_unobserved=True,
    )


def _wrong_enter(
    sample: Sample,
    snaps: list[Snapshot],
    intended: frozenset[Target],
    local_only: bool,
    truth: GroundTruth | None,
) -> dict[int, Observed]:
    wrong_enter: dict[int, Observed] = {}
    for cp in CHECKPOINTS_MS:
        snap = _snapshot_at(snaps, sample.final_key_post_ms + cp)
        view = _view(snap.rows, local_only) if snap else []
        if snap is None:
            wrong_enter[cp] = "unobserved"
        elif view and _identity(view[0], intended, truth) is Identity.UNRESOLVED:
            wrong_enter[cp] = "unresolved"
        else:
            wrong_enter[cp] = _rank(view, intended, truth) != 1

    return wrong_enter
