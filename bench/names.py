"""Invented app names for planted apps, and settings-pane labels."""

import json
import random
from pathlib import Path

from bench.normalize import edit_distance

CONSONANTS = "bdfgklmnprstvz"
VOWELS = "aeiou"
SECOND_WORDS = ["Studio", "Desk", "Pad", "Hub", "Lab", "Works", "Box", "Sync", "Flow", "Deck"]
MIN_DISTANCE = 3


def _invent(rng: random.Random) -> str:
    syllables = rng.choice([2, 2, 3])
    word = "".join(rng.choice(CONSONANTS) + rng.choice(VOWELS) for _ in range(syllables))
    if rng.random() < 0.5:
        word += rng.choice(CONSONANTS)
    return word


def _far_from_all(word: str, blocked: list[str]) -> bool:
    limit = MIN_DISTANCE - 1
    return all(edit_distance(word, other, limit=limit) > limit for other in blocked)


def make_planted_names(seed: int, n: int, dictionary_path: Path, forbid: set[str]) -> list[str]:
    dictionary = {w.strip().lower() for w in dictionary_path.read_text().splitlines() if w.strip()}
    blocked = sorted(dictionary | {w.lower() for w in forbid})
    rng = random.Random(seed)
    heads: list[str] = []
    while len(heads) < n:
        word = _invent(rng)
        if _far_from_all(word, blocked) and _far_from_all(word, heads):
            heads.append(word)
    names = [h.capitalize() for h in heads]
    two_word = n // 2
    return [
        f"{name} {rng.choice(SECOND_WORDS)}" if i < two_word else name
        for i, name in enumerate(names)
    ]


def load_settings_labels(path: Path) -> dict[str, str]:
    labels: dict[str, str] = json.loads(path.read_text())["labels"]
    return labels
