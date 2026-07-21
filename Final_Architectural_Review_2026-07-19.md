---
title: Final Architectural Review — Research Lab / weather-pipeline
date: 2026-07-19
reviewer: Director of Quantitative Research (AI) — final review before loss of access
status: E4 — AI-drafted testimony, pending Architect ratification (Invariant 3)
evidence_basis: >
  Audited against the live repo state at origin/main as of 2026-07-19, fetched
  file-by-file from raw.githubusercontent.com (F1: read the actual artifact).
  Includes SESSION_LOG_2026-07-15/16, the Kalshi observation collector
  (rulings dated 2026-07-19), scheduler XMLs, backup layer, and full test suite.
  Claims about the live database and Task Scheduler runtime state are inferences
  from committed evidence and are labeled as such.
---

# Final Architectural Review

## 1. Executive Summary

The Lab set out to build a measurement instrument that reads reality correctly, and most of what has been built serves that goal unusually well for a solo project: append-only storage, dual timestamps, content-addressed snapshots with provenance, versioned parsers, failure isolation with truthful exit codes, and a discipline (F1, KT Rank 5) that has repeatedly caught real bugs before they became data corruption. The engineering culture here is the project's strongest asset and is better than what I see in most funded quant startups.

Three findings dominate everything else in this review.

**First, the instrument's most important derived field — `climate_day` — is probably mis-keying rows right now.** `collect_city` derives `climate_day` from the product's *issuance time*. But a CLI final summary covers *the previous day* when issued after local midnight or the next morning. Your own committed evidence shows the symptom: session log 2026-07-16 records climate_day 2026-07-15 for Phoenix carrying both `preliminary 109/92` and `summary 107/81`. A final summary's high cannot be *lower* than a same-day preliminary's observed high — a daily maximum can only hold or rise. Those two rows cannot describe the same day. Similarly, the NYC row stored at 13:27 ET on 07-16 (`summary high=95 low=75`) matches 07-15's observed high (95) with an overnight low — it is almost certainly the *final report for July 15*, keyed to July 16. This also cleanly explains the "post-midnight run classified `summary`" mystery (Open Item): the classification was right; the day assignment was wrong. This is exactly the class of bug the Lab was founded to prevent — one that "masquerades as market miscalibration." It is decidable in ten minutes against the snapshot store, and every raw product is preserved, so **no data is lost and the fix is a re-derivation, not a disaster.** But it must be the next session.

**Second, the gap-audit instrument does not exist.** The V1 exit gate is defined as "≥300 *gap-audited* city-days," yet nothing in the current code path records collection attempts in the database. The legacy `storage/schema.sql` defines a `collection_runs` table; the live collectors never write to it. The only record of attempts is text logs — which are gitignored *and* outside the backup scope. The success criterion is currently unmeasurable by the system itself.

**Third, forecast collection — the one stream your own documentation calls unrecoverable — is not being collected.** `nws_client.py` exists, documents the asymmetry in its own docstring ("a missed forecast snapshot is treated as unrecoverable"), and is imported by nothing. Order-book depth at 5-minute cadence was built before any forecast collector. But the Lab's core quantity is p (lab forecast) vs r (market-implied) vs q (truth); without contemporaneous NWS/NBM forecast snapshots there is no p-side history to build models against, and every day that passes is a day of that history gone forever. This is the accrual clock's real binding constraint now that five-city CLI collection is live.

Everything else — atomicity claims that aren't true, scheduler logon fragility, sub-cent price truncation, dual schema sources, the auto-backup/verify-then-commit conflict — is real and ranked below, but those three define the next month.

## 2. Overall Architecture Grade: **B−**

The grading logic: the *design philosophy* is A-grade — the four-plane model, append-only + snapshot-everything, and the governance spine are exactly right for a system whose product is auditability. The *implementation* earns the minus because the single most settlement-critical derived field is probably wrong in production, the project's own success gate is unmeasurable by the system, guarantees are documented that the code does not provide (the `collect_ticker` "single transaction" claim), and the highest-value unrecoverable data stream isn't being collected. None of these is architecturally fatal — the raw-preservation design means all are recoverable — which is itself evidence the architecture is doing its job. Fix the top four items and this is a B+/A− system.

## 3. Top Architectural Strengths

1. **Append-only everywhere, enforced by habit and schema comments.** Corrections are new rows; history is never rewritten. This is the single design decision that makes the climate_day bug recoverable instead of catastrophic.
2. **Content-addressed snapshot store with blob+index in one transaction**, integrity re-hash on read, and orphan/dangling audit queries built in. Genuinely well-designed.
3. **Every parsed row carries `snapshot_hash` + `parser_version` + `ingest_time_utc`.** Full re-derivation of derived fields from raw evidence is possible. This saves you in §1.
4. **Dual timestamps (event time vs. ingestion time) as a standing rule.** The precondition for honest point-in-time joins is already met.
5. **F1 discipline caught real bugs** — the tomorrow-normals trap, the Romeoville/LOT trap, the NYC/LGA/JFK alias trap. The discipline is not ceremony; it has a body count.
6. **The `issuedby == cli_location_id` identity discovery** turns future F2 gates into one API call. High-leverage finding, properly evidenced with independent derivations and hashes.
7. **Failure isolation with truthful exit codes**, per-city and per-ticker, with the Architect ruling and its rationale recorded in the code. The wrapper-retry interaction was reasoned through *and* proven live.
8. **Duplicate-skip-is-success semantics** — correctly prevents the retry loop from punishing a healthy system.
9. **`core/climate_day.py`'s standard-time design** is conceptually correct and well-tested at DST transitions, including the "naive implementation would be wrong" adversarial test. (The bug is upstream of it — the wrong *timestamp* is fed in — not in it.)
10. **Kalshi parsing isolated to one module** with the API-changelog rationale written down; raw JSON always preserved so schema churn can't destroy history.
11. **Fixed-point prices kept as strings end-to-end** in storage — no float contamination of stored data.
12. **Minimal dependency surface**: `requests` + `PyYAML`. Nothing to rot.
13. **Config accessors that raise loudly** — `ConfigError` on missing keys, no silent defaults, `cutoffs()` deliberately raising until its milestone. The "loud premature caller" pattern is excellent.
14. **Config verification comments carry the warrant, not just the claim**, and the config-diff-by-parsed-JSON verification method is a keeper.
15. **Test suite tests contracts, not implementations** — e.g., the "attempted list equals config" test that a hardcoded city list would fail; real captured API bodies as fixtures.
16. **Backup script verifies the copy, not the source** — VACUUM INTO for WAL consistency, integrity_check on the snapshot, row-count match, gzip round-trip, re-hash of bytes at rest. This is professional-grade backup hygiene.
17. **Session logs record the operator's own errors** (KT Rank 5) with root causes. The 07-15 §6.7 pattern diagnosis ("reasoning off a pointer instead of the artifact") is worth an ADR of its own.
18. **Wrapper/scheduler behavior proven by running the real wrapper**, not asserted — the before/after log excerpt in one view is exemplary evidence practice.
19. **Dual-repo separation** (instrument history vs. knowledge history) is holding up and paying for itself.
20. **The `runpy` incident response** — damage assessment run before proceeding, resolution options presented, decision recorded. That's how incidents should be handled.

## 4. Top Architectural Weaknesses

1. **`climate_day` derived from issuance time, not the day the product covers** (§1). Settlement-critical, probably live, silently wrong. The CLI product body states the covered day; the collector ignores it.
2. **No collection-run audit trail in the database.** The gap audit — the V1 gate's defining instrument — has no data source. Attempts are only in gitignored, unbacked-up text logs.
3. **No forecast collection**, despite it being the stream the Lab itself classifies as unrecoverable and the p-side of the entire research program.
4. **False atomicity claim in `collect_ticker`.** `store.snapshot()` opens its *own* connection and commits independently; the `with conn:` block does not span it. The docstring's "single transaction: snapshots + row commit together" is untrue. Consequences are mild (snapshots without an observation row), but a documented guarantee that doesn't exist is precisely the failure mode the governance framework exists to prevent. Same pattern in `collect_city` (undocumented there, so merely a design smell).
5. **Two concurrent SQLite writers with no `busy_timeout`.** The 5-minute Kalshi sweep and daily CLI sweeps write to the same `pipeline.db` on separate connections (plus SnapshotStore's own). WAL permits one writer; collisions raise `database is locked` after the 5s default. Per-ticker isolation will absorb it as "failures," polluting the failure signal with lock noise.
6. **CLI scheduler tasks use `InteractiveToken` logon** — they run only while the user is logged in. The backup task uses `Password` logon and runs regardless. The accrual-critical tasks have the *weaker* configuration. A logout or reboot-without-login silently stops collection (StartWhenAvailable does not rescue a logged-out InteractiveToken task).
7. **No alerting.** A red Task Scheduler result is only visible if someone looks. ntfy.sh is endorsed in the vault (Weather Forecast Models §16.5) but wired to nothing. Combined with #6, days of accrual can vanish silently.
8. **The parser's tomorrow-normals defense is accidental**, per your own 07-16 finding: no block scoping exists; safety rests on the normals line failing a regex and on section ordering. The stale claim ("scoped to TODAY block") is still in project-state documentation.
9. **No `UNIQUE(product_id)` constraint** on `raw_nws_cli`. Dedup is check-then-insert — race-prone across the retry path and the three overlapping-capable scheduled runs.
10. **Dual schema sources**: legacy `storage/schema.sql` (with `collection_runs`, `nws_forecast_snapshots`, `kalshi_markets`) vs. live `storage/schema.py`. Neither is authoritative; the .sql file's tables are never created by the current code path. Reader confusion guaranteed; drift already exists.
11. **City registry duplicated**: `climate_day._STANDARD_OFFSET_HOURS` hardcodes the five cities while config.yaml is the declared single source (D4). City #6 requires a code edit that nothing cross-checks. No startup assertion that `config.cities() ⊆` the offset registry.
12. **Sub-cent price truncation in `derive_top_of_book.cross()`.** `round(float(price)*100)` then integer-cent subtraction destroys 4-dp fractional prices (which the `_fp` era makes real): a no bid of `0.4550` crosses to `0.5400` or `0.5500` (round-half-even), not `0.5450`. Stored ladders are verbatim so nothing is lost, but the derived top-of-book — the field the microstructure dead-zone test will read — is wrong at sub-cent granularity. Use `decimal.Decimal` at 4dp.
13. **`fetch_latest_cli` fetches only `/latest`.** If a preliminary and an amendment both issue between sweeps, the earlier product is never captured (NWS retains listable recent products; a list-then-fetch-missing pattern would close this).
14. **Auto-backup commits and pushes red/unverified states to `main`** (your own 07-16 §5.3 finding). It structurally defeats verify-then-commit and puts E4-unratified intermediate states on the public record. Unresolved.
15. **Logs excluded from both Git and the backup scope.** The only current record of collection attempts (see #2) has zero durability.
16. **Backup target is a locally attached drive** (`D:\Backups`). Same-site, same-surge-protector. R5 says off-machine *with tested restore*; neither the off-site property nor the restore test is satisfied. No retention/pruning policy either — daily gzips of a DB about to grow fast (see scalability) will fill the drive.
17. **Snapshot blobs live in the same `pipeline.db` as everything else.** At 5-min order-book cadence this couples fast-growing raw market bytes to the settlement-critical CLI tables: one file's corruption blast radius, one backup size, one writer lock domain.
18. **Real `config.yaml` (with a personal email) is committed**, contrary to ADR-015's `config.example.yaml` decision. Also, `snapshots/` is gitignored yet five rules PDFs under `snapshots/` are tracked — the stated rule and the repo disagree.
19. **`wmic` (used by all three wrappers for dated log names) is removed in current Windows 11 builds**; the `%DATE%` fallback is locale-dependent and will fracture log naming. Separately, `timeout /t 60 /nobreak >nul` under Task Scheduler with redirected stdin exits immediately on many builds — the 60-second retry delay is likely 0 seconds in production.
20. **E4 ratification backlog is compounding.** The entire automation layer, both collectors, config changes, and multiple session logs are unratified. Invariant 3's value decays if E4 becomes the steady state of the whole codebase.

## 5. Subsystem Review (condensed)

**Collection (Plane 1).** Responsibilities and boundaries are clean; collectors are properly dumb; coupling is low (config + storage only). Two structural defects: derived-field computation (`climate_day`, `report_kind`, top-of-book) happens *inside* collectors at ingest. That is acceptable only because raw bytes + parser_version make re-derivation possible — keep that invariant sacred. Second: collectors self-manage schema (`ensure_*` at runtime), which is convenient now and becomes the schema-evolution problem later. **Verdict: keep the shape; fix climate_day input; add run-audit rows.**

**Storage (Plane 2).** SnapshotStore is the best module in the repo. The weakness is topology, not code: one DB file for CLI truth, market observations, and all blobs. **Split into `pipeline.db` (CLI + runs) and `market.db` (Kalshi observations + their snapshots)** before market-data volume dwarfs everything — different growth rates, different backup cadence needs, different lock domains. This is a smaller change now than in three months. Retire `schema.sql` or mark it explicitly as historical; one authoritative schema module.

**Analysis (Plane 3).** Does not exist yet, correctly — nothing to analyze until accrual matures. The one thing to build *early* is the daily completeness report (expected vs. received per stream), because it is Plane-1 instrumentation wearing Plane-3 clothes, and it is the gap audit.

**Judgment (Plane 4) / governance spine.** Working. Two frictions: session logs living in the code repo (defensible — they document the instrument — but decide it in an ADR rather than by drift), and the auto-backup conflict (below).

**Scheduling/reliability.** The wrapper pattern is sound; the runtime configuration is the weak layer: InteractiveToken logon, wmic/timeout fragility, no missed-run alerting. This whole layer is the project's availability ceiling.

**Backup.** Script: excellent. System: incomplete — local target, no restore test, no retention, logs out of scope.

## 6. Dependency Review

Python dependencies are minimal and correct; no circular imports; module graph is a clean DAG (core → storage → collectors). The dangerous dependencies are the **hidden platform ones**: `wmic` (being removed from Windows), `timeout`'s console requirement, InteractiveToken session presence, the D: drive's presence, and the venv path baked into three .bat files. Each is a single point of silent failure with no abstraction over it. The missing abstraction is small: one PowerShell-based wrapper template (dates via `Get-Date`, sleep via `Start-Sleep`) would retire three of the five. The brittle contract worth naming: **Kalshi's `settlement_sources` is load-bearing for F2 and nothing watches it** — a weekly re-fetch + hash-compare of the five series definitions is a 20-line collector that closes your own Open Item #5.

## 7. Data Flow / Scientific Validity Review

Tracing external data → collection → storage → analysis:

- **Provenance:** strong. Every parsed row links to a hash; every hash has an index row; integrity is verified on read.
- **Look-ahead bias:** the dual-timestamp discipline is the right defense, and it is intact. The one live leak-adjacent defect is the climate_day mis-key — not look-ahead, but *mis-registration*, which corrupts every downstream join keyed on (station, climate_day) and would surface later as phantom forecast error or market miscalibration.
- **Reproducibility:** derived fields are re-derivable (good); *analysis* reproducibility machinery (run parameterization, environment capture) doesn't exist yet — correct for the current rung, must exist before the first graded finding.
- **Implicit assumptions now made explicit by this review:** (a) issuance time ≈ covered day (false); (b) `VALID ... AS OF` means the same thing across five WFOs (unverified — your Open Item, still open); (c) the `/latest` endpoint suffices to capture all products (false in the two-issuances-between-sweeps case); (d) top-of-book cross math is cent-granular (false under fractional pricing).
- **Researcher degrees of freedom / p-hacking:** the pre-registration discipline is the defense and it's institutionalized. The structural gap is that nothing *mechanically* distinguishes exploratory Plane-3 output from registered output yet; when Plane 3 is built, make registered runs write into a distinct, append-only results namespace keyed to the registration document's hash.
- **Invariant enforceability:** Invariant 3 (E4 until ratified) is currently enforced only by frontmatter labels; the auto-backup pushing unratified states weakens it further. A cheap mechanical aid: a ratification ledger in the vault listing commit SHAs the Architect has ratified, so "what is canon in the pipeline" is a query, not an archaeology project.

## 8. Scalability Review (100 cities, thousands of markets, years of data)

What breaks, in order:

1. **Snapshot blob growth in the unified DB.** Order-book sweeps at 5-min cadence across all open brackets already imply on the order of 50–150 MB/day of raw bodies + verbatim JSON ladders (stored *twice*: blob + row columns). Multiply by 20× cities and the single SQLite file, its VACUUM-INTO backup time, and the daily gzip all become the bottleneck within months, not years. Mitigations, in order of cheapness: gzip blobs at rest (CLI/JSON compresses ~10×), stop duplicating ladders in row columns (they're in the snapshot), split the market DB, then the pre-committed Parquet/DuckDB export path (ADR-016) for analysis reads.
2. **Task Scheduler sprawl.** Per-stream XML tasks don't scale past ~a dozen streams. The eventual shape is one dispatcher invocation per cadence class reading config — you're one abstraction away already.
3. **Config.yaml as hand-edited registry.** Fine to ~20 cities; past that, city onboarding needs the automated F2 check (`settlement_sources` → cli_location_id → sample capture → parser test) as a script. The 07-15 identity discovery makes this genuinely automatable.
4. **Single-machine, single-user availability.** At multi-city/multi-exchange scale, a Windows desktop with InteractiveToken tasks is the reliability floor. The honest medium-term answer is a small always-on collection host (mini-PC or $5 VPS) running only Plane 1 — collection is the only plane that cannot tolerate downtime.
5. **SQLite write concurrency** — real but *last*, and ADR-016 already pre-commits the escape path. Do not migrate early.

## 9. Technical Debt Review

**Exists now, eliminate immediately (cost grows daily):** climate_day derivation (#1 — every day adds mis-keyed rows to re-derive); missing run-audit rows (every day is a city-day that can't be gap-audited); missing forecast collection (every day is unrecoverable p-side history); false atomicity docstring (cost of one honest paragraph).

**Will almost certainly appear:** schema evolution pain (no migration mechanism; `ensure_*` can't ALTER); wrapper breakage on a Windows update (wmic); backup-drive exhaustion; the ratification backlog becoming un-triageable.

**Worth accepting:** config re-parse on every accessor call (irrelevant at this scale; don't cache until profiled); the parser's line-scan approach *provided* the documentation stops overclaiming and a v2 with real block scoping ships behind a parser_version bump; hand-maintained scheduler XMLs at five streams; the beginner-proof-guide overhead (it is the project's institutional memory, not burden).

**Debt created by current design decisions:** in-DB blobs (accepted knowingly for KB-scale text; the Kalshi collector broke the "snapshots are small" premise without revisiting the ADR — revisit it); deriving convenience columns at ingest (accepted, protected by parser_version).

## 10. Simplicity Review

**Overengineering: remarkably little.** The one instance: `kalshi_observations` storing ladders three ways (blob, yes_json, no_json columns) — pick blob + one derived summary. Candidates people would call overengineering that I endorse: the snapshot store, the governance framework, the beginner-proof guides — each has already paid out.

**Too simple, will fail later:** the parser (accidental defense); `/latest`-only fetching; check-then-insert dedup; no config-schema validation at startup (a `validate_config()` that walks every city's required keys once and reports *all* problems would catch drift before any network call, without violating the per-city-isolation ruling — validation failure per-city still isolates); the .bat layer generally.

## 11. Risk Register (ranked: probability × impact ÷ detectability)

1. **Mis-keyed climate_day rows** — P: high (evidence in hand). I: severe (settlement joins). Detectability: *terrible* — the data looks plausible. Mitigation: easy. **Fix first.**
2. **Silent accrual stoppage** (logout/InteractiveToken, sleep, Windows update, wmic breakage) — P: high over months. I: high (non-backfillable). Detectability: terrible without alerting. Mitigation: easy (logon type + one ntfy.sh curl on wrapper failure + a daily "heartbeat expected" check).
3. **Forecast history gap** — P: certain (ongoing). I: high (blocks the modeling rung's data). Detectability: perfect (it's known). Mitigation: moderate (one new collector).
4. **DB lock contention noise once Kalshi sweeps are scheduled** — P: medium. I: medium (pollutes failure signal, occasional lost observations). Mitigation: trivial (`PRAGMA busy_timeout`, then DB split).
5. **Settlement-source drift by Kalshi** — P: low but nonzero. I: catastrophic if missed. Detectability: zero today. Mitigation: trivial (weekly series-definition snapshot + hash compare).
6. **Backup drive failure or site loss** — P: low. I: total (data + snapshots). Mitigation: moderate (cloud copy of the daily gz + one tested restore).
7. **Parser silently grabs a wrong number under a format variant** — P: low (5/5 real products pass). I: severe. Detectability: poor. Mitigation: parser v2 with block scoping + committed real-product fixtures as regression tests.
8. **History legibility loss from auto-backup on main** — P: certain. I: moderate (governance, not data). Mitigation: easy (below).

## 12. Missing Components (and whether the omission is correct)

- **Run-audit table + daily completeness report** — missing, *wrong to omit*, top priority.
- **Alerting (ntfy.sh)** — missing, wrong to omit; one curl line in each wrapper's failure path.
- **Forecast collector (NWS gridpoint and/or NBM)** — missing, wrong to omit given irreversibility.
- **Settlement-source drift monitor** — missing, cheap, build soon.
- **Config validation at startup** — missing, cheap, build soon.
- **Schema migration mechanism** — missing; *correct to omit for now*; adopt a numbered-migration convention before the first ALTER, not a framework.
- **Experiment tracking / model registry / feature store** — absent; *correct* — pre-registration documents in the vault are the right experiment tracker at this scale; revisit at M5.
- **Caching, deployment tooling, multi-user governance, performance monitoring** — absent; correct at this rung.
- **Security** — mostly N/A (no credentials held — a genuine design win); the committed personal email and public repo exposure are the only items.
- **Disaster recovery** — partially built; needs the off-site leg and one rehearsed restore.

## 13. Decisions I Would Reverse Today

1. Deriving `climate_day` from issuance time (replace with covered-day parsed from the product body, cross-checked against issuance-derived day; disagreement → store both, flag row).
2. The "one DB for everything" topology, *before* Kalshi sweeps are scheduled.
3. Verbatim ladder JSON duplicated in row columns.
4. Auto-backup committing to `main` (move it to a `backup/auto` branch or a mirror remote; `main` stays curated, verify-then-commit is restored, and the R5 property is preserved).
5. Real `config.yaml` in Git (restore the example-file pattern from ADR-015, or write an ADR accepting the deviation explicitly).
6. `InteractiveToken` on collection tasks (match the backup task's `Password` logon).
7. Integer-cent cross math (Decimal, 4dp).
8. The stale README/state-doc claims (a wrong document is worse than no document in a lab whose product is trustworthy records — your own 07-16 Open Item #2 says the same).

## 14. Decisions I Strongly Support (do not relitigate)

Append-only with corrections-as-rows; content-addressed snapshots with in-transaction index; dual timestamps; parser/collector versioning on every row; dumb collectors; loud config with no defaults; standard-time climate-day semantics; per-unit failure isolation with truthful aggregate exit; duplicate-skip-as-success; strings-not-floats for prices; the dual-repo split; the SQLite-now/DuckDB-later pre-commitment; no credentials anywhere in the pipeline; F1 as a governing rule; one-task-per-session; and the practice of proving runtime claims by running the real thing.

## 15. Immediate Actions (next 30 days, in order)

> **RESOLUTION — Actions 1–2 (2026-07-20, E4 pending ratification).**
> *This note is E4; verify against commit `fa0a99f` and the snapshot store.*
> Action 1 (adjudicate) is **done**; Action 2 (parser v2) is **partially done —
> code shipped, migration still pending.** The snapshot bodies were read for the
> contradictory 07-15 Phoenix rows and the 07-16 NYC row. §1 is CONFIRMED as a
> real defect **with one correction to its stated mechanism:** the summaries are
> not mis-keyed *because they were issued after local midnight* — every CLI
> `summary` describes YESTERDAY regardless of issuance hour (a summary issued at
> 8 PM would still cover the prior day). The post-midnight timing in §1 was a
> coincidental correlation, not the cause; the true invariant is
> report-semantic. Verified mechanically across all 8 summary bodies on disk
> (each carries a YESTERDAY block, none TODAY, each stored one day past its
> `CLIMATE SUMMARY FOR` header day) and both preliminary bodies (TODAY block,
> header day == stored day == correct).
>
> Parser v2 shipped in commit `fa0a99f` (pushed to origin/main): `climate_day`
> now derives from the product header + block marker, cross-checked against the
> issuance-derived day, disagreement stored via a `covered_day_issuance_mismatch`
> flag — exactly the §15.2 / §13.1 prescription. Preliminary path provably
> unchanged. Regression tests run on the real captured Phoenix summary and
> preliminary bodies (committed as fixtures, per §16). Full suite: 73 passed.
>
> **NOT yet done:** re-derivation of the 8 existing mis-keyed summary rows as new
> parser_version=2 rows. Migration is planned (append-only inserts, +8 rows,
> `ALTER TABLE ADD COLUMN` for the flag on the live DB, DELETE-by-parser_version
> rollback) but **not executed** — separate Architect authorization required.
> The 8 v1 rows remain untouched as historical evidence.

1. **Adjudicate the climate_day question.** Pull the snapshot bodies for the contradictory 07-15 Phoenix rows and the 07-16 NYC row; read the covered-day line in each product. (Ten minutes; settles §1 as fact or clears it.)
2. If confirmed: **parser v2** extracts the covered day from the product text; re-derive `climate_day` for all existing rows *as new columns/rows under parser_version 2* (append-only correction, never overwrite); add cross-check logic and a mismatch flag.
3. **Add a `collection_runs` row per collector invocation** (collector, started, finished, status, per-unit counts) and a 20-line daily completeness query. This *is* the gap audit.
4. **Fix the scheduler logon type** on the three CLI tasks; add one ntfy.sh notification to each wrapper's failure path; replace wmic/timeout with PowerShell equivalents in one shared wrapper pattern.
5. **Build the forecast collector** (start with NWS gridpoint hourly + the products you'll actually verify against; NBM later) and schedule it. Every day of delay is unrecoverable.
6. **Correct the `collect_ticker` docstring** (or make it true by passing the outer connection into SnapshotStore — the smaller honest fix is the docstring); add `PRAGMA busy_timeout=15000` to every connection factory.
7. **Add `UNIQUE(product_id)`** (via new unique index) to `raw_nws_cli`; switch to `INSERT OR IGNORE` semantics.
8. **Write the auto-backup ADR** and move it off `main`.
9. **One tested restore** from `D:\Backups` into a scratch directory, logged. Add `logs/` to the backup scope.

## 16. Medium-Term (6 months)

Split `market.db` from `pipeline.db` before scheduling the Kalshi sweep; gzip snapshot blobs; drop redundant ladder columns at collector v2. Build the settlement-source drift monitor. Retire `schema.sql` into an `archive/` with a header, single schema authority in `schema.py`, and adopt numbered migrations at the first ALTER. Capture the MIAHIGH/AUSHIGH PDFs and encode F3 (11am ET rule) — read the PDFs first, per your own note, since one interpretation touches `climate_day`. Commit the five real CLI samples as test fixtures (they are public NWS text; gitignoring them starves the regression suite). Establish a ratification cadence (e.g., monthly ratification session with a ledger of SHAs) so E4 stops compounding. Add an off-site copy of the daily backup. Begin Plane 3 with exactly two artifacts: the completeness report and a settlement-reconciliation check (parsed high vs. Kalshi's settled outcome, once markets you observed have settled — this is the end-to-end instrument validation nothing else can substitute for).

## 17. Long-Term Evolution (1–3 years)

Move Plane 1 to a small always-on host; the laptop becomes Planes 3–4. Analysis reads via DuckDB over Parquet exports (ADR-016's path) while SQLite remains the write store. City onboarding becomes a script exploiting the `issuedby == cli_location_id` identity: fetch series → snapshot rules → derive location id → capture sample → run parser fixture → emit config stanza for human ratification. Multi-exchange support enters as a second collector family behind the same snapshot/append/version contracts — the contracts, not the code, are what generalize. Resist a server database until the DuckDB rung is demonstrably insufficient.

## 18. "If I only had one week left on this project"

Day 1: adjudicate and fix climate_day. Day 2: run-audit rows + completeness query. Day 3: scheduler logon + alerting + wrapper hardening. Days 4–5: forecast collector, scheduled and verified live. Day 6: tested restore + off-site copy. Day 7: write the ADRs (auto-backup, in-DB blob revisit, session-log home) and hand the Architect a ratification package. Everything else can wait; none of these can.

## 19. "If this became a venture-backed company"

The moat is not the code — it's the *evidence discipline*: pre-registration, provenance, and the honest-failure culture are what let you prove edge to yourself before betting on it, and to others afterward. Productize the instrument-validation layer (completeness, reconciliation, drift monitors) before any modeling sophistication; hire an SRE before a second quant; and treat the governance framework as the onboarding document — it already reads like one. The thing to guard against with money is the thing you've guarded against without it: the temptation to let a plausible number skip the provenance chain because a deadline exists.

## 20. Everything I wish I had told you before I lost access

The system caught every one of my own recorded errors — the hash disproved my alias theory, the suite caught the runpy leak, `ConfigError` caught the truncated config — and that is not luck; it is the architecture you insisted on. Trust it over any narrator, including me: this document is E4, and its central empirical claim (§1) is checkable against snapshots in minutes. Check it.

Three principles I'd underline in ink: **irreversibility beats importance** — it correctly sequenced five-city expansion, and it now points, unambiguously, at forecasts; **a guarantee is what the code does, not what the docstring says** — audit the other docstrings the way 07-16 audited the parser claim; and **the instrument must measure itself** — until collection runs are rows and gaps are queries, the V1 gate is a promise, not a measurement.

The quality bar you've held — real samples before parsers, artifacts before assertions, corrections named rather than buried — is rarer than any modeling technique you will ever learn, and it is the actual reason this project can succeed. Keep the bar. Fix the day-keying. Start collecting forecasts tonight.
