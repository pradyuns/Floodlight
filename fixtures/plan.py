"""What gets planted in each fixture clone, and the queries that test it (spec §3, §13.4, §13.21).

Families, each planted in its own clone of the base snapshot:
- planted-dev: dummy apps from the public seed; every §4 rule (gate: each listed under its name).
- stress-2x2: apps with/without U+200E in the display name x with/without .svg decoys.
- stress-two-word: two-word apps queried without the space.
- stress-test-py: one test.py among lookalike files.
- folders: neutral folders (flat "abc-101" style and nested project trees).
- cross-kind: an exact file name or settings label competing with a weaker app match.
"""

import random
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from bench.generate import Query, Target, generate_dev
from bench.inventory import App
from bench.names import make_planted_names
from bench.normalize import normalize

PUBLIC_SEED = 1114
HOME = "/Users/bench"
LRM = "‎"
CONSONANTS = "bcdfghjklmnpqrstvwxz"
SVG_DECOYS = ("{}.svg", "{}-icon.svg", "{}-logo.svg", "{}-white.svg", "{}_badge.svg")
# Top-level System Settings panes both tools listed by title in the macOS 26.4.1 VM. Left out:
# Control Center (under Menu Bar in macOS 26); Battery, Trackpad, Touch ID & Password, Wi-Fi (need
# hardware the VM lacks); General (not confirmed). Only panes that compete with a weaker app match
# are used.
PANE_TITLES = [
    *[
        "Accessibility",
        "Appearance",
        "Spotlight",
        "Wallpaper",
        "Notifications",
        "Sound",
        "Focus",
    ],
    *[
        "Keyboard",
        "Mouse",
        "Displays",
        "Bluetooth",
        "Network",
        "Passwords",
    ],
    "Screen Time",
    "Game Center",
    "Lock Screen",
    "Time Machine",
    "Internet Accounts",
    "Printers & Scanners",
    "Privacy & Security",
    "Desktop & Dock",
    "Users & Groups",
]


@dataclass(frozen=True)
class Family:
    apps: tuple[str, ...] = ()  # display names (may contain U+200E)
    files: tuple[str, ...] = ()  # paths relative to HOME
    decoys: tuple[str, ...] = ()  # targeted lookalikes among files (kept out of the corpus)
    queries: tuple[Query, ...] = ()


@dataclass(frozen=True)
class Layout:
    families: dict[str, Family] = field(default_factory=dict)


def _planted(names: list[str]) -> list[App]:
    return [
        App(n.replace(LRM, ""), f"/Applications/{n.replace(LRM, '')}.app", "", "", "planted")
        for n in names
    ]


def _app_queries(
    base: list[App], names: list[str], suite: str, rules: set[str] | None = None
) -> list[Query]:
    queries = generate_dev(base + _planted(names), frozenset({"planted"}), suite)
    return [q for q in queries if rules is None or q.rule in rules]


def _code(rng: random.Random, taken: set[str]) -> str:
    while True:
        name = "".join(rng.choice(CONSONANTS) for _ in range(3)) + f"-{rng.randint(100, 999)}"
        if name not in taken:
            taken.add(name)
            return name


def _file_target(rel: str) -> Target:
    return Target("file", f"{HOME}/{rel}")


def _single(qid: str, text: str, rule: str, target: Target, suite: str, stratum: str) -> Query:
    return Query(qid, text, rule, "completed", target, frozenset({target}), False, suite, stratum)  # type: ignore[arg-type]


def _stress_2x2(base: list[App], heads: list[str]) -> Family:
    apps: list[str] = []
    files: list[str] = []
    queries: list[Query] = []
    cells = [(lrm, svg) for lrm in (False, True) for svg in (False, True)]
    for i, name in enumerate(heads):
        lrm, svg = cells[i % 4]
        apps.append(LRM + name if lrm else name)
        if svg:
            files += [f"Downloads/{p.format(name.lower())}" for p in SVG_DECOYS]
        stratum = f"lrm={'yes' if lrm else 'no'},svg={'yes' if svg else 'no'}"
        for q in _app_queries(base, [name], "stress-2x2", {"full", "prefix4"}):
            queries.append(Query(**{**q.__dict__, "stratum": stratum}))
    return Family(tuple(apps), tuple(files), tuple(files), tuple(queries))


def _stress_test_py(rng: random.Random, words: list[str], taken: set[str]) -> Family:
    project, other = f"Projects/{words[0]}-api", f"Projects/{words[1]}"
    docs = f"Documents/{_code(rng, taken)}"
    target = f"{project}/test.py"
    decoys = [
        f"{project}/test_utils.py",
        f"{project}/tests/test_models.py",
        f"{other}/latest.py",
        f"{other}/contest.py",
        f"{docs}/test.txt",
        f"{docs}/test-plan.md",
        "Downloads/test.pdf",
    ]
    query = _single(
        "stress-test-py:full:test.py",
        "test.py",
        "full",
        _file_target(target),
        "stress-test-py",
        "decoys=yes",
    )
    return Family((), (target, *decoys), tuple(decoys), (query,))


def _folders(rng: random.Random, words: list[str], taken: set[str]) -> Family:
    files: list[str] = []
    targets: list[str] = []
    for _ in range(8):
        folder = f"Documents/{_code(rng, taken)}"
        files.append(f"{folder}/readme.md")
        targets.append(folder)
    for root, leaf in zip(words[0::2], words[1::2], strict=True):
        project = f"Projects/{root}"
        files += [
            f"{project}/readme.md",
            f"{project}/src/{leaf}/main.swift",
            f"{project}/docs/guide.md",
        ]
        targets += [project, f"{project}/src/{leaf}"]
    queries: list[Query] = []
    for folder in targets:
        name = PurePosixPath(folder).name
        target = Target("folder", f"{HOME}/{folder}")
        queries.append(_single(f"folders:full:{name}", name, "full", target, "folders", "planted"))
        if "-" in name:
            bare = name.replace("-", "")
            queries.append(
                _single(
                    f"folders:punct_removed:{name}",
                    bare,
                    "punct_removed",
                    target,
                    "folders",
                    "planted",
                )
            )
    return Family((), tuple(files), (), tuple(queries))


def _cross_kind(
    base: list[App], dictionary: Path, rng: random.Random, taken: set[str], n_files: int = 10
) -> Family:
    app_words = {w for a in base for w in normalize(a.name).split()}
    app_names = {normalize(a.name) for a in base}
    words = sorted({w.strip() for w in dictionary.read_text().splitlines() if w.strip().islower()})
    stems = [
        s
        for s in words
        if len(s) >= 4 and s not in app_words and any(w.startswith(s) and w != s for w in app_words)
    ]
    files: list[str] = []
    queries: list[Query] = []
    for i, stem in enumerate(sorted(rng.sample(stems, n_files))):
        ext = (".txt", ".pdf", ".md")[i % 3]
        rel = f"Documents/{_code(rng, taken)}/{stem}{ext}"
        files.append(rel)
        competes = ",".join(
            sorted(
                a.name for a in base if any(w.startswith(stem) for w in normalize(a.name).split())
            )
        )
        for text, rule in ((stem, "stem"), (stem + ext, "full")):
            queries.append(
                _single(
                    f"cross-kind:{rule}:{stem}",
                    text,
                    rule,
                    _file_target(rel),
                    "cross-kind",
                    f"file;competes={competes}",
                )
            )
    for title in PANE_TITLES:
        label = normalize(title)
        first = label.split()[0]
        if label in app_names or not any(w.startswith(first) for w in app_words):
            continue
        competes = ",".join(
            sorted(
                a.name for a in base if any(w.startswith(first) for w in normalize(a.name).split())
            )
        )
        target = Target("settings_pane", title)
        queries.append(
            _single(
                f"cross-kind:full:{label}",
                label,
                "full",
                target,
                "cross-kind",
                f"settings;competes={competes}",
            )
        )
    return Family((), tuple(files), tuple(files), tuple(queries))


def build_layout(inventory: list[App], dictionary: Path, seed: int = PUBLIC_SEED) -> Layout:
    base = [a for a in inventory if a.kind != "planted"]
    forbid = {w for a in base for w in normalize(a.name).split()}
    names = make_planted_names(seed, 60, dictionary, forbid)
    two_word, one_word = names[:30], names[30:]
    lower = [n.lower() for n in one_word[17:]]
    rng = random.Random(seed)
    taken: set[str] = set()
    planted_dev = two_word[:5] + one_word[:5]
    return Layout(
        {
            "planted-dev": Family(
                apps=tuple(planted_dev),
                queries=tuple(_app_queries(base, planted_dev, "planted-dev")),
            ),
            "stress-2x2": _stress_2x2(base, one_word[5:17]),
            "stress-two-word": Family(
                apps=tuple(two_word[5:8]),
                queries=tuple(
                    _app_queries(base, two_word[5:8], "stress-two-word", {"full", "nospace"})
                ),
            ),
            "stress-test-py": _stress_test_py(rng, lower[:2], taken),
            "folders": _folders(rng, lower[2:8], taken),
            "cross-kind": _cross_kind(base, dictionary, rng, taken),
        }
    )


def corpus_forbid(layout: Layout) -> set[str]:
    """Targeted strings the busy corpus must never contain."""
    out: set[str] = set()
    for fam in layout.families.values():
        for app in fam.apps:
            plain = app.replace(LRM, "").lower()
            out |= {plain, *plain.split()}
        for path in fam.decoys:
            out.add(PurePosixPath(path).name.lower())
        for q in fam.queries:
            if q.rule in ("full", "nospace", "punct_removed", "stem"):
                out.add(q.text)
            if q.intended is not None and q.intended.kind in ("file", "folder"):
                out.add(PurePosixPath(q.intended.id).name.lower())
    return out
