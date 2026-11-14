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
