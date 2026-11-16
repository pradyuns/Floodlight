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
