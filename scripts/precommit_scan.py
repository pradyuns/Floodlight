"""Blocks commits whose staged additions contain personal or secret-looking text.

Personal patterns (home path, hostname, real email, ...) live outside the repo in
~/.config/floodlight-scan.local, one per line, so the repo never contains them.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

KEY_LIKE: list[tuple[str, re.Pattern[str]]] = [
    ("private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("API secret key", re.compile(r"\bsk-[A-Za-z0-9_-]{32,}")),
]
LOCAL_ONLY = re.compile(r"\.local\.")
DEFAULT_PATTERNS_FILE = Path.home() / ".config" / "floodlight-scan.local"


def scan(text: str, patterns: list[str]) -> list[str]:
    findings: list[str] = []
    lowered = text.lower()
    findings += [f"personal pattern: {p}" for p in patterns if p.lower() in lowered]
    findings += [f"key-like: {name}" for name, rx in KEY_LIKE if rx.search(text)]
    return findings


def local_only_files(names: list[str]) -> list[str]:
    return [f"local-only file staged: {n}" for n in names if LOCAL_ONLY.search(Path(n).name)]


def load_patterns(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def staged_names() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, check=True
    ).stdout
    return [n for n in out.splitlines() if n]


def staged_additions() -> str:
    diff = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    added = [
        line[1:]
        for line in diff.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    return "\n".join(added)


def main() -> int:
    patterns_file = Path(os.environ.get("FLOODLIGHT_SCAN_PATTERNS", DEFAULT_PATTERNS_FILE))
    patterns = load_patterns(patterns_file)
    names = staged_names()
    findings = scan(staged_additions() + "\n" + "\n".join(names), patterns)
    findings += local_only_files(names)
    for finding in findings:
        print(f"BLOCKED by privacy scan: {finding}", file=sys.stderr)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
