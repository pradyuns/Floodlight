# Floodlight vs Spotlight vs Raycast: Application Benchmark

## What was tested

Three macOS launchers (Spotlight, Raycast 2.12.1 and Floodlight) were given the same hidden set of
app-name queries inside a clean macOS 26.4.1 virtual machine with default settings and no usage
history. The queries were typed by a probe, and the top result was read through the accessibility
interface 5 times per query. The main comparison uses 209 queries for 40 invented apps planted in
the VM. The queries are of five kinds: full name, a 1–4 letter prefix, the name without spaces,
initials, and the name with one typo. The test rules, scoring and main comparison were fixed and
published before the runs. The hidden queries were committed to by a published hash (see
[Verifying the results](#verifying-the-results)).

## Result

**Floodlight was meaningfully better than Spotlight: +19.8 percentage points (likely range +18.7
to +20.9, a 95% confidence interval).** The rule, fixed before any results, counts a gap only if
even the low end of that range is above 5 points, and it is. **All of the difference comes from
queries with a typo; on correctly typed names, the tools tied.**

| Intended app shown first | Spotlight | Raycast | Floodlight |
|---|---|---|---|
| Correctly typed: full name, prefix, no-space, initials (169 queries) | 100% | 99.4% | 100% |
| One typo, invented app names (40 queries) | 0% | 27.5% | 100% |
| **Main result: all 209 queries, each app weighted equally** | **80.2%** | **84.9%** | **100%** |
| One typo, real app names (69 queries, reported separately) | 1.4% | 23.2% | 100% |

Every query got the same outcome in all 5 runs.

**Why the typo gap appears.** A minimal offline check was scored on the same queries:
- Given the list of app names in the VM, matching only exact names, prefixes and initials scores
  80.2%, exactly Spotlight's result.
- Adding acceptance of names one edit away (one letter added, removed, changed or swapped) raises
  it to 100%.

So the gap is explained by one-edit typo matching, a standard technique. This check is not a
launcher and not a model of Floodlight. It only picks a name from a list it is given. Floodlight
does its own discovery, indexing, ranking and launching, and was measured live in the VM. The
test shows typo recovery. It cannot show whether Floodlight's ranking does better than basic
matching.

## What this means

- **On correctly typed app names there is no meaningful difference.** The one exception is a
  Raycast initials query (`sf`), where Raycast put one of its own commands first.
- **On names with one typo, Floodlight found the app and Spotlight almost never did.**
  Spotlight showed only "search in Finder" and "search the web". Raycast recovered names with a
  missing letter, but not swapped or wrong letters.
- **This is a test of typo recovery, not of ranking in general.** One-edit matching alone
  accounts for the whole gap (see above).
- **A busy VM or a restart barely mattered.** With 200,000 extra files on disk, or right after
  restarting each launcher, results were nearly unchanged on matched queries: Spotlight changed
  one sample in each condition, and Raycast and Floodlight changed none ([appendix F](#f-busy-disk-and-restart-reported-separately)).
- **No speed claim.** Floodlight and Raycast had the intended app first about as early as each
  other. Spotlight was later and slowed steadily over the run (appendix).

## Limitations

1. **App searches only.** Files, folders and System Settings were not tested.
2. **Synthetic, single typos.** Each test typo has exactly one mistake and doesn't resemble
   another app's name. Harder cases were not tested, such as several mistakes in one query or a
   typo that matches a different app.
3. **Fresh installs in one VM.** No tool had usage history, so ranking by habit was not tested.
4. **No Enter key was pressed.** Results are the ranked list each tool showed, not the app that
   actually opened.

---

## Appendix

### A. How the main result is calculated

- **Weighting:** each planted app counts equally, whatever its number of queries. Apps have 4–7
  queries each, exactly one of them a typo.
- **Why it's 19.8 and not 19.1:** Spotlight's per-app score is (n − 1)/n. Averaging over apps
  gives the 19.8-point gap. Counting every query equally instead gives 19.1.
- **Statistics:** a paired bootstrap over apps (10,000 resamples).
- **Raw counts:** Spotlight 845, Raycast 895 and Floodlight 1045, each out of 1045 samples.
- **Other differences (descriptive):** Floodlight − Raycast +15.1 (CI +11.9 to +18.1). Raycast −
  Spotlight +4.7 (CI +2.0 to +7.5), which is inconclusive.
- **Validity checks, all passed:** no lost samples; no primary sample without a fresh final read.
- **Flagged samples:** five primary samples per tool came from blocks flagged for host load and
  were kept, as the selection rule requires.

### B. Typo misses, by kind of typo

Read by hand. Counts are hits out of queries, warm run, invented and real names together:

| Typo | Spotlight | Raycast | Floodlight |
|---|---|---|---|
| two neighbouring letters swapped (31) | 0 | 0 | 31 |
| one letter replaced by the next key on the keyboard (50) | 0 | 0 | 50 |
| one letter missing (28) | 1 | 27 | 28 |

On these misses the intended app was absent from every row the probe could read: Raycast's first
10, and all rows Spotlight and Floodlight exposed (at most 11 and 20). Rows further down were not
observed. This describes these queries only. It does not show that either product lacks typo
handling in general, and the study does not inspect how either product matches.

### C. Why one-edit matching explains the result

The hidden set hides the strings, not the kinds of queries:
- Practice and hidden queries use the same rule families.
- Invented names are kept far from real words, real apps and each other.
- A typo is rejected if it is close to another app's name.

This makes every typo unambiguous, which suits plain edit-distance matching. The hard cases
listed in the limitations are absent by design.

### D. Very short queries

The 1–2 letter queries can fit several apps, so they are scored separately. "The specific app
the generator had in mind" and "any app that fits" differ a lot here:
- For 1-letter queries, 40 queries share only 14 strings. No tool without context could get
  more than 35% "specific app first".
  - Floodlight and Spotlight: 7.5% specific, but **99.5% / 97.5% any fitting app**.
  - Raycast: 15% specific, 67.5% any fitting app. It often showed its own commands first.
- For 2-letter queries: Floodlight 100%, Spotlight 98.3%, Raycast 93.3% any fitting app.
- Across all ambiguous queries (warm / busy / restart), any fitting app first:
  - Floodlight 99.7 / 96.7 / 100;
  - Spotlight 97.2 / 96.7 / 95.0;
  - Raycast 77.5 / 83.3 / 75.0.

The offline check also gets 100% on "any fitting app", so this is not evidence of smarter
ranking either.

### E. Where Floodlight did worse or the outcome is unknown

- **No ranking error was observed for Floodlight on the unambiguous queries.**
- **4 Floodlight outcomes are unknown** (1 warm, 3 busy), all on 1–2 letter queries. No
  readable result arrived in the last 100 ms before the 3-second cutoff, so they count as
  non-hits. The other tools had observed hits on those same tries.
- **The riskier cases for a typo-correcting launcher were not tested,** such as opening the wrong
  app after a correction (see the limitations).

### F. Busy disk and restart (reported separately)

Each condition was run on its own random 25% of the queries and compared with the normal VM on
the same queries:

| Same queries, intended app first | Spotlight | Raycast | Floodlight |
|---|---|---|---|
| **Busy set (53 queries, 5 runs):** normal VM | 71.7% | 79.2% | 100% |
| Busy VM (200,000 extra files) | 71.3% | 79.2% | 100% |
| **Restart set (55 queries, 5 runs):** normal VM | 83.6% | 83.6% | 100% |
| Right after restarting the launcher | 83.3% | 83.6% | 100% |

Scores differ from the main set's 80.2% / 84.9% because each random draw has a different share
of typo queries: busy 15 of 53 (28%), restart 9 of 55 (16%), main set 19%. Within each set the
condition barely matters:
- In the busy VM, Spotlight changed one sample, a hit that became unknown.
- After a restart, Spotlight changed one sample: in one run it showed the typed text but no
  results for the full 3 seconds.
- Raycast and Floodlight changed nothing.

The pre-registered comparisons for these parts, Floodlight minus the other tool with each app
weighted equally:
- Busy: Floodlight − Spotlight +31.4 (CI +18.7 to +45.1); Floodlight − Raycast +24.2 (+12.1 to
  +38.4).
- Restart: Floodlight − Spotlight +19.0 (+8.4 to +31.2); Floodlight − Raycast +17.2 (+7.6 to
  +28.8).

The bigger busy gap reflects the typo-heavy query draw, not the files. How many of the extra files each tool actually indexed was not measured.

**The first restart run was stopped by a pre-set rule.** After about a quarter of the run,
Raycast was "not ready" in 10 of 217 tries (4.6%, limit 1%); no keys were typed in those tries.
Spotlight and Floodlight had no failures.
- **Cause:** Raycast's accessibility read stalled for about 2 seconds during the readiness check.
  Why, and whether a person would notice, was not established.
- **Fix (published first as Amendment 30):** the readiness check was changed the same way for
  all three tools, then tested on public queries.
- **Replacement run:** completed cleanly, 2608 of 2610 first tries delivered. The stopped run's
  data is released too.

Time to get ready after a restart (median / slowest), in the replacement run:
- Floodlight 1.2 / 4.7 s;
- Spotlight 4.2 / 4.7 s;
- Raycast 5.0 / 6.5 s. Raycast needed a second check in 141 of 435 tries.

None ever failed. This is the probe's restart procedure, not app-launch time.

### G. Timing

Time until the intended app was first, measured from the last keystroke (negative means it was
already first before typing finished). Only the 168 queries all three tools got right in every
run are included:

| Tool | Median | 95th percentile | Median in runs 1 → 5 |
|---|---|---|---|
| Floodlight | −105 ms | 49 ms | −93, −75, −106, −108, −111 |
| Raycast | −77 ms | 71 ms | −76, −77, −74, −68, −78 |
| Spotlight | 144 ms | 537 ms | 27, 94, 180, 274, 371 |

How to read this:
- **Spotlight slowed steadily during the run.** Why is not known.
- **Floodlight and Raycast differ by only 20–30 ms,** which is smaller than the probe's 50 ms
  sampling step.
- **It is partly a ranking measure:** a tool that ranks the app first at a shorter prefix scores
  earlier.
- **It is not screen latency or app-launch time.**

**Wrong app at Enter (estimated, 250 ms after the last key).** The probe takes the first result in
the latest read by 250 ms; no Enter was pressed. Raycast doesn't expose which row is highlighted,
so its first row is assumed. In Spotlight and Floodlight the highlighted row was always the first
whenever one was highlighted.

| | Wrong first result | No fresh read by 250 ms |
|---|---|---|
| Floodlight | 0 / 1045 | 0 |
| Raycast | 150 / 1045 | 0 |
| Spotlight | 165 / 1045 | 245 / 1045 |

So many of Spotlight's reads were missing that this is not a clean comparison.

### H. Data quality

| Run | Tries | Retried blocks | Lost samples |
|---|---|---|---|
| Warm (main) | 5488 for 5235 samples | 7 (host load) | 0 |
| Busy | 1305 for 1305 | 0 | 0 |
| Restart (replacement) | 2611 for 2610 | 0 | 0 |

- Every result row was identified, with no ambiguous identities.
- Unknown outcomes outside the main set: warm Floodlight 1; busy Spotlight 4, Floodlight 3;
  restart Spotlight 2.
- **Not done:**
  - the planned screen-recording check;
  - any real Enter press.

  The numbers are verified against the recorded data, not against what was on screen.

## Verifying the results

- **Fixed in advance:** the analysis plan, scoring and statistics were locked and published
  before the hidden runs.
- **Hidden queries:** they were committed to by the hash
  `2775ea5ff6212f3a168e545b4c9c2d2606df819c77f070b02c9bf65b11e8ba12` (commit `24a7289`), the
  SHA-256 of a random nonce followed by the query file.
- **Written afterwards:** the script that aggregates the raw results was written after the
  reveal and is tested. A second reviewer reproduced the main result independently.

The query file, nonce and per-sample results (no result titles) are in
[release/heldout-2026-11-18](../release/heldout-2026-11-18/README.md). Its README explains how to
check the hash and recompute the main result and the timing table. That re-checks the
statistics; it cannot re-score what the launchers showed, because raw result titles are not
released.

Published before the runs:
- the plan, scoring code and lock;
- Amendment 30 (commits `8832d48`, `3c44d30`).

Released with this report:
- the hidden query file and nonce;
- the per-sample data;
- the analysis, export, baseline and verification scripts, with their tests.
