"""Post-reveal offline control (not preregistered, not a launcher): how far basic name matching
gets on the held-out app queries. Exact name, name prefix, later-word prefix and initials, then
optionally names within one edit (insert, delete, substitute, adjacent swap); alphabetical
tie-break. No tuning, aliases, usage history or Floodlight code.

usage: python -m scripts.simple_matcher_control HELDOUT NONCE
"""

import json
import sys
from pathlib import Path

from bench.final import load_heldout, published_commitment
from bench.generate import Query
from bench.normalize import normalize
from bench.stats import weighted_mean


def osa(a: str, b: str) -> int:
    """Optimal string alignment distance (Levenshtein plus adjacent swaps)."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(
                d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1])
            )
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def simple_match(text: str, names: list[str], one_edit: bool) -> str | None:
    q = normalize(text).replace(" ", "")
    best: list[tuple[int, str, str]] = []
    for name in names:
        words = normalize(name).split()
        full = "".join(words)
        if full == q:
            tier = 0
        elif full.startswith(q):
            tier = 1
        elif any("".join(words[i:]).startswith(q) for i in range(1, len(words))):
            tier = 2
        elif q == "".join(w[0] for w in words):
            tier = 3
        elif one_edit and osa(q, full) <= 1:
            tier = 4
        else:
            continue
        best.append((tier, normalize(name), name))
    return min(best)[2] if best else None


def app_weighted_hits(queries: list[Query], names: list[str], one_edit: bool) -> tuple[int, float]:
    values = []
    for q in queries:
        assert q.intended is not None
        got = simple_match(q.text, names, one_edit)
        values.append(
            (
                q.intended.id,
                q.id,
                float(got is not None and normalize(got) == normalize(q.intended.id)),
            )
        )
    return int(sum(v for *_, v in values)), 100 * weighted_mean(values, "app")


def main() -> int:
    held = load_heldout(
        Path(sys.argv[1]), Path(sys.argv[2]), published_commitment(Path("LOCK.txt").read_text())
    )
    inventory = json.loads(Path("data/inventory-macos-26.4.1.json").read_text())["apps"]
    names = [a["name"] for a in inventory] + list(held.planted_names)
    sets = {
        "primary (stratum b, unambiguous)": [
            q for q in held.queries.values() if q.stratum == "b" and not q.ambiguous
        ],
        "real-app typos (stratum a)": [q for q in held.queries.values() if q.stratum == "a"],
    }
    for label, qs in sets.items():
        for one_edit in (False, True):
            hits, pct = app_weighted_hits(qs, names, one_edit)
            rules = "with one-edit" if one_edit else "no typo matching"
            print(f"{label}, {rules}: {hits}/{len(qs)} queries, app-weighted {pct:.4f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
