import json
from pathlib import Path

import pytest

from bench.final import FINAL_TOOLS, final_plan, load_heldout, plant_command
from bench.heldout import canonical_bytes, commitment


def _query(qid: str, stratum: str) -> dict[str, object]:
    ref = {"id": "Zorblat", "kind": "app"}
    return {
        "acceptable": [ref],
        "ambiguous": False,
        "id": qid,
        "intended": ref,
        "mode": "completed",
        "provenance": "generated",
        "rule": "full",
        "stratum": stratum,
        "suite": "heldout",
        "text": qid,
    }


def _heldout(tmp_path: Path) -> tuple[Path, Path, str]:
    data = {
        "version": 1,
        "planted_names": ["Zorblat"],
        "strata": {
            "a": [_query(f"a{i}", "a") for i in range(8)],
            "b": [_query(f"b{i}", "b") for i in range(12)],
        },
        "overlap_b_with_dev": 0,
    }
    file, nonce = tmp_path / "heldout.json", tmp_path / "nonce.bin"
    file.write_bytes(canonical_bytes(data))
    nonce.write_bytes(b"\x01" * 32)
    return file, nonce, commitment(nonce.read_bytes(), file.read_bytes())


def test_warm_runs_every_heldout_query_on_all_three_tools(tmp_path: Path) -> None:
    file, nonce, digest = _heldout(tmp_path)
    held = load_heldout(file, nonce, digest)
    plan = final_plan("final-warm", held)
    assert plan.tools == FINAL_TOOLS == ("spotlight", "raycast", "floodlight")
    assert (plan.env, plan.conditions, plan.runs, plan.pause_ms) == ("sparse", ("warm",), 5, 300)
    assert len(plan.query_ids) == 20


def test_restart_pairs_are_a_seeded_25_percent_subset(tmp_path: Path) -> None:
    held = load_heldout(*_heldout(tmp_path))
    plan = final_plan("final-restart", held)
    assert (plan.env, plan.conditions) == ("sparse", ("ui_restart", "warm"))
    assert len(plan.query_ids) == 5
    assert plan == final_plan("final-restart", held)


def test_busy_is_warm_on_a_seeded_25_percent_subset(tmp_path: Path) -> None:
    held = load_heldout(*_heldout(tmp_path))
    plan = final_plan("final-busy", held)
    assert (plan.env, plan.conditions) == ("busy", ("warm",))
    assert len(plan.query_ids) == 5
    assert plan == final_plan("final-busy", held)
    assert plan.query_ids != final_plan("final-restart", held).query_ids


def test_refuses_a_file_that_does_not_match_the_commitment(tmp_path: Path) -> None:
    file, nonce, _ = _heldout(tmp_path)
    with pytest.raises(SystemExit, match="commitment"):
        load_heldout(file, nonce, "0" * 64)


def test_refuses_an_unknown_part(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        final_plan("final-everything", load_heldout(*_heldout(tmp_path)))


def test_plant_command_reads_names_from_a_file_and_never_contains_them(tmp_path: Path) -> None:
    held = load_heldout(*_heldout(tmp_path))
    cmd = plant_command("/Volumes/My Shared Files/run/planted.txt")
    assert "Zorblat" not in cmd
    assert "make_planted.sh" in cmd and "< '/Volumes/My Shared Files/run/planted.txt'" in cmd
    assert held.planted_names == ("Zorblat",)
    assert "Zorblat" not in json.dumps(held.summary())


class FakeGuest:
    """Records guest commands; answers mdfind counts and probe dumps."""

    def __init__(self, listed: dict[str, set[str]]) -> None:
        self.commands: list[str] = []
        self.listed = listed

    def sh(self, cmd: str, timeout: float = 600) -> str:
        self.commands.append(cmd)
        if cmd.startswith("mdfind -count"):
            return "1\n"
        if "probe dump" in cmd:
            tool = cmd.split("--tool ")[1].split()[0]
            name = cmd.split("--query ")[1].split()[0].strip("'")
            title = next((n for n in self.listed[tool] if n.lower() == name), None)
            rows = [{"title": title, "kind": "app"}] if title else []
            return json.dumps(rows) + "\nexit=0"
        if "shasum -a 256" in cmd:
            from bench.final import PLANTER_SHA256

            return "".join(f"{d}  {f}\n" for f, d in PLANTER_SHA256.items())
        if "make_planted.sh" in cmd:
            return "planted=2 failed=0\n"
        return "up\n"


def test_planting_passes_names_only_through_a_file_that_is_deleted(tmp_path: Path) -> None:
    from bench.final import plant_and_restart

    guest = FakeGuest({})
    counts = plant_and_restart(
        guest.sh, guest.sh, tmp_path, ("Zorblat", "Quimble"), sleep=lambda s: None
    )
    assert counts == {"planted": 2, "failed": 0}
    assert not (tmp_path / "planted.txt").exists()
    planting = [c for c in guest.commands if "./make_planted.sh" in c]
    assert len(planting) == 1 and "Zorblat" not in planting[0]
    assert any("shutdown -r" in c for c in guest.commands)


def test_ready_check_counts_every_tool_and_never_reports_names() -> None:
    from bench.final import ready_check

    names = ("Zorblat", "Quimble")
    every = {t: set(names) for t in FINAL_TOOLS}
    assert ready_check(FakeGuest(every).sh, names, sleep=lambda s: None) == {
        "spotlight": 2,
        "raycast": 2,
        "floodlight": 2,
    }
    missing = {**every, "raycast": {"Zorblat"}}
    with pytest.raises(RuntimeError) as err:
        ready_check(FakeGuest(missing).sh, names, sleep=lambda s: None)
    assert "raycast" in str(err.value) and "Quimble" not in str(err.value)


def test_reads_the_published_commitment_from_the_lock_file() -> None:
    from bench.final import published_commitment

    digest = "ab" * 32
    assert published_commitment(f"x  data/a.json\nheldout_commitment {digest}\n") == digest
    with pytest.raises(SystemExit):
        published_commitment("x  data/a.json\n")


def test_refuses_a_floodlight_build_that_is_not_the_pinned_one() -> None:
    from bench.final import check_floodlight

    pinned = "cd" * 32
    ok = {"sha": pinned}
    assert check_floodlight(lambda cmd, t=600: f"{ok['sha']}  /Applications/x\n", pinned) == {
        "floodlight_sha256": pinned
    }
    with pytest.raises(RuntimeError, match="Floodlight"):
        check_floodlight(lambda cmd, t=600: "ee" * 32 + "  x\n", pinned)
    with pytest.raises(SystemExit, match="pinned"):
        check_floodlight(lambda cmd, t=600: pinned, None)


def test_final_runs_only_with_the_pinned_probe_and_floodlight_build() -> None:
    from bench.final import FLOODLIGHT_SHA256, require_final_probe

    assert FLOODLIGHT_SHA256 == "4c9bb50015a98ea88bd116116309d34a55041fa6df5b7465ed13c8e667826661"
    for part in ("final-warm", "final-busy"):
        require_final_probe(part, "probe-74220bbf4463")
        with pytest.raises(SystemExit, match="probe-e3e18537995d"):
            require_final_probe(part, "probe-e3e18537995d")


def test_restart_runs_only_with_the_fixed_restart_probe() -> None:
    from bench.final import require_final_probe

    require_final_probe("final-restart", "probe-9b7a7674653c")
    with pytest.raises(SystemExit, match="probe-74220bbf4463"):
        require_final_probe("final-restart", "probe-74220bbf4463")


class FlakyListing:
    """Probe dumps answer from a script: one list of titles per call, then the last one forever."""

    def __init__(self, answers: list[list[str]]) -> None:
        self.answers = answers
        self.dumps = 0

    def sh(self, cmd: str, timeout: float = 600) -> str:
        answer = self.answers[min(self.dumps, len(self.answers) - 1)]
        self.dumps += 1
        return json.dumps([{"title": t, "kind": "app"} for t in answer]) + "\nexit=0"


def test_ready_check_retries_a_valid_read_that_misses_the_app() -> None:
    from bench.final import ready_check

    guest = FlakyListing([[], ["Zorblat"]])
    assert ready_check(guest.sh, ("Zorblat",), tools=("raycast",), sleep=lambda s: None) == {
        "raycast": 1
    }
    assert guest.dumps == 2


def test_ready_check_gives_up_after_three_reads_without_the_app() -> None:
    from bench.final import ready_check

    guest = FlakyListing([[]])
    with pytest.raises(RuntimeError, match="raycast"):
        ready_check(guest.sh, ("Zorblat",), tools=("raycast",), sleep=lambda s: None)
    assert guest.dumps == 3


class PlanterGuest(FakeGuest):
    def __init__(self, digests: dict[str, str]) -> None:
        super().__init__({})
        self.digests = digests

    def sh(self, cmd: str, timeout: float = 600) -> str:
        if cmd.startswith("cd ") and "shasum -a 256" in cmd:
            self.commands.append(cmd)
            return "".join(f"{d}  {f}\n" for f, d in self.digests.items())
        return super().sh(cmd, timeout)


def test_planting_runs_only_the_pinned_planter_files(tmp_path: Path) -> None:
    from bench.final import PLANTER_SHA256, plant_and_restart

    guest = PlanterGuest(dict(PLANTER_SHA256))
    plant_and_restart(guest.sh, guest.sh, tmp_path, ("Zorblat", "Quimble"), sleep=lambda s: None)
    download = next(c for c in guest.commands if "curl" in c)
    assert "rm -f planted make_planted.sh" in download.split("curl")[0]
    assert any("./make_planted.sh" in c for c in guest.commands)

    tampered = PlanterGuest({**PLANTER_SHA256, "make_planted.sh": "ee" * 32})
    with pytest.raises(RuntimeError, match=r"make_planted\.sh"):
        plant_and_restart(tampered.sh, tampered.sh, tmp_path, ("Zorblat",), sleep=lambda s: None)
    assert not any("./make_planted.sh" in c for c in tampered.commands)
    assert not (tmp_path / "planted.txt").exists()


def test_planter_digests_match_the_staged_files_and_sources_are_locked() -> None:
    import hashlib

    from bench.final import PLANTER_SHA256
    from bench.lock import locked_paths

    root = Path(__file__).resolve().parents[1]
    assert PLANTER_SHA256 == {
        "planted": "4703b46c5103c1063e90caa897a72e165c2e7d0ab9b5d28bfabf6e4680ea1617",
        "make_planted.sh": "0f77760b88ce375bc03a56d80dbfb47cb53df948c2dee469a83efbf4b2078e9c",
    }
    script = (root / "fixtures/make_planted.sh").read_bytes()
    assert hashlib.sha256(script).hexdigest() == PLANTER_SHA256["make_planted.sh"]
    locked = {p.relative_to(root).as_posix() for p in locked_paths(root)}
    assert {"fixtures/make_planted.sh", "fixtures/planted_main.c"} <= locked
