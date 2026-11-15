"""Runs a schedule in a fresh clone, block by block, under the host-load policy.

Each block is one `probe run-schedule` call inside the guest. Host conditions are sampled
before and during every block; a flagged block is kept and retried per the policy, never cut
short. Every attempt is written to raw.jsonl; block conditions to blocks.jsonl."""

import hashlib
import json
import os
import shlex
import subprocess
import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from bench.delivery import quarter_gate
from bench.generate import Query
from bench.hostload import HostSample, Policy, evaluate, make_blocks, read_host_sample, should_retry
from bench.lock import verify_lock
from bench.runner import GUEST_SHARE, write_schedule
from bench.schedule import Slot
from bench.vm import VM

REPO = Path(__file__).resolve().parent.parent
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


def probe_digest(name: str, data: bytes) -> str:
    """Full sha256 of the probe binary; its file name must carry the first 12 hex digits."""
    full = hashlib.sha256(data).hexdigest()
    if name != f"probe-{full[:12]}":
        raise ValueError(f"probe file {name} does not match its contents (sha256 {full})")
    return full


class StopRuleError(RuntimeError):
    pass


class StuckToolError(RuntimeError):
    pass


def _stuck_tool(block: list[Slot], result_lines: list[str]) -> str | None:
    """A tool whose every sample in the block errored: the launcher is stuck, not flaky."""
    errors: dict[str, list[bool]] = {}
    for ln in result_lines:
        rec = json.loads(ln)
        errors.setdefault(rec["tool"], []).append(rec.get("error") is not None)
    for tool in sorted({s.tool for s in block}):
        if len(errors.get(tool, [])) >= 4 and all(errors[tool]):
            return tool
    return None


def errored_slots(block: list[Slot], result_lines: list[str]) -> list[Slot]:
    """Slots whose sample errored (or is missing), in their original order, for one requeue."""
    ok = set()
    for ln in result_lines:
        rec = json.loads(ln)
        if rec.get("error") is None:
            ok.add((rec["query_id"], rec["tool"], rec["run"], rec["condition"]))
    return [s for s in block if (s.query_id, s.tool, s.run, s.condition) not in ok]


def _wait_for_host(policy: Policy) -> float:
    """Waits up to the recovery period for the host to be within policy; returns seconds waited."""
    start = time.monotonic()
    while (
        evaluate([read_host_sample()], policy) and time.monotonic() - start < policy.recovery_wait_s
    ):
        time.sleep(policy.interval_s)
    return time.monotonic() - start


def probe_command(guest_io: str, name: str, result_name: str, pause_ms: int | None) -> str:
    pause = f"--settle-ms {pause_ms} " if pause_ms is not None else ""
    return (
        f"~/probe run-schedule {pause}--schedule {guest_io}/{name} "
        f"--out {guest_io}/{result_name} >/dev/null 2>&1; true"
    )


def check_block_pauses(blocks: list[list[Slot]], pauses: list[int]) -> None:
    if len(blocks) != len(pauses):
        raise ValueError(f"{len(blocks)} blocks but {len(pauses)} pauses")


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
    guest_ready_load1: float = 3.0,
    guest_ready_timeout_s: float = 1200,
    extra_meta: dict[str, str] | None = None,
    block_pause_ms: list[int] | None = None,
    stop_rule: bool = False,
) -> None:
    if require_lock:
        verify_lock(REPO)
    out_dir.mkdir(parents=True, exist_ok=False)
    awake = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
    io = out_dir / "io"
    io.mkdir()
    vm = VM(f"run-{out_dir.name}", snapshot)
    vm.clone()
    vm.start(shares={"run": (str(io), False)})

    def sh(cmd: str, timeout: float = 600) -> str:
        return vm.ssh(cmd, timeout)

    keep_vm = False

    try:
        settle = vm.wait_index_settled(timeout_s=900)
        t_guest = time.monotonic()
        while float(sh("sysctl -n vm.loadavg").split()[1]) >= guest_ready_load1:
            if time.monotonic() - t_guest > guest_ready_timeout_s:
                raise RuntimeError(f"guest load stayed >= {guest_ready_load1} after boot")
            time.sleep(15)
        guest_wait = round(time.monotonic() - t_guest)
        expected = probe_digest(probe, (REPO / "results" / "share" / probe).read_bytes())
        sh(f"curl -sf -o ~/probe {URL}/{probe} && chmod +x ~/probe && echo ok")
        in_guest = sh("shasum -a 256 ~/probe").split()[0]
        if in_guest != expected:
            raise RuntimeError(f"probe in guest has sha256 {in_guest}, expected {expected}")
        meta = {
            "label": label,
            "env": env,
            "snapshot": snapshot,
            "probe": probe,
            "probe_sha256": expected,
            "window_ms": window_ms,
            "policy": asdict(policy),
            "block_size": block_size,
            "macos": sh("sw_vers -productVersion; sw_vers -buildVersion").split(),
            "raycast": sh(
                "defaults read /Applications/Raycast.app/Contents/Info CFBundleShortVersionString"
            ).strip(),
            "index_settled": settle.settled,
            "guest_ready_load1": guest_ready_load1,
            "guest_ready_wait_s": guest_wait,
            "locked": require_lock,
            **(extra_meta or {}),
        }
        (out_dir / "meta.json").write_text(json.dumps(meta, indent=1) + "\n")
        raw = (out_dir / "raw.jsonl").open("a")
        recorded: list[dict[str, Any]] = []
        log = (out_dir / "blocks.jsonl").open("a")
        blocks = make_blocks(slots, block_size)
        if block_pause_ms is not None:
            check_block_pauses(blocks, block_pause_ms)
        queue = [(b, blk, 0, False) for b, blk in enumerate(blocks)]
        i = 0
        while i < len(queue):
            b, block, attempt, requeue = queue[i]
            i += 1
            waited = _wait_for_host(policy)
            name = f"sched-{b}-{attempt}.jsonl"
            result_name = f"result-{b}-{attempt}.jsonl"
            write_schedule(io / name, block, queries, window_ms)
            guest_load_before = sh("sysctl -n vm.loadavg").strip()
            started = time.monotonic()
            guest_io = shlex.quote(GUEST_SHARE)
            pause_ms = block_pause_ms[b] if block_pause_ms is not None else None
            with _Monitor(policy.interval_s) as mon:
                sh(
                    probe_command(guest_io, name, result_name, pause_ms),
                    timeout=60 * len(block) + 300,
                )
            result_file = io / result_name
            text = result_file.read_text() if result_file.exists() else ""
            lines = [ln for ln in text.splitlines() if ln.startswith("{")]
            reasons = evaluate(mon.samples, policy)
            for ln in lines:
                rec = json.loads(ln)
                rec.update(block=b, attempt=attempt, env=env)
                raw.write(json.dumps(rec) + "\n")
                recorded.append(rec)
            log.write(
                json.dumps(
                    {
                        "block": b,
                        "attempt": attempt,
                        "requeue_of_errors": requeue,
                        "pause_ms": pause_ms,
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
            stuck = _stuck_tool(block, lines)
            if stuck is not None:
                keep_vm = True
                raise StuckToolError(
                    f"{stuck} failed every sample in block {b}; VM {vm.name} kept for diagnosis"
                )
            if stop_rule and (breach := quarter_gate(slots, recorded)) is not None:
                keep_vm = True
                (out_dir / "stopped.txt").write_text(f"stop rule after block {b}: {breach}\n")
                raise StopRuleError(f"stop rule: {breach}; data kept, VM {vm.name} kept")
            if should_retry(attempt, bool(reasons), policy):
                time.sleep(policy.recovery_wait_s)
                queue.insert(i, (b, block, attempt + 1, requeue))
            elif not requeue and (errs := errored_slots(block, lines)):
                queue.insert(i, (b, errs, attempt + 1, True))
        raw.close()
        log.close()
    finally:
        if not keep_vm:
            vm.destroy()
        awake.terminate()
