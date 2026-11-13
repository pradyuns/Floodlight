import json
from pathlib import Path

import pytest

from bench.names import load_settings_labels, make_planted_names
from bench.normalize import edit_distance

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def small_dictionary(tmp_path: Path) -> Path:
    path = tmp_path / "words"
    path.write_text("\n".join(["calendar", "studio", "banana", "pilot", "melon"]) + "\n")
    return path


def test_planted_names_are_ascii_and_split_one_and_two_word(small_dictionary: Path) -> None:
    names = make_planted_names(seed=1, n=10, dictionary_path=small_dictionary, forbid=set())
    assert len(names) == 10
    assert all(n.isascii() for n in names)
    assert sum(1 for n in names if " " in n) == 5


def test_planted_names_are_deterministic(small_dictionary: Path) -> None:
    a = make_planted_names(seed=3, n=6, dictionary_path=small_dictionary, forbid=set())
    b = make_planted_names(seed=3, n=6, dictionary_path=small_dictionary, forbid=set())
    assert a == b


def test_planted_names_keep_distance_from_dictionary_forbidden_and_each_other(
    small_dictionary: Path,
) -> None:
    forbid = {"calculator", "chess"}
    names = make_planted_names(seed=5, n=8, dictionary_path=small_dictionary, forbid=forbid)
    heads = [n.split()[0].lower() for n in names]
    blocked = forbid | set(small_dictionary.read_text().split())
    for i, head in enumerate(heads):
        assert all(edit_distance(head, w) >= 3 for w in blocked)
        assert all(edit_distance(head, other) >= 3 for other in heads[i + 1 :])


def test_settings_synonyms_map_to_the_same_pane() -> None:
    labels = load_settings_labels(REPO / "data" / "settings-labels.json")
    assert labels["wifi"] == labels["wi-fi"]
    assert labels["display"] == labels["displays"]


def test_settings_labels_file_is_valid_json_with_pane_keys() -> None:
    raw = json.loads((REPO / "data" / "settings-labels.json").read_text())
    assert all(isinstance(v, str) and v for v in raw["labels"].values())
