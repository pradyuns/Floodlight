import argparse
import json
from pathlib import Path

from bench.__main__ import cmd_queries
from bench.generate import Target, queries_from_json


def _app(name: str, kind: str) -> dict[str, str]:
    path = f"/Applications/{name}.app"
    return {"name": name, "path": path, "real_path": path, "bundle_id": name, "kind": kind}


def test_queries_command_writes_dev_collision_and_stepped_files(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.json"
    apps = [
        _app("Calendar", "builtin"),
        _app("Rectangle", "third_party"),
        _app("Raycast", "tool_under_test"),
    ]
    inventory.write_text(json.dumps({"apps": apps}))

    assert cmd_queries(argparse.Namespace(inventory=str(inventory), out_dir=str(tmp_path))) == 0

    dev = queries_from_json((tmp_path / "dev-queries.json").read_text())
    collisions = queries_from_json((tmp_path / "collision-queries.json").read_text())
    stepped = queries_from_json((tmp_path / "stepped-queries.json").read_text())
    assert {q.intended.id for q in dev if q.intended} == {"Calendar", "Rectangle"}
    assert {q.intended.id for q in stepped if q.intended} == {"Calendar", "Rectangle"}
    r = next(q for q in dev if q.text == "r")
    assert r.acceptable == {Target("app", "Rectangle"), Target("app", "Raycast")}
    assert [(q.text, q.acceptable) for q in collisions] == [("r", r.acceptable)]
