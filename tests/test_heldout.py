import json
import subprocess
import sys
from pathlib import Path

import pytest

from bench.heldout import build_heldout, canonical_bytes, commitment, verify_commitment
from bench.inventory import App

REPO = Path(__file__).resolve().parent.parent
DICT = Path("/usr/share/dict/words")
SEED = b"not-the-real-seed: test only\n"


def _inventory() -> list[App]:
    raw = json.loads((REPO / "data/inventory-macos-26.4.1.json").read_text())["apps"]
    return [App(**a) for a in raw]


def _dev_strings() -> set[str]:
    return {q["text"] for q in json.loads((REPO / "data/dev-queries.json").read_text())}


@pytest.fixture(scope="module")
def heldout():  # type: ignore[no-untyped-def]
    if not DICT.exists():
        pytest.skip("needs the macOS dictionary")
    return build_heldout(SEED, _inventory(), DICT, _dev_strings(), public_names=set())


def test_stratum_a_never_reuses_a_dev_string(heldout) -> None:  # type: ignore[no-untyped-def]
    texts = {q["text"] for q in heldout["strata"]["a"]}
    assert texts and not texts & _dev_strings()


def test_stratum_b_overlap_with_dev_strings_is_allowed_and_reported(heldout) -> None:  # type: ignore[no-untyped-def]
    texts = {q["text"] for q in heldout["strata"]["b"]}
    assert heldout["overlap_b_with_dev"] == len(texts & _dev_strings())


def test_forty_secret_names_half_two_word(heldout) -> None:  # type: ignore[no-untyped-def]
    names = heldout["planted_names"]
    assert len(names) == 40 and sum(" " in n for n in names) == 20


def test_same_seed_gives_identical_file_bytes(heldout) -> None:  # type: ignore[no-untyped-def]
    again = build_heldout(SEED, _inventory(), DICT, _dev_strings(), public_names=set())
    assert canonical_bytes(again) == canonical_bytes(heldout)


def test_commitment_fails_on_a_one_byte_change() -> None:
    nonce, data = bytes(32), b'{"a":1}'
    digest = commitment(nonce, data)
    assert verify_commitment(digest, nonce, data)
    assert not verify_commitment(digest, nonce, b'{"a":2}')
    assert not verify_commitment(digest, b"\x01" + bytes(31), data)


def _cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "bench", "heldout", *args],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def test_out_dir_inside_the_repo_is_refused(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    seed.write_bytes(SEED)
    result = _cli("--seed-file", str(seed), "--out-dir", str(REPO / "results" / "heldout-x"))
    assert result.returncode != 0 and "inside the repo" in result.stderr
    assert not (REPO / "results" / "heldout-x").exists()


def test_stdout_has_digest_and_counts_but_no_query_strings(tmp_path: Path) -> None:
    if not DICT.exists():
        pytest.skip("needs the macOS dictionary")
    seed, out = tmp_path / "seed", tmp_path / "out"
    seed.write_bytes(SEED)
    result = _cli("--seed-file", str(seed), "--out-dir", str(out))
    assert result.returncode == 0, result.stderr
    data = (out / "heldout.json").read_bytes()
    nonce = (out / "nonce.bin").read_bytes()
    assert len(nonce) == 32
    assert commitment(nonce, data) in result.stdout
    import hashlib

    assert f"dictionary_sha256={hashlib.sha256(DICT.read_bytes()).hexdigest()}" in result.stdout
    file = json.loads(data)
    secrets = [q["text"] for s in file["strata"].values() for q in s] + file["planted_names"]
    leaked = [s for s in secrets if len(s) >= 3 and s in result.stdout + result.stderr]
    assert not leaked


def test_existing_output_is_never_overwritten(tmp_path: Path) -> None:
    seed, out = tmp_path / "seed", tmp_path / "out"
    seed.write_bytes(SEED)
    out.mkdir()
    (out / "nonce.bin").write_bytes(b"keep")
    result = _cli("--seed-file", str(seed), "--out-dir", str(out))
    assert result.returncode != 0
    assert (out / "nonce.bin").read_bytes() == b"keep"
