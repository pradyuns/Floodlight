import json
from pathlib import Path

from bench.generate import queries_from_json

REPO = Path(__file__).resolve().parent.parent


def _load(name: str):  # type: ignore[no-untyped-def]
    return json.loads((REPO / "data" / name).read_text())


def test_every_natural_target_exists_in_the_vm() -> None:
    queries = queries_from_json((REPO / "data/natural-queries.json").read_text())
    apps = {a["name"] for a in _load("inventory-macos-26.4.1.json")["apps"]}
    panes = set(_load("settings-panes-macos-26.4.1.json")["panes"])
    layout = _load("fixture-layout.json")["folders"]
    folders = {f"/Users/bench/{p.rsplit('/', 1)[0]}" for p in layout["files"]}
    folders |= {f"/Users/bench/{'/'.join(p.split('/')[:2])}" for p in layout["files"]}
    valid = {"app": apps, "settings_pane": panes, "folder": folders}
    for q in queries:
        assert q.suite == "natural" and q.rule == "natural" and q.intended is not None
        assert q.intended in q.acceptable
        for t in q.acceptable:
            assert t.id in valid[t.kind], (q.text, t)


def test_review_decisions_are_applied() -> None:
    queries = queries_from_json((REPO / "data/natural-queries.json").read_text())
    texts = {(q.provenance, q.text) for q in queries}
    assert ("model", "battery") not in texts
    generated_folder_texts = {q["text"] for q in _load("folder-queries.json")}
    assert not {t for p, t in texts if p == "model"} & generated_folder_texts
    human = {t for p, t in texts if p == "human"}
    assert {"screen", "act", "chrome", "firefox", "blue", "dock", "wifi"} <= human
    assert "brave" not in human
    assert {q.provenance for q in queries} == {"model", "human"}


def test_each_query_belongs_to_a_task_prompt() -> None:
    tasks = {t["task"] for t in _load("natural-tasks.json")}
    for q in queries_from_json((REPO / "data/natural-queries.json").read_text()):
        assert q.stratum is not None and int(q.stratum.split("task=")[1].split(";")[0]) in tasks
