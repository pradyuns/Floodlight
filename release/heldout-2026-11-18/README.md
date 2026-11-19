# Application Benchmark: data release (2026-11-18)

Public data for the final held-out comparison of Floodlight, Spotlight and Raycast. The report is
`docs/heldout-results.md`. The plan and scoring rules are in `docs/analysis-plan.md`, locked by
`LOCK.txt`.

## Files

- `heldout.json`: the held-out queries (synthetic) and the 40 invented planted app names.
- `nonce.bin`: random bytes for verifying the commitment. It is not a credential.
  sha256(nonce ‖ heldout.json) must equal the commitment in `LOCK.txt`, published before any
  held-out run (commit `24a7289`).
- One folder per run part:
  - `final-warm-20261116-1903` (primary);
  - `final-busy-20261117-1902`;
  - `final-restart-20261118-0857` (replacement, Amendment 30);
  - `final-restart-20261117-0232` (stopped under the stop rule; no scored samples).
- Each part folder contains:
  - `samples.jsonl`: one row per reported sample. Ids, rule, tool, run, condition, scores
    (Intended@1, Acceptable@1, wrong-Enter checkpoints, rank, timings) and the flagged label.
    No result titles.
  - `attempts.jsonl`: every attempt, with its delivery outcome, readiness preparation time and
    failed re-checks.
  - `blocks.jsonl`: per-block counts, duration, flagged state and flag reasons.
  - `meta.json`: VM image, macOS and Raycast versions, probe hash, commit and commitment.

## Check it

From the repository root, with the Python environment from `pyproject.toml`:

    python -m scripts.verify_public release/heldout-2026-11-18/heldout.json \
        release/heldout-2026-11-18/nonce.bin \
        release/heldout-2026-11-18/final-warm-20261116-1903/samples.jsonl

This verifies the commitment and prints the primary statistic: Floodlight − Spotlight +19.78
points, 95% CI +18.70 to +20.94. It also prints the matched-query timing table.
`python -m scripts.simple_matcher_control <heldout.json> <nonce.bin>` reruns the offline
matcher control.

**Limits of what this checks.** It re-aggregates the exported per-sample scores and recomputes
the statistics. It cannot rescore samples from what the launchers showed: raw accessibility
rows, including result titles, are not released. It cannot check the screen or Enter behaviour
either: no screen audit was done and no Enter was pressed.

## What the data contains

- Query ids encode app names: names from the declared public VM app inventory
  (`data/inventory-macos-26.4.1.json`) and the invented planted names, for example
  `heldout:typo:activity-monitor`. They contain no personal-machine titles or paths.
- `blocks.jsonl` keeps the flag reasons of 7 warm blocks. They are limited host-condition
  readings from the machine that ran the VM (for example "swap activity 1533 pages/s",
  "memory pressure level 2"). All other host monitor readings were removed.
