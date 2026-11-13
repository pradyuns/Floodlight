# Floodlight — project rules

A replacement for macOS Spotlight, plus a public, reproducible benchmark comparing
Spotlight, Raycast and this tool. **This repo is public.** Every commit must be safe to
publish.

## Privacy (check before every commit)
- Never commit personal paths, the user's name or username, hostnames, serials,
  installed-app inventories, or result titles from the user's real account.
- Files named `*.local.*`, `results/`, raw run data and recordings from the real account
  stay gitignored. Confirm with `git check-ignore` before the first commit of any new
  path.
- Published tables come only from the whitelisting export script: query id, rank,
  timings, row kind. No free-text titles.
- Before committing, review the full diff, including binary files (PDF metadata, PNG text
  chunks). Use the no-reply git identity. No AI or Claude attribution in commits or PRs.
- Never list, read, print or move hidden files or anything that looks like a key, token,
  `.env` or credential, including the hidden key files on the Desktop and Spotlight's
  `/.Spotlight-V100`. This also applies to subagents: repeat this rule in their prompts.

## Prove it works
- Never say "done" without evidence: the command you ran and its real output.
- Check the real thing (actual launcher rows, actual data values, actual video frames),
  not what you believe it shows.
- If you couldn't run or check something, say so. Don't guess.
- Work in small steps you can check one at a time, and commit after each one passes.

## Benchmark integrity
- **Lock before running.** The query list, answer key, scoring rules and analysis plan
  are committed, and their sha256 is recorded in `LOCK.txt` before any scored run. The
  runner refuses to run on a hash mismatch.
- **No edits after results.** Never edit queries or answers after seeing results. If one
  is truly wrong, stop, ask the user, and log it. Additions are flagged
  `added_after_lock`.
- **No tuning for one tool.** Never tune the matcher, labeler or scorer to make one tool
  look better. Every tool is read through the same observation channel.
- **Same setup for every tool.** Any preparation (history simulation, settings, warm-up)
  is done identically for every tool and written down.
- **Before a timed run:**
  - Write the claim you expect to report.
  - Check the machine: Spotlight not indexing, load from `uptime`, power and Low Power
    Mode, network and Siri Suggestions state.
  - Record the macOS build and tool versions in the run metadata.
- **Run the timed benchmark only when the user says go.**
- **Interleave tools.** Comparisons interleave tools query by query in a seeded,
  counterbalanced order (A, B, A, B for two tools; rotating orders for three), with at
  least 5 runs per tool. Report the median and the worst run, never a single run. Single
  smoke runs are labeled as such.
- **Statistics:** the app is the unit of analysis. Queries derived from the same app
  (prefixes, typos, no-space form) are not independent, so they are grouped by app.
  Report bootstrap confidence intervals that resample apps and paired comparisons
  between tools. Report run-to-run variation alongside every difference.
- **Verdicts:** based on the difference (our tool minus the other, in percentage points)
  and its paired 95% confidence interval. The ±5-point margin is fixed before any
  results.
  - Meaningfully better: the entire interval is above +5.
  - Meaningfully worse: the entire interval is below −5.
  - Practically similar: the entire interval is inside −5 to +5.
  - Inconclusive: anything else. Never call an inconclusive result "the same".
- **Explain every number before reporting it:**
  - What limited it?
  - Did the work actually happen inside the timed window?
  - Does it repeat across runs?
  - How big is the harness's own delay?
- **Surprises are bugs first.** Treat a surprising result as a bug until proven otherwise.
  Look at raw rows, screenshots and logs first.
- **Look at the data first.** Before trusting any metric, read the misses by hand and
  sort them into failure types (typo, prefix, recency, file vs. app, and so on). Publish
  the failure types alongside the scores.
- **Headline metrics stay tied to user frustration:** top-1 and wrong-Enter rate. Never
  invent a composite score.
- **Show where our tool loses.** Every comparison includes the queries and categories
  where our tool is worse than Spotlight or Raycast, with examples, given the same
  prominence as its wins.
- **Report format:** lead with a verdict (better, worse, no measurable difference,
  inconclusive). Raw data is never edited or deleted; reports are always rebuilt from it.

## Tests
- Test behavior, not implementation: assert what a user of the code would see.
- Never delete, skip or loosen a test to make it pass. Never special-case code to produce
  what a test expects.
- When fixing a bug, first add a test that fails without the fix.
- Run `ruff`, `mypy` and `pytest` (Python) and `swift build` plus the Swift tests before
  saying done.

## Swift
- Swift 6 strict concurrency, value types by default, no force-unwraps (especially on
  Accessibility reads), timeouts on Accessibility calls, a monotonic clock for timing, no
  third-party dependencies.

## Code
- Make the smallest change that solves the task. Prefer deleting code to adding it. No
  abstractions for a single use.
- No unrelated refactors or "while I'm here" cleanups. Remove dead code before building on
  top of it.
- Fix root causes: trace a symptom back to where it first went wrong.
- Validate inputs where data comes in (CLI args, config, accessibility or OCR reads,
  files), and trust the types inside.
- Fail loudly with useful messages. Never silently fall back to fake or default data. If
  the harness reads results by OCR instead of accessibility, the report header says so.
- Use types to rule out bad states (e.g. an enum for result source: local, web, instant).
- Don't invent APIs, flags or packages. Check the installed version or the docs, and ask
  before adding a dependency.
- **Ask before changing the system.** No installs, permission changes or system settings
  changes without asking first.
- **Before typing anything,** confirm the target launcher's process has its search window
  open and the search field is empty, and abort otherwise. (Spotlight's panel never
  becomes the frontmost app, so a frontmost-app check doesn't work.)

## Comments
- Default to no comments. Names and types should explain the code.
- Keep a comment only if the next agent would otherwise spend several tool calls figuring
  it out.
- Never put conversation, prompt or iteration history in comments, commits or docs.
- If a comment states a rule like "must run before X", turn it into a type, assertion or
  test instead.

## Repeated mistakes
- If the user corrects the same thing twice, encode it as a lint rule, type, assertion or
  test instead of just remembering it.

## Logging
- Add every decision and action to `docs/DECISIONS.local.md`: what, why, evidence, result.
- Keep `docs/PROGRESS.local.md` current: the readable summary of steps completed, decisions with
  their reasoning, and open items. Update it at the end of every task.
- End each task with what changed, why, what you tested (with output), and what you're
  unsure about.
