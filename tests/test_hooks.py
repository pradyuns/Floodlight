import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / "scripts" / "hooks"
NOREPLY = "162063181+pradyuns@users.noreply.github.com"


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=check)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "tester")
    _git(tmp_path, "config", "user.email", NOREPLY)
    _git(tmp_path, "config", "core.hooksPath", str(HOOKS))
    (tmp_path / "a.txt").write_text("hello\n")
    _git(tmp_path, "add", "a.txt")
    return tmp_path


def _commit(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    return _git(repo, "commit", "-q", "-m", message, check=False)


def test_commit_with_noreply_email_and_clean_message_succeeds(repo: Path) -> None:
    assert _commit(repo, "feat: add a").returncode == 0


def test_commit_with_other_email_is_blocked(repo: Path) -> None:
    _git(repo, "config", "user.email", "someone@example.com")
    result = _commit(repo, "feat: add a")
    assert result.returncode != 0
    assert "no-reply" in result.stderr


@pytest.mark.parametrize(
    "message",
    [
        "feat: x\n\nCo-Authored-By: Someone <a@b.c>",
        "feat: written by Claude",
        "feat: thanks Anthropic",
        "feat: x\n\nGenerated with a tool",
        "feat: x <noreply@anthropic.com>",
    ],
)
def test_commit_message_with_ai_attribution_is_blocked(repo: Path, message: str) -> None:
    result = _commit(repo, message)
    assert result.returncode != 0
    assert "attribution" in result.stderr


def test_staged_personal_path_is_blocked(
    repo: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    patterns = tmp_path_factory.mktemp("cfg") / "scan.local"
    patterns.write_text("/Users/someone\n")
    (repo / "b.txt").write_text("path /Users/someone/x\n")
    _git(repo, "add", "b.txt")
    result = subprocess.run(
        ["git", "commit", "-q", "-m", "feat: b"],
        cwd=repo,
        capture_output=True,
        text=True,
        env={**_env(), "FLOODLIGHT_SCAN_PATTERNS": str(patterns)},
    )
    assert result.returncode != 0
    assert "personal pattern" in result.stderr


def _env() -> dict[str, str]:
    import os

    return dict(os.environ)
