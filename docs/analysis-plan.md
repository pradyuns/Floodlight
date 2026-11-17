# Analysis plan

Public copy of the pre-registered measurement, metrics, statistics and lock rules (spec §6–§9) and the
v4.2 amendments (§13). Values set by the pilot are in "Pilot-derived settings" at the end. Locked in
LOCK.txt before any scored run.

## 6. Measurement
- **One observation channel:** an in-VM probe reads rows via the Accessibility API.
  - **Feasibility gate before any scored run:** app identity, file identity, the selected row, and
    timing must be readable for Spotlight and Raycast. Each tool's exact file-search interaction is
    documented.
  - If the gate fails: stop and ask. No silent OCR.
  - A sample of runs is checked against a screen recording; the disagreement rate is published.
- **Two typing modes:**
  - **Completed query:** type the query (e.g. `cal`), stop, then measure at checkpoints anchored to
    the last key of that query.
  - **Continuous typing:** the stepped `prefix-all` sequence (§4), to measure early appearance and
    result movement.
- **Input pacing (fixed, absolute):** 80 ms/key. It models a human, who doesn't slow down for a
  slow machine.
  - Input-delivery overhead (key posted → field shows the text) is measured per sample and reported
    separately.
  - Whether the VM delivers keys at a steady 80 ms is checked in the pilot.
- **Sampling:**
  - 50 ms sampling with real timestamps (monotonic clock), from the first key until 3 s after the
    query is completed. **No early stop.**
  - Settling is computed afterwards. The endpoint is the **final observed rank**; anything beyond
    the window is unknown.
  - A checkpoint uses the latest snapshot at or before it. If that snapshot is more than 100 ms
    old, the checkpoint is "unobserved" and reported as a rate.
- **Pilot (unscored, before lock):** if more than 2% of samples still change in the last 500 ms,
  lengthen the window.
- **Conditions:**
  - **UI restart:** kill the launcher UI process, then proceed when the readiness check passes.
    (Not "cold": the index and caches stay warm.)
  - **Warm:** an immediate repeat, kept as a pair with the UI-restart sample.
  - Optional, descriptive only: the first query after a fresh clone boots.
- **Runs:**
  - At least 5 per tool per query.
  - **Tool order:** seeded (seed 42) and counterbalanced.
    - Two tools: AB/BA alternating per query.
    - Three tools: cycle through all 6 orderings of {Spotlight, Raycast, Floodlight}, assigned per
      query by a seeded shuffle, so each tool is first, second and third equally often.
    - Each tool's UI-restart sample is immediately followed by its warm sample (a pair is never
      split).
  - A single-tool run is labeled baseline/smoke.
- **Run-time cap:** decided after the pilot and locked before any scored run.

## 7. Metrics
- **Primary comparison:**
  - Floodlight minus Spotlight on Intended@1.
  - Unambiguous queries only, final observed rank, all-rows view, UI-restart and warm averaged.
  - Dataset: held-out stratum (b) if the planted-dev gate passes, else stratum (a). This is chosen
    before the commitment.
  - Everything else is descriptive. Don't treat whichever secondary interval excludes zero as a
    confirmed win.
- **Headline set** (descriptive alongside the primary): Intended@1; wrong-Enter rate at 250 ms.
- **Safe Enter:**
  - Read from the selected row if it's readable. Outcomes: intended opens / another item activates
    / nothing launches.
  - Validated by real Enter presses on a sample, in throwaway clones only (pressing Enter trains
    history).
- **Also reported:**
  - Acceptable@1 and intended rank on ambiguous queries.
  - 1-letter queries as their own table.
  - Wrong-Enter at 500/1000 ms, and at 100 ms only if input overhead is under 25 ms.
  - MRR@10 of the intended item.
- **Simulated minimum keystrokes** (from `prefix-all`):
  - Smallest k with intended at #1, plus 1 for Enter.
  - Never-#1 rate reported separately.
  - Prefix stability: the share of longer prefixes where the item stays #1.
  - Labeled "simulated minimum".
- **Run stability:** the share of queries with the same #1 in all runs.
- **Latency:** p50/p95 time-to-intended-at-#1 over hits, with the miss rate separate, plus
  time-to-first-appear. Labeled VM-relative.
- **Views:** all rows and local-only. **No composite score.**

## 8. Statistics and reporting
- **Unit of analysis:** the app.
- **Weights:** average repeats per query; weight queries equally within an app, and apps equally.
  Exclusions are recorded. Query-weighted results are printed as a sensitivity check.
- **Comparisons:** paired percentage-point differences with a 10,000-resample app-cluster
  bootstrap, keeping tools paired. No sign test/McNemar by default.
- **Variability:** run-to-run variability is reported separately. A gap within it is "no
  measurable difference".
- **Breakdowns:** by rule type, query length (1, 2, 3, 4+), provenance and stratum.
- **Misses:** every miss is read and typed by stage (with evidence; unknown allowed). The
  failure-type table is published.
- **Report:**
  - Leads with a verdict.
  - Gives our tool's losses the same prominence as its wins.
  - Rebuilt from raw data only.
- **Publish:** the whitelisting export only (query id, rule, ranks, timings, row kind).

## 9. Lock and commitment
1. **Lock** before launcher work starts:
   - everything that affects query generation and scoring: generator, rules, inventory,
     accepted-set code, scoring/stats code and config, this analysis plan
   - stress and natural queries
   - Record sha256 in `LOCK.txt`; the runner refuses to run on a mismatch.
   - Probe, adapter and runner versions are recorded per run. Harness fixes and affected reruns
     are logged.
2. **Held-out commitment:**
   - The user runs one command with a secret seed file.
   - It writes the held-out file: canonical UTF-8 JSON with sorted keys, containing the typos of
     stratum (a), the planted names and queries of stratum (b), and the accepted sets.
   - A **separate** 32-byte random nonce file is written alongside.
   - It prints `sha256(nonce bytes ‖ held-out file bytes)`.
   - Held-out strings exclude every dev string.
   - Claude and Fable never see the seed, nonce or file.
3. **Publish the commitment:** push `LOCK.txt` + the commitment to the public repo before building
   the launcher.
4. **Before the final campaign:** push Floodlight's build hash (git commit + app sha256).
5. **Final campaign:** one campaign with preset repeats, all three tools, identical conditions.
   No tuning or reruns afterwards.
6. **Reveal:** the seed, nonce and file are revealed, and anyone can check the hash.
   - The report states the claim's limits:
     - Stratum (a) shows we didn't special-case known strings.
     - Stratum (b) covers newly installed, never-opened minimal apps (no icon, usage or App Store
       metadata) and is reported apart from built-ins.


## 13. Amendments (override earlier sections where they conflict)
Synthetic typing is deferred, outside Phase 1.

1. **§2 snapshot lineage:**
   - Order: `bench-clean` → `bench-tools` (third-party apps installed, never opened; Raycast;
     Floodlight) → `bench-busy` (plus corpus, index settled, then snapshotted).
   - Published per app: version, source URL, installer sha256, install method.
   - Installers are archived privately.
2. **§2 readiness:**
   - Index settled = indexed count stable over 3 checks 10 s apart, 10-minute timeout.
   - Targets still missing are coverage results, not errors.
3. **§3 Dev:** every built-in **and third-party** app, reported separately.
   - Third-party list frozen by a stated criterion before any results. Any selection bias is
     disclosed (e.g. WhatsApp chosen because it is a known Spotlight failure).
   - Tools under test (Raycast, Floodlight) are never intended targets, but count in acceptable
     sets.
4. **§3 new suites:**
   - **Collisions:** every prefix with two or more acceptable apps, generated mechanically.
     - Scored by Acceptable@1, plus a descriptive "which app each tool put first".
     - Any user-preferred answers are labeled "user preference" and never headline.
   - **Planted files/folders:** neutral name patterns with valid contents. Labeled patterns, not
     real-file performance. Floodlight v1 returns folders (item 16).
   - **Settings (item 15):** fixed labels mapped to pane identity; piloted first.
     - Unsupported is reported as unsupported.
     - Never in the app headline.
     - Settings-pane navigation is a Floodlight v1 requirement.
   - **Busy (item 17):** synthetic populated-Mac condition. Public seed, valid file contents,
     manifest summary published.
     - Indexed once and snapshotted, so each session starts settled.
     - All files share one creation day, which is stated.
     - Corpus size piloted at 50k/100k/200k small files and locked on resources, not on results.
     - Kept separate from targeted decoys.
     - "File count slows Spotlight" is a hypothesis, not a claim.
5. **§3 publication:**
   - Committed: generators, inventories, query manifests, corpus summaries.
   - Never committed: bundles, bulk corpus files, private data, unrevealed held-out output.
   - Held-out file, seed and nonce are published at reveal.
6. **§4 secret names:** 40 apps (20 one-word, 20 two-word). Dictionary is the guest's
   `/usr/share/dict/words`, with its sha256 recorded.
7. **§6 typing modes:**
   - **Completed query:** type, stop, measure.
   - **Continuous:** the full name at 80 ms/key with no pauses; measures early appearance and
     movement only.
   - **Stepped prefixes:** 1000 ms per key; simulated minimum keystrokes only; excluded from query
     weights.
   - **Deferred (not in Phase 1):** synthetic burst-and-correction typing. If revived: precomputed seeded
     schedules, seeded subset, run after the baseline.
   - **Timing origin:** the final key post; the field-shows-text time is also kept.
8. **§6 pilot:** run on Spotlight and Raycast.
   - If more than 2% of samples change in the last 500 ms, extend the window 3 → 4 → 5 s
     (maximum).
   - The window length is a runner setting.
9. **§7 primary:**
   - Sparse environment, completed-query mode.
   - Contributing rules: full, nospace, typo, unambiguous prefixN and initials.
   - Dataset: held-out stratum (b), else (a).
   - **Built-in + third-party combined 50/50 is a pre-declared secondary** (stratified
     bootstrap), not the primary. Reasons: only 12 clusters, and dev-rule queries are public and
     tunable.
   - Third-party typos join held-out stratum (a).
10. **§8 verdict rule:** difference = Floodlight minus
    the other tool in percentage points, with its paired 95% app-cluster bootstrap interval.
    The ±5-point margin is fixed now.
    - Meaningfully better: the entire interval is above +5.
    - Meaningfully worse: the entire interval is below −5.
    - Practically similar: the entire interval is inside −5 to +5.
    - Inconclusive: anything else. Never reported as "the same".
    - Run-to-run variability is reported alongside. Intervals do not correct for dev-set tuning.
11. **§9.2:**
    - Stratum (a) typos exclude every dev string.
    - Stratum (b) prefixes may coincide with dev strings; the overlap is reported.
12. **§9.5 final-campaign errors:**
    - Harness-error samples are retried up to twice; all attempts are kept.
    - Denominator: all scheduled samples.
    - The campaign is inconclusive if any tool keeps more than 5% errors, or error rates differ
      between tools by more than 2 points.
    - Both environments are declared in advance, and the build is frozen before either.
13. **Campaign matrix** (rough estimates at about 5 s/sample, before the pilot):

    | Campaign | Environment | Mode | History | Estimate |
    |---|---|---|---|---|
    | Dev, 3 tools × 5 runs | sparse | completed, warm | empty | ~10 h |
    | Dev, UI-restart pairs | sparse | completed, seeded 20% | empty | ~3 h |
    | Stepped prefixes | sparse | stepped | empty | ~3 h |
    | Dev subset 25% + stress + files | busy | completed, warm | empty | ~3 h |
    | Synthetic typing (optional) | sparse | 10% subset | empty | ~1 h |
    | Recency | sparse, own clones | completed | scripted | ~1 h |
    | Final held-out | sparse | completed, pairs | empty | ~11–14 h |
    | Final held-out | busy | completed, warm | empty | ~5 h |

    If the pilot shows this is too long, cut the held-out UI-restart pairs to a subset and make the
    primary warm-only. Decide before the commitment.
14. **Disk:**
    - Apps are about 6–8 GB (Docker Desktop, about 2 GB, is the first to drop) and the corpus
      1–3 GB.
    - Keep at least 5 GB free on both the host and the guest; the guest disk is 40 GB with about
      23 GB used.
    - Freeing host disk first is recommended.
15. **Settings suite:**
    - Added to §3 as a separate capability suite.
    - Opening System Settings panes is a **v1 requirement** for our launcher.
    - Labels and synonyms are declared before lock (e.g. wifi / wi-fi, bluetooth, display /
      displays, battery).
    - Success = the named pane opens; nothing is toggled.
    - Pane identity readability is piloted first. Unsupported is reported as unsupported.
    - Never in the app headline.
16. **Folders:**
    - Our launcher returns folders in v1, and must improve on Spotlight's folder results.
    - A planted neutral folder suite (e.g. `abc-101/`, nested project folders) with
      human-written and model-written queries.
    - Scored with the file rules (name + parent folder shown).
17. **Decisions:**
    - **Name:** Floodlight.
    - **Busy Mac:** yes.
    - **Third-party apps** (installed from official, signature-verified downloads; never opened):
      Google Chrome, Firefox, Spotify, Slack, Discord, WhatsApp, Visual Studio Code, Obsidian,
      iTerm2, Telegram, VLC, Rectangle.
    - **Selection criterion, as published:** common apps with a small disk footprint and natural
      name collisions with built-ins. WhatsApp was also chosen because it is a known Spotlight
      failure, which is disclosed.
18. **Consistency pass (2026-11-13):**
    - Frontmost-app check removed everywhere; the readiness check (§2) is the rule.
    - Three-tool counterbalanced order defined (§6).
    - The final campaign's run-time budget is set after the pilot of both competitors and fixed
      before the commitment.
19. **§5 short-query rule (2026-11-13; replaces the prefix/initials bullets in §5):** every short
    query (prefixN, initials, and collision prefixes) uses one mechanical rule.
    - **Acceptable:** any app with a word starting with the query, or whose initials equal it.
    - The same string therefore always has the same acceptable set, whatever rule produced it.
    - **Intended:** the source app, kept for descriptive intended-rank reporting.
    - Full-name, no-space and typo queries keep intended-only.
    - Collision candidates include every multi-word app's initials.
    - Ambiguity counts are recomputed now and again after third-party apps are installed.
      Built-ins only: 429 dev queries, 150 ambiguous, 279 unambiguous; 69 collision strings.
    - After third-party apps (2026-11-13): 502 dev queries, 171 ambiguous, 331 unambiguous;
      74 collision strings; 78 stepped sequences.
20. **Environment and Raycast protocol (2026-11-13; overrides §2 snapshot lineage and §6 where they
    conflict):**
    - **VM resize:** the main container was too full for Spotlight to index (lowDiskSpace, read-only
      index). From recoveryOS the separate Recovery partition was removed and the container grown
      to 49.5 GB (Tart FAQ procedure). SIP stayed enabled throughout; the paired Recovery volume
      remains. Disclosed in the environment notes. macOS updates may not work in this VM (pinned).
    - **Snapshot lineage:** bench-clean-2026-11-12 → bench-tools-2026-11-13 (13 apps) →
      bench-resized-2026-11-13 (resize only) → **bench-ready-2026-11-13** (Raycast set up). Every
      sparse and busy environment is cloned from bench-ready.
    - **Raycast 2.12.1.0 setup:** no sign-in; hotkey Option+Space; Spotlight's Cmd+Space kept; all
      settings default ("Include Files in Root Search" is on by default); file access granted to
      Desktop, Documents, Downloads and Music via macOS prompts; starts at login.
    - **Raycast interaction:** main bar for every suite (same type-then-Enter as Spotlight).
    - **Raycast highlighted row:** not exposed via Accessibility. Enter is scored as the top row,
      checked on every snapshot against the Enter-button label; disagreements are counted as
      `highlight_mismatch`; plus the screen-recording sample audit for every tool.
    - **Raycast rows:** only the top 10 are read (⌘-number hints delimit rows).
    - **Raycast coverage:** no index-settled signal; before runs, planted canaries must be found.
      Busy-corpus reports state each tool's indexed coverage, including folders Raycast ignores
      by default (caches, temp, node_modules, Application Support).
    - **Checkpoints:** 100 ms is kept. Harness overhead measured via Raycast ≈19 ms median (<25 ms
      rule); Spotlight's ~190 ms key-to-field delay is Spotlight's own behavior.
21. **Floodlight ranking principle:** match strength comes first; apps are
    preferred only among equally strong matches. A weak app match (e.g. a prefix) never displaces an
    exact filename match or an explicit settings query. Apps-first applies to the benchmark headline
    (the app suite), not to cross-kind ranking.
    - **Cross-kind stress set (Task 6, public, labeled, never headline):** queries where an exact file
      name or settings label competes with a weaker app match; reported per tool so an
      "apps always win" ranker shows up as a loss.
22. **Measurement rules and environment (overrides §6 where they conflict):**
    - **Timing:** checkpoints anchor to the final key's actual post time; each snapshot is known at
      its read-finish; a checkpoint with no finished read whose start is within 100 ms is
      "unobserved" (strict rule: a later read never fills an earlier ranking
      checkpoint). 100/250 ms are reported with their unobserved rates; 500/1000 ms kept; final
      Intended@1 stays primary. What Enter opens is tested separately (§7 Safe Enter).
    - **Keys** are posted on their own real-time thread; a key > 10 ms late makes the sample a
      harness error (`key_post_late`).
    - **Field readings that don't match what was typed** are kept as flagged snapshots
      (`field_mismatch`), never scored.
    - **Snapshot:** `bench-ready-2026-11-14` = bench-ready-2026-11-13 + display sleep, system sleep
      and screen lock off (the VM locked after 10 idle minutes, sending keys to the lock screen).
      The probe refuses to run on a locked screen (`screen_locked`).
23. **File and folder identity:** a result showing its full parent path is identified by it. One
    showing only the parent folder's name, or no location, counts as the target only when the
    environment's filesystem ground truth (a `find` over the declared scope: /Users,
    /Applications, /System/Applications, /Library, /opt, /usr/local; hidden paths and the user's
    Library excluded; never launcher results or the index) has no other path it could be.
    Otherwise it is **unresolved**: not a hit, not a wrong Enter, not a coverage miss.
    Unresolved samples stay in every denominator; top-1 is reported as hit / miss / unresolved
    shares, and the unresolved rate is published per tool. Ground truth is captured per
    environment once its contents are final.
24. **Settings targets:** the panes System Settings itself shows in the bench VM (read from its
    sidebar), with reasons for catalog panes it doesn't show (data/settings-panes-macos-26.4.1.json).
    Never selected by whether a launcher finds them. "battery" is not applicable in the VM (no
    battery; System Settings shows Energy); "energy" targets the Energy pane.
25. **Natural queries:** model-written (reviewed) and human-written queries are labelled by
    provenance and reported separately. Hyphen-free folder queries are labelled `punct_removed`,
    each next to its exact-name control.
26. **Busy environment:** 200k files (public seed 1114), chosen on resources only; Downloads and
    Desktop hold fixed shares (10%, 2%) of document files; one creation day. Every fixture clone
    is restarted after planting, and every planted app must be listed by both tools before any
    query (steady-state scope; live-install refresh is not measured, and Raycast's missed live
    installs are reported as a separate observation).
27. **Host-load policy:** light host use is allowed. Monitored every 5 s: host and guest load,
    memory pressure level, swap-in/out *rates* (not swap used), power source, Low Power Mode;
    each sample block stores its conditions. A crossing never interrupts a sample; the block is
    kept, flagged and retried by a fixed rule that preserves tool pairing and the restart/warm
    structure; every attempt is retained. Thresholds, recovery wait and retry limit are set from
    the pilot's resource and read-reliability measurements (never from which values favour a
    tool) and locked below. Interleaving reduces, but does not rule out, background effects. The
    first block starts only after the guest's 1-minute load is below 3.0. Reported as "ran under
    a monitored host-load policy allowing light use".
28. **Amendment 1 (2026-11-15, after the first dev baseline; overrides earlier sections where they
    conflict).** Hand review of the first dev baseline found measurement defects. That run, its
    lock and its raw data are kept unchanged as a labelled diagnostic and are not reported as a
    comparison.
    - **Read states:** each read of the search field is readable text (possibly empty) or
      unreadable, with its reason; a failed row read is unreadable too. An unreadable read is an
      observation failure, never an empty result, and never counts as "ready to type".
    - **Read budget:** one whole read (field, rows, Enter label) must finish within 150 ms. Every
      accessibility call gets only the time left; a read that runs out is unreadable
      ("deadline") and its partial rows are discarded.
    - **Final freshness:** the final outcome comes from a readable read that started at least
      2.9 s and finished by 3.0 s after the final key. A later read never fills the gap. Without
      one, the outcome is unobserved: kept in the denominator with its own rate per tool, distinct
      from unresolved identity. Early checkpoints keep their 100 ms rule and report their own
      unobserved rates.
    - **Observability gate:** the final Intended@1 comparison is inconclusive on observability if
      any tool's unobserved rate exceeds 5% of scheduled samples, or the tools differ by more
      than 2 points. The limits are not loosened to obtain a verdict.
    - **Retries (supersedes item 12's "up to twice"):** an errored or missing sample is run once
      more, right after its block; a host-load-flagged block is retried up to 2 times (separate
      rule). The reported sample is the first attempt that is neither errored nor in a flagged
      block; if every clean attempt was flagged, the last clean one, labelled flagged; a slot with
      no clean attempt is a kept error. All attempts are kept; first-attempt and after-retry error
      rates are both reported.
    - **Dropped keys:** a dropped key is counted only when a readable field shows text other than
      what was typed. First-attempt drop rates are reported per tool and per quarter of each
      campaign.
    - **App identity:** an app row matches its target by the target's inventory name or by any
      name from the app's own bundle (Info.plist display and bundle names, English
      localizations), read in the bench VM (guest locale en_US, languages en-US) and stored with
      its source in `data/app-aliases-macos-26.4.1.json`. Only rows of kind app can match, and
      every alias must map to exactly one app in the declared inventory (a shared name is
      refused).
      Queries and intended apps are unchanged. A tool showing a name from another localization
      than the guest's (e.g. "Print Centre" on en-US) is reported as an observation.
    - **Pause before typing:** the same fixed pause between "ready" and the first key for every
      tool, chosen from 0/150/300/500 ms by an unscored, counterbalanced input-delivery
      calibration (shortest pause at which, for every tool, observed first-try drops are ≤ 0.5%
      and unverified first tries — not ready, unreadable, timed out — are ≤ 1%; if none
      qualifies, none is chosen), then checked during the scored rerun itself by the stop rule
      below (no separate endurance run). Chosen on delivery only, never on ranking. Timing
      stays anchored to actual key posts; the pause is recorded separately.
    - **Stop rule for scored runs:** each tool's scheduled slots are split into quarters in run
      order. Once a quarter's slots have all been reached, its first attempts (retries excluded)
      must show ≤ 1% confirmed drops and ≤ 1% unverified tries (not ready, unreadable, timed out,
      missing), and its drop rate may not exceed quarter 1's by more than 1 point. A breach stops
      the run at the next block boundary; all data and the VM are kept and the cause diagnosed.
      Any fix gets a new published lock and a separately authorized rerun; unchanged runs are
      never repeated until one passes. The pause and rules never change during a run. All four
      quarters' counts and rates are reported; passing means meeting this operational gate.
    - **Calibration result (2026-11-15, unscored, probe `e3e18537995d`):** 320 first tries per
      tool per pause. Confirmed drops: Raycast 1 at 0 ms, none otherwise; Spotlight none.
      Unverified (Spotlight; Raycast none): 1.25% at 0 ms, 1.88% at 150, 0.94% at 300, 0.31% at
      500. Chosen: **300 ms** (also 300 ms with the battery-powered blocks excluded, Spotlight at
      1.00%). A follow-up unscored check with the 3 s window (160 per tool, 300 ms) found 0%
      unobserved at the final cutoff for both tools; Spotlight's over-budget reads all fell in the
      first second after the final key.
    - **Power source (overrides item 27 and the locked host-load policy):** running on battery is
      recorded for every block but no longer flags or retries it; Low Power Mode, load, memory
      pressure and swap still flag. Applies from the dev baseline rerun onward; reports state
      that runs were allowed on battery.
29. **Amendment 2 (2026-11-16): Floodlight joins, and the final held-out campaign (overrides earlier
    sections where they conflict).**
    - **Same observation channel.** Floodlight is read by the same probe, timing, 150 ms read
      budget, 300 ms pause, 3 s window, freshness rules and gates as Spotlight and Raycast (item 28).
      Adapter `probe/Sources/ProbeCore/Floodlight.swift`: field = text field with accessibility id
      `floodlight.search`; rows = table `floodlight.results`, each row's texts are title, parent
      folder (files and folders only) and kind label; the selected row is exposed directly. Opened
      with Control-Space; ready = field present and empty. Floodlight shows at most 20 rows; each
      tool is read as it shows itself.
    - **Frozen build.** `bench/final.py` pins `FLOODLIGHT_SHA256` and `FINAL_PROBE` (see
      "Measurement binary"). The runner refuses any other probe, and checks the Floodlight binary's
      sha256 inside the guest before any sample. Floodlight does not change until the final campaign is finished.
    - **Snapshots.** `bench-final-sparse-2026-11-16` = `bench-ready-2026-11-14b` and
      `bench-final-busy-2026-11-16` = `bench-busy-2026-11-14b`, each plus Floodlight in
      /Applications started at login, with its Desktop/Documents/Downloads access granted once
      (as for Raycast). Spotlight and Raycast state is unchanged; Floodlight starts with no usage
      history.
    - **Planting the secret apps (inside each final run).** Names reach the guest only through a
      share file deleted right after planting; only counts are printed. Wait until Spotlight has
      indexed every planted app (10 min limit), then reboot so every launcher starts with them
      present. Before any query, every tool must list every planted app as an app (see
      "Readiness tries"), or the run stops.
    - **Campaign parts** (three tools, 5 runs, schedule seed 42, rotation of all 6 tool orders):
      `final-warm` = all 349 held-out queries, sparse, warm (**primary**); `final-restart` = a
      seeded 25% subset, sparse, UI-restart + warm pairs (secondary); `final-busy` = a seeded 25%
      subset with its own seed tag, busy, warm (additional check). Subsets are drawn with
      `random.Random("2026:<part>")` from the sorted held-out ids. Stop rule, host policy and
      retries as item 28, applied per part.
    - **Primary reading.** Floodlight minus Spotlight, Intended@1, unambiguous queries, stratum (b)
      if the planted-dev gate passes (else (a)), app-weighted, paired app-cluster bootstrap, ±5
      points. Per the "Final held-out campaign budget" decision, the primary uses the warm
      condition only; §7's "UI-restart and warm averaged" no longer applies. UI-restart results
      are secondary.
    - **Safe Enter gap.** §7's validation of Safe Enter by real Enter presses in throwaway clones
      was not built. Safe Enter and wrong-Enter are therefore **proxies**: what Enter would open,
      read from the selected row (Spotlight, Floodlight) or the top row (Raycast), never an
      observed launch or an observed "nothing launches". Every table, figure and sentence names
      them "wrong-Enter (selected-row proxy)" and "Safe Enter (selected-row proxy)", including
      the `wrong_enter_*` export columns. Wrong-Enter at 250 ms stays in the headline set under
      that name; Intended@1 stays primary.
    - **Primary stratum, fixed before the campaign.** The public planted-dev gate passed for
      Spotlight and Raycast (2026-11-14). Floodlight's planted-dev check runs on the final
      snapshot before any held-out run. Its outcome and the resulting primary stratum ((b) if it
      passes, else (a)) are recorded in the freeze checklist and published before the campaign
      starts; the choice is never made at reporting time.
    - **Planter frozen.** `fixtures/make_planted.sh` and `fixtures/planted_main.c` are locked;
      `bench/final.py` pins the sha256 of the staged script and compiled stub (`PLANTER_SHA256`).
      The guest deletes any old copies, downloads both, and the runner verifies both hashes
      before planting; a mismatch stops the run.
    - **Readiness tries.** Each tool gets up to 3 reads per planted app (10 s apart); a read
      only counts once it lists the app. After 3 reads without it, the run stops (counts only).
    - **Development evidence (descriptive, tuned, not a result).** Floodlight was developed against
      the public dev queries. An unlocked Floodlight-only rehearsal on the dev set (5 runs, same
      harness, commit `a8066e6`, this probe and build) had 0 kept errors, 0 dropped or unverified
      keys, 0 flagged blocks, and Intended@1 of 99.7% on unambiguous queries. This is tuned
      development performance from a different session than the Spotlight/Raycast dev baseline
      and supports no comparative claim; only the held-out campaign does.
    - **Secrecy.** The final command prints counts and the commitment check only; raw results stay
      out of the repo until the reveal. No tuning or reruns after any final result.

## Pilot-derived settings (from the unscored pilot, 2026-11-14)
Pilot data: 240 samples sparse (restart + warm), 180 busy (warm), 120 sparse during light host use;
30 dev queries, Spotlight and Raycast, 5 s window. Two invalid pilot runs are kept and labelled (one
on battery, one stopped when Spotlight stopped opening after UI restarts on the busy snapshot).

- **Checkpoints:** input overhead (final key to the field showing it) was median 27-34 ms
  (Raycast) and 55-83 ms (Spotlight), p95 up to ~370 ms. Spotlight's 100 ms checkpoint was
  unobserved in 41-71% of samples and 250 ms in 23-54%. Both checkpoints are kept as descriptive
  measures, always reported with their unobserved rates, never as headline metrics. Final
  Intended@1 stays primary.
- **Late-change window:** 3 s. No sample in the valid pilot runs changed its top result after
  3 s (0 of 540). The window stays 3 s.
- **Errors:** Spotlight 0/270, Raycast 3/270 in valid runs (field never showed the typed text, or
  launcher not ready). Errored or missing samples are run once more right after their block, in
  their original order; all attempts are kept.
- **Time per sample:** 7.5 s (sparse, restart + warm), 6.5 s (busy, warm-only); the guest needs
  about 200-230 s to settle after boot.
- **Busy environment is warm-only** (campaign matrix item 13); UI-restart pairs run on sparse only.
- **Baseline order (Spotlight vs Raycast, 5 runs each):** (1) dev, sparse, warm; (2) dev
  UI-restart pairs on a seeded 20% subset, sparse; (3) natural (apps and settings), sparse, warm;
  (4) dev 25% subset, busy, warm; (5) fixture suites (stress, folders, cross-kind) in their
  planted clones once planting runs inside the campaign driver.
- **Final held-out campaign budget:** primary warm-only; UI-restart pairs on a seeded 25% subset
  (decided before the commitment, per item 13).
- **Host-load policy:** every valid run stayed at memory pressure level 1, host 1-min load at most
  9.1 (the VM itself accounts for about 3-5), swap activity at most 87 pages/s. The run that went
  bad showed pressure level 2 and a 7,720 pages/s swap burst. Locked values:
  - sampling interval 5 s
  - flag when host 1-min load > 10.0
  - flag when memory pressure level > 1 (warning or critical)
  - flag when swap-in + swap-out > 500 pages/s between samples
  - flag when on battery or Low Power Mode is on
  - before each block, wait up to 120 s for the host to be within policy
  - a flagged block is retried up to 2 times; the first unflagged attempt is used; if every
    attempt is flagged, the last attempt is used and labelled flagged; every attempt stays in the
    raw data and the flagged-block rate is reported per tool
  - guest 1-min load < 3.0 before the first block
  - light use measured in the pilot (browsing, a video) stayed within these limits

## Held-out commitment
- Commitment (sha256 of nonce ‖ held-out file): `2775ea5ff6212f3a168e545b4c9c2d2606df819c77f070b02c9bf65b11e8ba12`
- Counts: stratum (a) 69 typo queries; stratum (b) 280 queries over 40 secret planted apps, of
  which 22 coincide with public query strings (allowed and reported).
- Secret-name dictionary: `/usr/share/dict/words`, sha256
  `be41ad97963bf8dabedd5871d5d691596175269d540956b0f9965a885c2bbab9` (identical in the guest).

## Measurement binary
- The probe's Swift sources are locked with everything else. Every scored run uses the binary built
  from them: sha256 `e3e18537995dc73666a8d19aa19b7ca54e8896cc7544aa5c344369666830ba17`
  (staged as `probe-e3e18537995d`; amendment 28). The first dev baseline used the earlier
  binary `6fa42c2a7df252dff15033099bb4a4ef0d88131477e8b6fef2e32dcc3624a54e` under the previous
  lock and is kept only as a labelled diagnostic. Before any sample, the runner checks the full sha256 of the
  binary inside the guest and refuses on a mismatch; the hash is stored in each run's metadata.
- Baselines are launched with `python -m bench baseline --campaign NAME --probe NAME`, which
  refuses unless the working tree is clean and HEAD is the pushed commit (recorded per run), and
  always uses the locked host-load policy and lock verification. Seeds: schedule 42, subsets 2026. A harness fix after the lock is
  a logged amendment with a new lock, and every affected run is redone.
- Final campaign (item 29): probe sha256
  `74220bbf4463475b841f6d9f2cc5e76e99d7202928a1e96fc2656e0d0d07b1bb` (staged as
  `probe-74220bbf4463`); Floodlight binary (`Floodlight.app/Contents/MacOS/Floodlight`, built by
  `scripts/build_floodlight.sh` at commit `a8066e6`) sha256
  `4c9bb50015a98ea88bd116116309d34a55041fa6df5b7465ed13c8e667826661`.
