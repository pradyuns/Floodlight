"""Controls Tart clones of the benchmark VM and talks to them over SSH."""

import os
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SSH_SCRIPT = REPO / "scripts" / "vmssh.exp"
TART_HOME = Path(os.environ.get("TART_HOME", Path.home() / "VMs" / "tart"))
PASSWORD_FILE = Path.home() / ".config" / "floodlight-vm.local"
APP_QUERY = "kMDItemContentType == 'com.apple.application-bundle'"

SshFn = Callable[[str, float], str]


@dataclass(frozen=True)
class SettleResult:
    settled: bool
    count: int


def _tart(*args: str, timeout: float = 600) -> str:
    env = {**os.environ, "TART_HOME": str(TART_HOME)}
    result = subprocess.run(
        ["arch", "-arm64", "tart", *args], capture_output=True, text=True, timeout=timeout, env=env
    )
    if result.returncode != 0:
        raise RuntimeError(f"tart {' '.join(args)} failed: {result.stderr.strip()[-500:]}")
    return result.stdout.strip()


def _vm_password() -> str:
    from_env = os.environ.get("FLOODLIGHT_VM_PASSWORD")
    if from_env:
        return from_env
    if not PASSWORD_FILE.exists():
        raise RuntimeError(f"VM password missing: set FLOODLIGHT_VM_PASSWORD or {PASSWORD_FILE}")
    return PASSWORD_FILE.read_text().strip()


class VM:
    def __init__(
        self,
        name: str,
        base: str,
        ssh_fn: SshFn | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = name
        self.base = base
        self._ssh_fn = ssh_fn or self._real_ssh
        self._clock = clock
        self._sleep = sleep
        self._process: subprocess.Popen[bytes] | None = None

    def clone(self) -> None:
        _tart("clone", self.base, self.name)

    def run_argv(self, shares: dict[str, tuple[str, bool]] | None = None) -> list[str]:
        """`tart run` command line; shares map name -> (host path, read_only).

        Shared folders appear in the guest under /Volumes/My Shared Files/<name>.
        """
        dirs = [
            f"--dir={name}:{path}" + (":ro" if read_only else "")
            for name, (path, read_only) in (shares or {}).items()
        ]
        return ["arch", "-arm64", "tart", "run", "--no-graphics", *dirs, self.name]

    def start(
        self, boot_timeout_s: float = 300, shares: dict[str, tuple[str, bool]] | None = None
    ) -> None:
        env = {**os.environ, "TART_HOME": str(TART_HOME)}
        self._process = subprocess.Popen(
            self.run_argv(shares),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        deadline = self._clock() + boot_timeout_s
        while self._clock() < deadline:
            try:
                if self.ssh("echo ready", 20).strip().endswith("ready"):
                    return
            except (subprocess.SubprocessError, RuntimeError):
                pass
            self._sleep(5)
        raise TimeoutError(f"VM {self.name} did not accept SSH within {boot_timeout_s}s")

    def ip(self) -> str:
        return _tart("ip", "--wait", "60", self.name, timeout=90)

    def ssh(self, cmd: str, timeout: float = 120) -> str:
        return self._ssh_fn(cmd, timeout)

    def _real_ssh(self, cmd: str, timeout: float) -> str:
        env = {**os.environ, "FLOODLIGHT_VM_PASSWORD": _vm_password()}
        result = subprocess.run(
            ["expect", str(SSH_SCRIPT), self.ip(), cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(f"ssh failed ({result.returncode}): {result.stdout[-500:]}")
        return result.stdout

    def indexed_count(self, query: str = APP_QUERY) -> int:
        return int(self.ssh(f'mdfind -count "{query}"', 60).strip().splitlines()[-1])

    def indexed_paths(self, query: str = APP_QUERY) -> set[str]:
        return {line for line in self.ssh(f'mdfind "{query}"', 120).splitlines() if line}

    def wait_index_settled(
        self, timeout_s: float = 600, interval_s: float = 10, stable_checks: int = 3
    ) -> SettleResult:
        deadline = self._clock() + timeout_s
        history: list[int] = []
        while True:
            history.append(self.indexed_count())
            recent = history[-stable_checks:]
            if len(recent) == stable_checks and len(set(recent)) == 1:
                return SettleResult(settled=True, count=recent[-1])
            if self._clock() + interval_s > deadline:
                return SettleResult(settled=False, count=history[-1])
            self._sleep(interval_s)

    def destroy(self) -> None:
        if self._process is not None:
            _tart("stop", self.name)
            self._process.wait(timeout=120)
        _tart("delete", self.name)
