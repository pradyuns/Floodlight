from pathlib import Path

import pytest

from bench.lock import LockMismatch, compute_lock, locked_paths, verify_lock, write_lock

REPO = Path(__file__).resolve().parent.parent


def _tree(root: Path) -> list[Path]:
    files = [root / "data" / "q.json", root / "bench" / "score.py"]
    for f in files:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(f"content of {f.name}\n")
    return files


def test_lock_changes_when_any_locked_file_changes(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    before = compute_lock(files, root=tmp_path)
    files[1].write_text("content of score.py!\n")
    assert compute_lock(files, root=tmp_path) != before


def test_verify_raises_and_names_the_changed_file(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    write_lock(files, root=tmp_path, commitment="ab" * 32)
    verify_lock(root=tmp_path)
    files[0].write_text("edited after lock\n")
    with pytest.raises(LockMismatch, match=r"data/q\.json"):
        verify_lock(root=tmp_path)


def test_verify_raises_when_a_locked_file_is_missing(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    write_lock(files, root=tmp_path, commitment="ab" * 32)
    files[1].unlink()
    with pytest.raises(LockMismatch, match=r"bench/score\.py"):
        verify_lock(root=tmp_path)


def test_lock_file_records_the_heldout_commitment(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    write_lock(files, root=tmp_path, commitment="cd" * 32)
    assert "heldout_commitment " + "cd" * 32 in (tmp_path / "LOCK.txt").read_text()


def test_bad_commitment_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="64 hex"):
        write_lock(_tree(tmp_path), root=tmp_path, commitment="not-a-digest")


def test_locked_set_covers_queries_scoring_and_plan() -> None:
    names = {p.relative_to(REPO).as_posix() for p in locked_paths(REPO)}
    for must in (
        "data/dev-queries.json",
        "data/natural-queries.json",
        "data/inventory-macos-26.4.1.json",
        "data/third-party.json",
        "bench/score.py",
        "bench/stats.py",
        "bench/generate.py",
        "bench/normalize.py",
        "bench/schedule.py",
        "bench/truth.py",
        "corpus/make_corpus.py",
        "bench/campaign.py",
        "bench/baseline.py",
        "bench/__main__.py",
        "probe/Package.swift",
        "probe/Sources/ProbeCore/Spotlight.swift",
        "probe/Sources/ProbeCore/Raycast.swift",
        "probe/Sources/ProbeCore/Sampler.swift",
        "probe/Sources/probe/main.swift",
    ):
        assert must in names, must
    assert not any(n.endswith(".local.md") or n.startswith("results/") for n in names)


def test_lock_refuses_an_analysis_plan_with_unfilled_settings(tmp_path: Path) -> None:
    files = _tree(tmp_path)
    plan = tmp_path / "docs" / "analysis-plan.md"
    plan.parent.mkdir()
    plan.write_text("- Late-change window: TBD\n")
    with pytest.raises(ValueError, match="TBD"):
        write_lock([*files, plan], root=tmp_path, commitment="ab" * 32)
