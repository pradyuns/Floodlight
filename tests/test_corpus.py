import json
import tarfile
from pathlib import Path

from corpus.make_corpus import CREATION_DAY, build_manifest, write_tar
from corpus.summary import summarize
from fixtures.make_files import content_for


def test_corpus_is_deterministic_from_its_seed() -> None:
    assert build_manifest(seed=11, n=500, forbid=set()) == build_manifest(11, 500, set())
    assert build_manifest(11, 500, set()) != build_manifest(12, 500, set())


def test_corpus_has_exactly_n_unique_paths() -> None:
    paths = [e.path for e in build_manifest(3, 2000, set())]
    assert len(paths) == 2000 == len(set(paths))


def test_targeted_names_never_appear_in_the_corpus() -> None:
    forbid = {"river", "zarvel", "test.py", "notes"}
    for entry in build_manifest(5, 3000, forbid):
        lowered = entry.path.lower()
        assert not any(word in lowered for word in forbid), entry.path


def test_tar_holds_valid_contents_with_one_creation_day(tmp_path: Path) -> None:
    manifest = build_manifest(9, 40, set())
    out = tmp_path / "c.tar.gz"
    write_tar(manifest, seed=9, out=out)
    with tarfile.open(out) as tar:
        members = [m for m in tar.getmembers() if m.isfile()]
        assert sorted(m.name for m in members) == sorted(e.path for e in manifest)
        assert {m.mtime for m in tar.getmembers()} == {CREATION_DAY}
        first = members[0]
        data = tar.extractfile(first)
        assert data is not None and data.read() == content_for(first.name, seed=9)


def test_summary_has_shape_but_no_names_or_contents() -> None:
    manifest = build_manifest(4, 1000, set())
    summary = summarize(manifest, seed=4)
    assert summary["files"] == 1000
    assert sum(summary["by_extension"].values()) == 1000
    assert sum(summary["by_pattern"].values()) == 1000
    assert summary["bytes"] == sum(len(content_for(e.path, 4)) for e in manifest)
    text = json.dumps(summary)
    for entry in manifest[:200]:
        assert entry.path.rsplit("/", 1)[-1] not in text
        body = content_for(entry.path, 4)[:40]
        assert body.decode(errors="ignore") not in text or not body.strip()


def test_forbidden_strings_never_empty_a_standard_home_folder() -> None:
    manifest = build_manifest(seed=3, n=4000, forbid={"desk", "down", "doc", "proj"})
    tops = {e.path.split("/")[0] for e in manifest}
    assert {"Desktop", "Downloads", "Documents", "Projects"} <= tops
    for e in manifest:
        created = e.path.split("/")[1:]
        assert not any(
            b in part.lower() for part in created for b in ("desk", "down", "doc", "proj")
        )


def test_downloads_and_desktop_get_their_fixed_share_of_document_files() -> None:
    manifest = build_manifest(seed=4, n=20000, forbid=set())
    tops = [e.path.split("/")[0] for e in manifest]
    docs = sum(t in ("Documents", "Downloads", "Desktop") for t in tops)
    assert abs(tops.count("Downloads") / docs - 0.10) < 0.02
    assert abs(tops.count("Desktop") / docs - 0.02) < 0.01


def test_impossible_forbid_set_fails_loudly_instead_of_looping() -> None:
    import pytest

    with pytest.raises(ValueError, match="reject too many"):
        build_manifest(seed=1, n=10, forbid=set("abcdefghijklmnopqrstuvwxyz0123456789"))
