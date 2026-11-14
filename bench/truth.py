"""Filesystem ground truth for file and folder identity: which paths with a given name exist in an
environment's declared search scope, listed from the guest filesystem (never from launcher
results or Spotlight's index)."""

import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from bench.model import Kind

SEARCH_SCOPE = ("/Users", "/Applications", "/System/Applications", "/Library", "/opt", "/usr/local")
# Never listed: hidden paths anywhere (including the index folders) and the user's private Library.
PRIVATE = ("/Users/bench/Library",)
_KINDS = {"f": Kind.FILE, "d": Kind.FOLDER}


@dataclass(frozen=True)
class GroundTruth:
    entries: frozenset[tuple[Kind, str]]

    @classmethod
    def from_find_output(cls, text: str) -> "GroundTruth":
        entries = set()
        for line in text.splitlines():
            if not line.strip():
                continue
            tag, _, path = line.partition(" ")
            if tag not in _KINDS or not path.startswith("/"):
                raise ValueError(f"bad ground-truth line: {line!r}")
            entries.add((_KINDS[tag], path))
        return cls(frozenset(entries))

    def candidates(self, kind: Kind, name: str) -> frozenset[str]:
        return frozenset(p for k, p in self.entries if k == kind and PurePosixPath(p).name == name)


def ground_truth_command(
    names: Iterable[str], roots: tuple[str, ...] = SEARCH_SCOPE, private: tuple[str, ...] = PRIVATE
) -> str:
    """Guest shell command printing 'f PATH' / 'd PATH' for each file or folder in names."""
    q = shlex.quote
    prune = " -o ".join(["-name '.*'", *(f"-path {q(p)}" for p in private)])
    wanted = " -o ".join(f"-name {q(n)}" for n in sorted(set(names)))
    return (
        f"find {' '.join(q(r) for r in roots)} \\( {prune} \\) -prune -o \\( {wanted} \\) "
        "\\( -type f -exec printf 'f %s\\n' {} + -o -type d -exec printf 'd %s\\n' {} + \\) "
        "2>/dev/null; true"
    )
