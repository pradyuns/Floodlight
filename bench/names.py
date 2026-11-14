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


class _Trie:
    """The blocked words as a trie, so one distance check walks shared prefixes once."""

    _END = ""

    def __init__(self, words: list[str]) -> None:
        self.root: dict[str, dict] = {}  # type: ignore[type-arg]
        for w in words:
            node = self.root
            for c in w:
                node = node.setdefault(c, {})
            node[self._END] = {}

    def far_from_all(self, word: str, limit: int = MIN_DISTANCE - 1) -> bool:
        """Same answer as _far_from_all(word, words): optimal-string-alignment distance > limit."""

        def near(node: dict, prev_char: str | None, prev: list[int], prev2: list[int]) -> bool:  # type: ignore[type-arg]
            for c, child in node.items():
                if c == self._END:
                    continue
                cur = [prev[0] + 1] + [0] * len(word)
                for j in range(1, len(word) + 1):
                    cost = 0 if c == word[j - 1] else 1
                    cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
                    if (
                        prev_char is not None
                        and j > 1
                        and c == word[j - 2]
                        and prev_char == word[j - 1]
                    ):
                        cur[j] = min(cur[j], prev2[j - 2] + 1)
                if self._END in child and cur[-1] <= limit:
                    return True
                if min(cur) <= limit and near(child, c, cur, prev):
                    return True
            return False

        return not near(self.root, None, list(range(len(word) + 1)), [])


def make_planted_names(seed: int, n: int, dictionary_path: Path, forbid: set[str]) -> list[str]:
    dictionary = {w.strip().lower() for w in dictionary_path.read_text().splitlines() if w.strip()}
    blocked = _Trie(sorted(dictionary | {w.lower() for w in forbid}))
    rng = random.Random(seed)
    heads: list[str] = []
    while len(heads) < n:
        word = _invent(rng)
        if blocked.far_from_all(word) and _far_from_all(word, heads):
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
