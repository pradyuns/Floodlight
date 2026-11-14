"""Deterministic benchmark queries and their mechanically computed accepted answers (spec §4-§5)."""

import json
import random
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from bench.inventory import App
from bench.normalize import edit_distance, normalize

Rule = Literal[
    "full", "nospace", "prefix1", "prefix2", "prefix3", "prefix4", "initials", "typo", "stem"
]
Mode = Literal["completed", "continuous", "stepped"]
TargetKind = Literal["app", "file", "folder", "settings_pane"]
Provenance = Literal["generated", "model", "human"]

DEV_TYPO_SEED = 7
MIN_TYPO_LETTERS = 5
RULE_ORDER: list[Rule] = [
    "full",
    "nospace",
    "initials",
    "prefix1",
    "prefix2",
    "prefix3",
    "prefix4",
    "typo",
]
QWERTY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]


@dataclass(frozen=True)
class Target:
    kind: TargetKind
    id: str
    unique_name: bool = False  # the name occurs once on the guest disk (checked when planted)


@dataclass(frozen=True)
class Query:
    id: str
    text: str
    rule: Rule
    mode: Mode
    intended: Target | None
    acceptable: frozenset[Target]
    ambiguous: bool
    suite: str
    stratum: str | None = None
    provenance: Provenance = "generated"


def _words(name: str) -> list[str]:
    return normalize(name).split()


def _slug(name: str) -> str:
    return "-".join(_words(name))


def _acceptable_for_prefix(prefix: str, inventory: Iterable[App]) -> frozenset[Target]:
    return frozenset(
        Target("app", a.name)
        for a in inventory
        if any(w.startswith(prefix) for w in _words(a.name))
    )


def _acceptable_for_initials(initials: str, inventory: Iterable[App]) -> frozenset[Target]:
    return frozenset(
        Target("app", a.name)
        for a in inventory
        if len(_words(a.name)) > 1 and "".join(w[0] for w in _words(a.name)) == initials
    )


def acceptable_for_short(text: str, inventory: Iterable[App]) -> frozenset[Target]:
    """One rule for every short query: any app with a word starting with it, or those initials."""
    return _acceptable_for_prefix(text, inventory) | _acceptable_for_initials(text, inventory)


def _candidates(app: App) -> list[tuple[Rule, str]]:
    full = normalize(app.name)
    words = full.split()
    out: list[tuple[Rule, str]] = [("full", full)]
    if len(words) > 1:
        out.append(("nospace", "".join(words)))
        out.append(("initials", "".join(w[0] for w in words)))
    for k, rule in enumerate(["prefix1", "prefix2", "prefix3", "prefix4"], start=1):
        prefix = full[:k]
        if len(full) > k and not prefix.endswith(" "):
            out.append((rule, prefix))  # type: ignore[arg-type]
    return out


def _query(app: App, rule: Rule, text: str, inventory: list[App], suite: str) -> Query:
    intended = Target("app", app.name)
    if rule.startswith("prefix") or rule == "initials":
        acceptable = acceptable_for_short(text, inventory) | {intended}
    else:
        acceptable = frozenset({intended})
    return Query(
        id=f"{suite}:{rule}:{_slug(app.name)}",
        text=text,
        rule=rule,
        mode="completed",
        intended=intended,
        acceptable=acceptable,
        ambiguous=len(acceptable) > 1,
        suite=suite,
    )


def _intended_apps(inventory: list[App], kinds: set[str]) -> list[App]:
    return [a for a in inventory if a.kind in kinds]


def generate_dev(
    inventory: list[App],
    intended_kinds: frozenset[str] = frozenset({"builtin", "third_party"}),
    suite: str = "dev",
) -> list[Query]:
    queries: list[Query] = []
    for app in _intended_apps(inventory, set(intended_kinds)):
        seen: set[str] = set()
        for rule, text in sorted(_candidates(app), key=lambda rt: RULE_ORDER.index(rt[0])):
            if text in seen:
                continue
            seen.add(text)
            queries.append(_query(app, rule, text, inventory, suite))
    typos = generate_typos(
        inventory, DEV_TYPO_SEED, exclude=set(), intended_kinds=intended_kinds, suite=suite
    )
    return queries + typos


def _typo_variants(name: str, rng: random.Random) -> list[str]:
    positions = [i for i, c in enumerate(name) if c != " "]
    variants: list[str] = []
    for i in positions:
        if i + 1 < len(name) and name[i + 1] != " " and name[i] != name[i + 1]:
            variants.append(name[:i] + name[i + 1] + name[i] + name[i + 2 :])
        variants.append(name[:i] + name[i + 1 :])
        for row in QWERTY_ROWS:
            j = row.find(name[i])
            if j == -1:
                continue
            for n in (j - 1, j + 1):
                if 0 <= n < len(row):
                    variants.append(name[:i] + row[n] + name[i + 1 :])
    rng.shuffle(variants)
    return variants


def _typo_ok(typo: str, source: str, others: list[str], exclude: set[str]) -> bool:
    if typo in exclude or typo == source or source.startswith(typo):
        return False
    if typo != " ".join(typo.split()):
        return False
    for other in others:
        for k in range(1, len(other) + 1):
            if edit_distance(typo, other[:k], limit=1) <= 1:
                return False
    return True


def generate_typos(
    inventory: list[App],
    seed: int,
    exclude: set[str],
    intended_kinds: frozenset[str] = frozenset({"builtin", "third_party"}),
    suite: str = "dev",
    stratum: str | None = None,
) -> list[Query]:
    queries: list[Query] = []
    for app in _intended_apps(inventory, set(intended_kinds)):
        source = normalize(app.name)
        if len(source.replace(" ", "")) < MIN_TYPO_LETTERS:
            continue
        others = [normalize(a.name) for a in inventory if a.name != app.name]
        rng = random.Random(f"{seed}:{app.name}")
        for typo in _typo_variants(source, rng):
            if _typo_ok(typo, source, others, exclude):
                q = _query(app, "typo", typo, inventory, suite)
                queries.append(
                    Query(**{**q.__dict__, "stratum": stratum})  # keep every other field
                )
                break
    return queries


def generate_collisions(inventory: list[App]) -> list[Query]:
    strings: set[str] = set()
    for app in inventory:
        words = _words(app.name)
        for word in words:
            strings.update(word[:k] for k in range(1, min(4, len(word)) + 1))
        if len(words) > 1:
            strings.add("".join(w[0] for w in words))
    queries: list[Query] = []
    for text in sorted(strings):
        acceptable = acceptable_for_short(text, inventory)
        if len(acceptable) < 2:
            continue
        queries.append(
            Query(
                id=f"collisions:prefix{len(text)}:{text}",
                text=text,
                rule=f"prefix{len(text)}",  # type: ignore[arg-type]
                mode="completed",
                intended=None,
                acceptable=acceptable,
                ambiguous=True,
                suite="collisions",
            )
        )
    return queries


def generate_stepped(
    inventory: list[App],
    intended_kinds: frozenset[str] = frozenset({"builtin", "third_party"}),
) -> list[Query]:
    return [
        Query(
            id=f"stepped:full:{_slug(app.name)}",
            text=normalize(app.name),
            rule="full",
            mode="stepped",
            intended=Target("app", app.name),
            acceptable=frozenset({Target("app", app.name)}),
            ambiguous=False,
            suite="stepped",
        )
        for app in _intended_apps(inventory, set(intended_kinds))
    ]


def _target_json(t: Target | None) -> dict[str, str | bool] | None:
    if t is None:
        return None
    out: dict[str, str | bool] = {"kind": t.kind, "id": t.id}
    if t.unique_name:
        out["unique_name"] = True
    return out


def queries_to_json(queries: list[Query]) -> str:
    rows = [
        {
            **q.__dict__,
            "intended": _target_json(q.intended),
            "acceptable": sorted(
                (_target_json(t) for t in q.acceptable),
                key=lambda d: (str(d["kind"]), str(d["id"])) if d else ("", ""),
            ),
        }
        for q in queries
    ]
    return json.dumps(rows, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def queries_from_json(text: str) -> list[Query]:
    out: list[Query] = []
    for row in json.loads(text):
        intended = row["intended"]
        out.append(
            Query(
                **{
                    **row,
                    "intended": None if intended is None else Target(**intended),
                    "acceptable": frozenset(Target(**t) for t in row["acceptable"]),
                }
            )
        )
    return out
