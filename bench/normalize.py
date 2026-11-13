import unicodedata

_DROP_CATEGORIES = {"Cf", "Mn"}


def normalize(s: str) -> str:
    decomposed = unicodedata.normalize("NFKD", s)
    kept = "".join(c for c in decomposed if unicodedata.category(c) not in _DROP_CATEGORIES)
    return " ".join(kept.casefold().split())


def edit_distance(a: str, b: str, limit: int | None = None) -> int:
    """Optimal-string-alignment distance (adjacent transposition costs 1).

    With `limit`, returns limit + 1 as soon as the distance must exceed it.
    """
    if limit is not None and abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: list[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if limit is not None and min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]
