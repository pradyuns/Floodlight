"""Runs a schedule in a fresh clone, block by block, under the host-load policy.

Each block is one `probe run-schedule` call inside the guest. Host conditions are sampled
before and during every block; a flagged block is kept and retried per the policy, never cut
short. Every attempt is written to raw.jsonl; block conditions to blocks.jsonl."""

import json
import os
import shlex
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from bench.generate import Query
from bench.hostload import HostSample, Policy, evaluate, make_blocks, read_host_sample, should_retry
from bench.lock import verify_lock
from bench.runner import write_schedule
from bench.schedule import Slot
from bench.vm import VM

REPO = Path(__file__).resolve().parent.parent
SHARE = REPO / "results" / "share"
URL = "http://192.168.64.1:8765"
RECORD_ONLY = Policy(
    interval_s=5,
    max_load1=float("inf"),
    max_pressure_level=99,
    max_swap_pages_per_s=float("inf"),
    recovery_wait_s=0,
    max_retries=0,
)


class _Monitor:
    def __init__(self, interval_s: float) -> None:
        self.samples: list[HostSample] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, args=(interval_s,), daemon=True)

    def _loop(self, interval_s: float) -> None:
        while not self._stop.is_set():
            self.samples.append(read_host_sample())
            self._stop.wait(interval_s)

    def __enter__(self) -> "_Monitor":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        self._thread.join()
        self.samples.append(read_host_sample())


def _wait_for_host(policy: Policy) -> float:
    """Waits up to the recovery period for the host to be within policy; returns seconds waited."""
    start = time.monotonic()
    while (
        evaluate([read_host_sample()], policy) and time.monotonic() - start < policy.recovery_wait_s
    ):
        time.sleep(policy.interval_s)
    return time.monotonic() - start


def run_campaign(
    *,
    snapshot: str,
    env: Literal["sparse", "busy"],
    queries: dict[str, Query],
    slots: list[Slot],
    probe: str,
    out_dir: Path,
    label: str,
    policy: Policy = RECORD_ONLY,
    block_size: int = 40,
    window_ms: int = 3000,
    require_lock: bool = True,
) -> None:
    if require_lock:
        verify_lock(REPO)
    out_dir.mkdir(parents=True, exist_ok=False)
    awake = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    vm = VM(f"run-{out_dir.name}", snapshot)
    vm.clone()
    vm.start()

    def sh(cmd: str, timeout: float = 600) -> str:
        return vm.ssh(cmd, timeout)

    try:
        settle = vm.wait_index_settled(timeout_s=900)
        sh(f"curl -sf -o ~/probe {URL}/{probe} && chmod +x ~/probe && echo ok")
        meta = {
            "label": label,
            "env": env,
            "snapshot": snapshot,
            "probe": probe,
            "window_ms": window_ms,
            "policy": asdict(policy),
            "block_size": block_size,
            "macos": sh("sw_vers -productVersion; sw_vers -buildVersion").split(),
            "raycast": sh(
                "defaults read /Applications/Raycast.app/Contents/Info CFBundleShortVersionString"
            ).strip(),
            "index_settled": settle.settled,
            "locked": require_lock,
        }
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        raw = (out_dir / "raw.jsonl").open("a")
        log = (out_dir / "blocks.jsonl").open("a")
        for b, block in enumerate(make_blocks(slots, block_size)):
            attempt = 0
            while True:
                waited = _wait_for_host(policy)
                name = f"sched-{out_dir.name}-{b}-{attempt}.jsonl"
                write_schedule(SHARE / name, block, queries, window_ms)
                guest_load_before = sh("sysctl -n vm.loadavg").strip()
                started = time.monotonic()
                with _Monitor(policy.interval_s) as mon:
                    out = sh(
                        f"curl -sf -o /tmp/s.jsonl {URL}/{shlex.quote(name)} && "
                        "~/probe run-schedule --schedule /tmp/s.jsonl --out /tmp/r.jsonl "
                        ">/dev/null 2>&1; cat /tmp/r.jsonl",
                        timeout=60 * len(block) + 300,
                    )
                lines = [ln for ln in out.splitlines() if ln.startswith("{")]
                reasons = evaluate(mon.samples, policy)
                for ln in lines:
                    rec = json.loads(ln)
                    rec.update(block=b, attempt=attempt, env=env)
                    raw.write(json.dumps(rec) + "\n")
                log.write(
                    json.dumps(
                        {
                            "block": b,
                            "attempt": attempt,
                            "slots": len(block),
                            "results": len(lines),
                            "secs": round(time.monotonic() - started, 1),
                            "waited_before_s": round(waited, 1),
                            "guest_load_before": guest_load_before,
                            "guest_load_after": sh("sysctl -n vm.loadavg").strip(),
                            "flagged": bool(reasons),
                            "reasons": sorted(set(reasons)),
                            "host": [asdict(s) for s in mon.samples],
                        }
                    )
                    + "\n"
                )
                raw.flush()
                log.flush()
                (SHARE / name).unlink(missing_ok=True)
                if not should_retry(attempt, bool(reasons), policy):
                    break
                attempt += 1
                time.sleep(policy.recovery_wait_s)
        raw.close()
        log.close()
    finally:
        vm.destroy()
        awake.terminate()
