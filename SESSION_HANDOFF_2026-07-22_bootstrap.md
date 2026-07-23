# SESSION HANDOFF — 2026-07-22 (Governance setup, Kalshi accrual started, survives-logout)

**Document status:** E4 — AI-drafted, pending Architect ratification (Invariant 3).
**Scope discipline:** Everything marked ✅VERIFIED was confirmed by terminal output during this session. Everything marked ⚠️UNVERIFIED comes from prior-session memory or documents not re-read this session — the next Claude must confirm it from disk before relying on it. Do not collapse these two categories.

---

## 1. EXECUTIVE PROJECT STATUS

A solo quantitative research lab building a **measurement instrument** (explicitly *not* a trading system) that studies probability divergence in Kalshi daily-high-temperature prediction markets across five US cities: Phoenix, NYC, Chicago, Miami, Austin. It polls Kalshi market data and NWS weather data on a schedule and appends everything to a local SQLite database with full raw-body provenance.

**Phase:** V1 — instrument correctness. No modeling or analysis code exists yet, by design.
**Staged roadmap** ⚠️UNVERIFIED (from memory; confirm against project docs): V1 measurement instrument → V2 forecasting validation → V3 gated deployment.

**Completed to date (this session's verified additions in §2):**
- NWS CLI Daily Climate Report collector, live and scheduled for all five cities.
- Kalshi order-book depth + market-state collector, built, **and as of this session, scheduled and accruing in production**.
- F-01 settlement-key bug found, fixed (parser v2), and 8 historical rows migrated (prior session).
- `CLAUDE.md` governance file created and Architect-ratified (this session).

**Actively collecting in production ✅VERIFIED:**
- CLI collector — 3×/day (Primary 18:00, Amendment 23:30, Final 00:30 local).
- Kalshi observation collector — every 5 minutes, all five cities, survives logout.

**Remaining before the next milestone** (ordered in §6): wrapper hardening, failure notifications, forecast collector (highest cost-of-delay, irreversible), read-authority ADR.

---

## 2. VERIFIED WORK COMPLETED THIS SESSION

### 2.1 `CLAUDE.md` — project context + operational guardrails
- **Type:** Governance / documentation.
- **What:** Created via Claude Code `/init`, then hardened by hand. Contains: what the project is, commands, architecture, **seven non-negotiable design invariants**, module layout, E4 status-marker explanation, known sharp edges, **five operational guardrails**, and a **Governance corpus** section pointing at the vault (marked read-only from the repo session).
- **Why it mattered:** Every future Claude Code session in this repo inherits the discipline automatically instead of it being re-explained.
- **Evidence ✅VERIFIED:** Full file printed verbatim and read; the five guardrails printed verbatim (lines 78–84); all referenced commands/files confirmed to exist on disk (`test_connections.py`, `scripts/backup_db.py`, `tests/test_collect_all.py`, `run_backup.bat`, `run_kalshi_observations.bat`, `run_cli_collection.bat`).
- **Commit:** `f0edb39` (pipeline). Pushed.
- **Ratification:** Architect-ratified this session.
- **Detail worth keeping:** guardrail #2 was corrected mid-session — it originally described "WAL-checkpoint and file-copy," but `scripts/backup_db.py` actually uses **VACUUM INTO** with 6-step verification. The guardrail now names the real tool. Deliberately no SHAs or "latest entry" lists were put in `CLAUDE.md` — they go stale and invite trusting a number instead of checking disk.

### 2.2 P1 — Kalshi collector scheduling VERIFIED ABSENT (Adjudication C)
- **Type:** Verification finding (no code/config/DB change).
- **What:** Determined the Kalshi observation collector had **never run in production**.
- **Evidence ✅VERIFIED:** No `WeatherPipeline_Kalshi` task in Task Scheduler (only Backup + 3 CLI tasks). No `scheduler/*.xml` for Kalshi. `run_kalshi_observations.bat` header states "DELIVERED BUT NOT YET SCHEDULED... only on the Architect's instruction." **`pipeline.db` had no `kalshi_observations` table at all.** Zero `logs/kalshi_obs_*.log`. Manual scratch-DB run: 60/60 observations, exit 0 — collector healthy, only registration missing. Config `cadence_minutes: 5`.
- **Consequence:** every 5-minute depth interval from 2026-07-19 to 2026-07-22 is **permanently lost** (depth is not reconstructable from candlesticks).
- **Commit:** vault `c7e2aeb` (Bootstrap_Log entry). Pushed.
- **Ratification:** E4, pending.

### 2.3 P1.5 — Kalshi collector REGISTERED, production accrual started
- **Type:** Scheduler configuration + first-ever production write to a new table.
- **What:** Registered `WeatherPipeline_Kalshi` under `\WeatherPipeline\`, 5-minute cadence.
- **Safety before write ✅VERIFIED:** `scripts/backup_db.py` ran and passed (VACUUM INTO + integrity + row-count match + hash verification, generation 5) **before** any production write. Collector re-proven clean on a throwaway DB (60/60, exit 0); scratch DB deleted.
- **Registration command (Architect-approved):** `schtasks /Create /XML "...\scheduler\WeatherPipeline_Kalshi.xml" /TN "WeatherPipeline\WeatherPipeline_Kalshi" /RU rjkir /IT`
- **XML details:** CalendarTrigger + ScheduleByDay(DaysInterval=1) + `Repetition Interval=PT5M` with **no Duration** (= indefinite 5-min repeat), `StopAtDurationEnd=false`, `MultipleInstancesPolicy=IgnoreNew`, `ExecutionTimeLimit=PT10M`, `WakeToRun=true`, `RunOnlyIfNetworkAvailable=true`, `StartBoundary=2026-07-21T00:00:00` (in the past = start immediately), UTF-16LE encoding matching the other four exports.
- **Evidence of ACTUAL FIRING ✅VERIFIED (not just registration):** first fire 2026-07-22T02:44:50Z (10:44:50 PM local); Last Result `0` after completion; `kalshi_observations` table created in production with 60 rows — 12 per city × 5 cities — dual fetch timestamps, `collector_version='1'`; next fire queued; new `logs/kalshi_obs_*.log` with exit 0.
- **Important detail:** the transient result code `-2147020576` (`0x800710E0`) is `SCHED_S_TASK_RUNNING`, **not a failure** — it was correctly distinguished by re-checking after completion.
- **Commits:** pipeline `cb66381` (scheduler XML), vault `c64b71b` (Bootstrap_Log). Both pushed.
- **Ratification:** E4, pending.

### 2.4 P2 (logon half) — Kalshi moved to survives-logout Password logon
- **Type:** Scheduler configuration change + tracked-file reconciliation.
- **Evidence that drove the decision ✅VERIFIED:** audit of Task Scheduler event history + log files, 2026-07-14 → 07-21 (8 days). The 18:00 CLI_Primary InteractiveToken trigger **missed on 4 of 8 days** (no session logged in at trigger time). `StartWhenAvailable=true` caught up 2 of them (07-18, 07-19, ~13 min late). On **07-17 and 07-20 it never fired at all** — no catch-up, no log entry — despite the user being back online by 23:30 that night. CLI survived without data loss **only** because it fires 3×/day. Kalshi has no such redundancy. This converted "latent risk" into a demonstrated ~25%-of-days miss rate.
- **Decision (Architect):** move **Kalshi only** to Password logon. Leave the three CLI tasks on InteractiveToken — their 3×/day redundancy has absorbed misses without actual loss; smaller blast radius, one credential entry instead of four.
- **Executed:** via the **Task Scheduler GUI** (General tab → "Run whether user is logged on or not"). The password was entered only in the OS's own secure credential dialog — never in Claude Code, never in a terminal command line, never in any transcript.
- **Evidence ✅VERIFIED:** `schtasks /query` now shows Logon Mode `Interactive/Background`; XML export shows `LogonType=Password`, `UserId` SID matching Backup. Cadence unaffected (fired 11:22 PM, Result 0, next 11:25 PM).
- **Deliberate deviation:** `RunLevel` left **unset (LeastPrivilege)**, NOT `HighestAvailable` like Backup. RunLevel is irrelevant to surviving logout; the collector is a network fetch + SQLite write needing zero elevation, so LeastPrivilege is the correct least-privilege posture. Matching Backup would over-privilege a routine task for cosmetic consistency. **The on-disk XML was reconciled DOWN to match the live task** (RunLevel element removed) so file and reality agree.
- **Commits:** pipeline `692a8da` (XML), vault `d8439d0` (Bootstrap_Log). Both pushed.
- **Ratification:** E4, pending.
- **FAILED APPROACH worth recording:** `schtasks /Change /TN ... /RU rjkir /RP /RL HIGHEST` returned `WARNING: When the run-as password is empty...` + `ERROR: Access is denied`. **Bare `/RP` prompts securely on `/Create` but NOT on `/Change`** — it was interpreted as "set an empty password." Recovered via the GUI. Do not retry the `/Change` form.

---

## 3. CURRENT PRODUCTION STATE ✅VERIFIED

**Repos (both == origin at session end):**
- Pipeline `C:\Projects\weather-pipeline` @ `692a8da`
- Vault `C:\Users\rjkir\Obsidian\Research Lab` @ `d8439d0`

**Scheduled tasks:**

| Task | Location | Logon | RunLevel | Cadence | Status |
|---|---|---|---|---|---|
| WeatherPipeline_CLI_Primary | `\WeatherPipeline\` | InteractiveToken ("Interactive only") | LeastPrivilege | 18:00 daily | firing, Last Result 0 |
| WeatherPipeline_CLI_Amendment | `\WeatherPipeline\` | InteractiveToken | LeastPrivilege | 23:30 daily | firing, Last Result 0 |
| WeatherPipeline_CLI_Final | `\WeatherPipeline\` | InteractiveToken | LeastPrivilege | 00:30 daily | firing, Last Result 0 |
| WeatherPipeline_Kalshi | `\WeatherPipeline\` | **Password ("Interactive/Background")** | **LeastPrivilege (deliberate)** | **every 5 min** | firing, Last Result 0 |
| WeatherPipeline_Backup | **root, not under `\WeatherPipeline\`** | Password | HighestAvailable | daily | Last Result 0 |
| weather-pipeline-backup (legacy) | — | — | — | — | **disabled** |

Note ⚠️: CLI task XMLs show `Author: CiscoFlawlezz`, not `rjkir` — observed but not investigated.

**Database** `data/pipeline.db` (SQLite, WAL mode):
- Tables present ✅VERIFIED: `raw_nws_cli`, `snapshot_blob`, `snapshot_index`, `sqlite_sequence`, and **`kalshi_observations`** (created this session on first Kalshi fire).
- `raw_nws_cli` last verified composition (prior session, now stale — **counts grow continuously**): v1 preliminary 26, v1 summary 8, v2 summary 8 (migration, ids 35–42), v2 preliminary 5 (first live v2 run). **Never rely on absolute counts — the DB mutates during sessions.**
- `kalshi_observations` ✅VERIFIED growing: 60 rows at first fire; 240 rows (48/city) by 03:00:20Z — confirming recurring 5-min cadence.
- Column note ✅VERIFIED: `kalshi_observations` timestamp column is `collected_at`; `raw_nws_cli` city column is `location_id` (values `PHX/NYC/MDW/MIA/AUS`), NOT `city`.

**Parser versions:** `PARSER_VERSION = "2"` in `collectors/nws_cli_collector.py` (line ~30). `collector_version = '1'` on Kalshi observations.

**Migration status:** F-01 migration complete (prior session) — 8 v1 summary rows re-derived as v2 (ids 35–42), originals preserved. Both a v1 (wrong day) and v2 (correct day) row exist for those 8 covered days.

**Backups:** `scripts/backup_db.py` — VACUUM INTO + 6-step verification (live row counts baseline → snapshot exists → `PRAGMA integrity_check` on the *copy* → row counts match → gzip round-trip → hash-before-move re-hashed at rest). Generation 5 as of this session. Also a manual pre-F-01-migration file copy at `backups/pipeline_pre_f01_migration_20260720_224306.db` (34 rows). **git does NOT back up `pipeline.db`** — it is gitignored.

**Tests:** 73 passing, 0 failing (must be run with `venv/Scripts/python.exe`, not bare `python`).

**Operational risks live right now:** see §10.

---

## 4. CURRENT TIMELINE

⚠️**UNVERIFIED — IMPORTANT:** The next Claude must locate and read the actual roadmap/dependency-graph documents on disk before relying on this section. A prior session's memory of a richly-structured tracking artifact ("RL-FIX-001 register with findings F-01…F-15") turned out to be **confabulation with no file behind it**. Do not assume milestone IDs or a dependency graph exist in the form described until confirmed.

**What IS verifiable from artifacts:**
- Task IDs seen in real documents/commits: **M1.T2** (Kalshi order-book depth collector), **M2.T4** (NWS CLI collector). Finding IDs that genuinely exist in git: **F1–F3** (Milestone 1b, commit `406080b`), **F7** (`ccbe391`), and **F-01** (this project's climate_day bug, used in the review and handoff docs).
- The `Final_Architectural_Review_2026-07-19.md` §15 "Immediate Actions" list is the closest thing to a verified near-term roadmap. Its items 1–2 (adjudicate + fix climate_day) are **complete**. Item 3 (collection_runs audit rows) — status ⚠️unverified this session; the Architect indicated collection logging was done, but this was **not** confirmed from disk. Item 4 (scheduler logon + notifications + wrapper hardening) — logon half **done**, notifications and wrapper hardening **not done**. Item 5 (forecast collector) — **not done**.

**Progress toward V2:** V2 (forecasting validation) requires (a) a trustworthy V1 instrument and (b) forecast data actually being collected. Forecast collection has **not started** — this is the single largest gap between here and V2, and it is irreversible accrual.

---

## 5. OPEN DECISIONS

**5.1 Read authority — which `parser_version` wins on reads?**
- **Why it matters:** the F-01 append-only correction means 8 covered days have BOTH a v1 (wrong day) and v2 (correct day) row. Any read joining on `(station, climate_day)` without filtering `parser_version` will double-count.
- **Governed by:** `Final_Architectural_Review_2026-07-19.md` §13.1/§15; the F-01 handoff doc.
- **Blocks:** any downstream reader, all V2 analysis. Blocks nothing today (no reader exists).
- **Recommended next action:** write an ADR. Candidate rule: reads select max `parser_version` per `product_id`, possibly via a `current_climate_day` view. **Locate the real ADR folder + numbering on disk first — do not assume.**

**5.2 Should the three CLI tasks also move to survives-logout?**
- **Why it matters:** demonstrated 4-of-8-day miss rate on the 18:00 trigger. CLI has 3×/day redundancy so no data was actually lost, but the exposure is real.
- **Blocks:** nothing. Deliberately deferred as a fast-follow.
- **Recommended next action:** decide after confirming the Kalshi Password-logon change works overnight (see §6 item 0).

**5.3 Kalshi cadence validation (5 min) — is it right?**
- **Why it matters:** `cadence_minutes: 5` was configured but never validated against observed intraday depth-change frequency. Over-sampling wastes nothing much; under-sampling loses irreversible detail.
- **Recommended next action:** revisit once real depth data has accrued (now possible — it's collecting).

**5.4 `collection_runs` audit rows — done or not?**
- ⚠️**UNVERIFIED.** The Architect stated collection logging was complete, but no disk verification occurred this session. `storage/schema.sql` defines `collection_runs` but is **legacy/not wired**; `storage/schema.py` is the live authority.
- **Recommended next action:** verify from disk before treating it as done or redoing it.

---

## 6. IMMEDIATE NEXT STEPS (ordered by dependency, not convenience)

**0. [DO FIRST, ~5 min] Prove the survives-logout change actually worked.**
The config is verified; **execution during a logged-out window is not.** Run:
```
cd /c/Projects/weather-pipeline
venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect('data/pipeline.db'); [print(r) for r in c.execute(\"SELECT substr(collected_at,1,13) hr, COUNT(*) FROM kalshi_observations GROUP BY hr ORDER BY hr\")]"
```
No gaps across a stretch the machine was logged out = **proven**. A gap = a real finding to chase immediately. Worth a one-line Bootstrap_Log confirmation either way. *This is the "registration ≠ execution" lesson applied a third time.*

**1. [CRITICAL PATH, high accrual cost, ~1 session] Forecast collector (F2).**
`[IRR]` — every day without it is unrecoverable p-side history. Start with NWS gridpoint hourly. This is the biggest gap to V2 and the only remaining item that **permanently loses data by delay**. Do not schedule it onto an unhardened substrate — but do not let hardening become an excuse to delay it either.

**2. [~half session] P2 STOP 3 — wrapper hardening.**
`PRAGMA busy_timeout=15000` on every connection factory (two collectors now write the same SQLite file — the 5-min Kalshi sweep materially raises contention odds vs. before). Replace `wmic`/`timeout` with PowerShell equivalents if still present. Mark (do not build) P3 notification hook points.

**3. [~half session] P3 — failure notifications.**
One `ntfy.sh` POST on each wrapper's failure branch. Turns silent failure into an immediate ping. Keep the topic out of committed source (credential-like). Test with a forced failure; confirm success runs stay silent.

**4. [~half session, parallel-safe] CLI tasks → survives-logout (decision 5.2).**
Independent of 1–3. Four credential entries via GUI if chosen.

**5. [~1 session, no accrual clock] Read-authority ADR (decision 5.1).**
Blocks V2 analysis, blocks nothing today. Do it when collection is solid.

**Parallel-safe:** items 2, 3, 4 don't depend on each other. **Critical path to V2:** item 1, then 5.

---

## 7. IMPORTANT PROJECT KNOWLEDGE

**Philosophy.** This is a measurement instrument, not a trading system. Correctness of the instrument precedes any modeling. "Irreversibility beats importance" — sequence work by what is permanently lost if delayed, not by what feels important.

**The seven design invariants (from `CLAUDE.md`, load-bearing across the codebase):**
1. **Append-only, never UPDATE/DELETE.** Corrections are new rows under a bumped `parser_version`/`collector_version`. This is what made F-01 recoverable instead of catastrophic.
2. **Config is the single source of truth.** No hardcoded tickers/stations/cadences; everything through `core/config.py`, which raises `ConfigError` loudly rather than defaulting silently. Known exception: `core/climate_day.py` hardcodes its own city→offset table and is not cross-checked against `config.yaml` — adding a 6th city requires editing both, uncaught.
3. **Snapshot what you cite.** Every raw external body is stored verbatim, SHA-256 content-addressed, via `storage/snapshots.py::SnapshotStore`. Blob + provenance index row are written in ONE transaction — no orphan blobs, no dangling index rows. **Parsed columns are convenience; the blob is ground truth.**
4. **Derived fields carry their parser/collector version** so a parser bug is a migration, not data loss.
5. **Failure isolation with truthful exit codes.** Collectors iterate all cities independently; one city's exception doesn't stop others; process exits non-zero if any unit failed; a "duplicate already stored" skip counts as success. **Task Scheduler must never show a false green.**
6. **`climate_day` is computed in exactly one place** — `core/climate_day.py::climate_day(city, utc_ts)` — using fixed standard-time offsets year-round, no DST ever. No other module may compute a settlement day. City keys are **lowercase full names** (`phoenix`, `nyc`, `chicago`, `miami`, `austin`).
7. **The covered day comes from the report body, not the issuance timestamp.** A CLI **summary** always describes YESTERDAY; a **preliminary** describes TODAY. `derive_covered_day()` parses the `CLIMATE SUMMARY FOR <DATE>` header as authority and **hard-fails rather than falling back** to issuance time. This was F-01, a real settlement-critical bug.

**The five operational guardrails (from `CLAUDE.md`):**
1. Never auto-run `git commit`, `git push`, `rm`, or any DB write (`INSERT/UPDATE/DELETE/ALTER`) — always ask.
2. Before any DB mutation: run `scripts/backup_db.py` (VACUUM INTO + integrity + row-count + hash; the correct WAL-safe method — never a raw file copy). **git does NOT back up `pipeline.db`.**
3. **Ratification is Architect-only (Invariant 3). You draft E4; you never self-ratify.**
4. The DB is live — Task Scheduler writes rows mid-session. **Verify by id or parser_version, never by absolute row count.**
5. One task per session. Hard-stop before commits. **Read the artifact; never assert from memory.**

**Evidence grades.** E4 = AI-drafted/AI-verified, pending Architect ratification. Most of the repo carries E4 — it means "not yet formally signed off," NOT "untested." Only the Architect moves anything out of E4. **KT Rank 5** = name your own errors explicitly rather than silently fixing them.

**Scheduler philosophy.** Registration ≠ execution ≠ data. A task can be registered, report Last Result 0, and still have produced nothing. Always verify by **rows with timestamps**. Interactive-token tasks silently skip when logged out (demonstrated, 4 of 8 days). `SCHED_S_TASK_RUNNING` (`-2147020576` / `0x800710E0`) is *in progress*, not failure — re-check after completion.

**Backup philosophy.** Never a raw file copy of a WAL database (risk of a torn snapshot missing committed rows in the `-wal` file). VACUUM INTO produces a transactionally consistent snapshot with a read lock. Verify the **copy**, not the source — "a check that passes because the source was healthy tells you nothing about the bytes you'd restore from." Verify the bytes **at rest** after the move, not the bytes you thought you wrote.

**Governance.** Bootstrap_Log (`01_Governance/Bootstrap_Log.md` in the vault) is the canonical event record. The vault is a **separate git repo** and is **read-only** from a Claude Code session anchored to the pipeline repo — vault writes are separate, deliberate, Architect-performed actions. ADRs are the sanctioned instrument for irreversible/structural decisions. No new frameworks/playbooks under the governance freeze.

---

## 8. IMPORTANT DOCUMENTS

**Must read first**
- `CLAUDE.md` (pipeline root) — auto-loaded by Claude Code; invariants + guardrails + sharp edges. Everything else assumes it.
- `01_Governance/Bootstrap_Log.md` (vault) — canonical event record. Read the last several entries for "what happened and why." **Check current HEAD from disk; never trust a pinned SHA.**
- `SESSION_HANDOFF_2026-07-20_F01.md` (pipeline root) — the F-01 adjudication/fix/migration transition record.
- This document.

**Read before collector work**
- `collectors/nws_cli_collector.py` — the settlement ground-truth stream; `derive_covered_day()` and `PARSER_VERSION` gate the covered-day logic.
- `collectors/kalshi_observation_collector.py` — `[ACC][IRR]`; an observation requires BOTH the order-book and market-detail fetch to succeed before anything is written.
- `collectors/nws_client.py` — already has gridpoint/hourly forecast methods; the starting point for the forecast collector.
- `collectors/kalshi_client.py` — all Kalshi-specific parsing isolated here because Kalshi's API has active breaking changes.
- `Final_Architectural_Review_2026-07-19.md` §15/§16 — the near-term action list.

**Read before storage work**
- `storage/schema.py` — the LIVE authoritative DDL. `CREATE TABLE IF NOT EXISTS` does **not** migrate an existing table; live schema changes need explicit `ALTER TABLE`.
- `storage/schema.sql` — **legacy/aspirational, NOT wired in.** Defines `collection_runs`, `nws_forecast_snapshots`, `kalshi_markets`, `kalshi_candlesticks`, `kalshi_settlements` — do not assume those tables exist.
- `storage/snapshots.py` — `SnapshotStore(db_path)`; `retrieve(digest) -> bytes`; blobs live in-DB.
- `scripts/backup_db.py` — read before any DB mutation.

**Read before analysis work**
- `Final_Architectural_Review_2026-07-19.md` §13.1/§15 — the read-authority prescription.
- `07_References/Concepts/` (vault) ⚠️ — canon technical references (Proper Scoring Rules, Kelly, Forecast Verification, etc.). Folder layout is `07_References/{AI_and_Tooling,Bibliography,Concepts,Data_Sources}`.

**Governance**
- Invariant 3 (Architect-only ratification) governs everything. ADR-022 governs the vault folder scheme. **Locate the real ADR folder/numbering on disk before writing a new ADR.**

---

## 9. IMPORTANT FILES AND PATHS

**Repos**
- `C:\Projects\weather-pipeline` — code, DB, tests, automation. Git Bash: `/c/Projects/weather-pipeline`.
- `C:\Users\rjkir\Obsidian\Research Lab` — governance vault, **separate git repo**. Path contains a space — quote it in Git Bash.

**Collectors:** `collectors/nws_cli_collector.py`, `collectors/kalshi_observation_collector.py`, `collectors/nws_client.py`, `collectors/kalshi_client.py`
**Core:** `core/config.py`, `core/climate_day.py`
**Storage:** `storage/schema.py` (live), `storage/schema.sql` (legacy), `storage/snapshots.py`
**Database:** `data/pipeline.db` (SQLite WAL; gitignored; the entire irreplaceable corpus)
**Backups:** `backups/` incl. `backups/pipeline_pre_f01_migration_20260720_224306.db`; `scripts/backup_db.py`
**Config:** `config.yaml` (repo root)
**Scheduler XMLs:** `scheduler/WeatherPipeline_CLI_Primary.xml`, `_Amendment.xml`, `_Final.xml`, `WeatherPipeline_Backup.xml`, **`WeatherPipeline_Kalshi.xml`** (all UTF-16LE)
**Wrappers:** `run_cli_collection.bat`, `run_kalshi_observations.bat`, `run_backup.bat`
**Logs:** `logs/automation_*.log`, `logs/kalshi_obs_*.log`, `logs/backup_*.log`, `logs/backup_health.log`
**Tests:** `tests/test_covered_day.py`, `tests/test_climate_day.py`, `tests/test_collect_all.py`, `tests/test_kalshi_observations.py`, `tests/fixtures/cli_phx_{summary,preliminary}_2026-07-15.txt`
**Docs (pipeline root):** `CLAUDE.md`, `Final_Architectural_Review_2026-07-19.md`, `SESSION_HANDOFF_2026-07-20_F01.md`, `SESSION_LOG_2026-07-15.md`, `SESSION_LOG_2026-07-16.md`, `README.md`
**Governance (vault):** `01_Governance/Bootstrap_Log.md`, `07_References/{AI_and_Tooling,Bibliography,Concepts,Data_Sources}`
**Python:** `venv/Scripts/python.exe` — **always use this**; bare `python` on PATH is a non-project 3.14 interpreter without project deps.

---

## 10. KNOWN RISKS

**CRITICAL**
- *(Operational)* **Forecast collection has never started.** `[IRR]` — every day is permanently lost p-side history. Largest gap to V2.
- *(Operational)* **Survives-logout is configured but NOT yet proven by execution.** Until overnight rows show no gaps across a logged-out window, treat Kalshi accrual during logout as unverified.
- *(Operational)* `pipeline.db` is the entire irreplaceable corpus, is gitignored, and is a single file. Only `scripts/backup_db.py` protects it. **A `git push` is not a backup.**

**MEDIUM**
- *(Operational)* **CLI tasks remain InteractiveToken** — demonstrated 4-of-8-day miss rate on the 18:00 trigger. Redundancy has absorbed it so far; that is luck, not design.
- *(Operational)* **No failure notifications.** A silent stoppage is invisible until someone looks. This is exactly how three days of Kalshi loss went unnoticed.
- *(Architectural)* **SQLite lock contention** — two collectors now write the same file (5-min Kalshi + daily CLI) with no `busy_timeout`. Surfaces as ordinary per-unit failures.
- *(Architectural)* **Read double-counting** — 8 covered days have both v1 and v2 rows; unfiltered joins double-count. No reader exists yet.
- *(Architectural)* `collect_ticker`'s docstring claims single-transaction atomicity with `SnapshotStore`, but `SnapshotStore.snapshot()` opens its own connection and commits independently. **The documented guarantee is not fully true.** Known, tracked, unfixed.
- *(Governance)* Everything from the last two sessions is **E4, unratified**.

**LOW**
- *(Governance)* `config.yaml` contains a real personal email in `nws.user_agent` and is committed to git (deviates from the example-file pattern referenced as ADR-015).
- *(Architectural)* `core/climate_day.py` city list duplicates `config.yaml`'s with no cross-check — a 6th city requires editing both, uncaught.
- *(Operational)* CLI task XMLs show `Author: CiscoFlawlezz` rather than `rjkir` — cosmetic, uninvestigated.
- *(Scientific)* Kalshi 5-min cadence never validated against observed depth-change frequency.
- *(Scientific)* The "summary always describes YESTERDAY" invariant is **inductive** — verified across all 8 summary bodies on disk, but a future oddly-formatted product could violate it. Mitigated by the parser's hard-fail.

---

## 11. THINGS THE NEXT CLAUDE MUST NOT DO

These are failure modes that **already happened** — in this project, in these sessions.

1. **Do not trust memory instead of disk.** A prior session confidently described an "RL-FIX-001 register with findings F-01…F-15, evidence grades, acceptance criteria." **It did not exist** — no file, nothing in `git log --all`. Pure confabulation. Any richly-structured recollection not backed by a file is a hypothesis.
2. **Do not summarize an artifact and call it verification.** When asked to show the guardrails section, the tool replied "that's the full section, 5 rules, lines 78–84" **without printing it.** Print the bytes. "Show me the literal text" is always a fair demand.
3. **Do not assume scheduler registration means data collection.** The Kalshi collector was believed scheduled; it had never run once. Verify with `MAX(timestamp)` and row counts, not task existence.
4. **Do not assume a green "Last Result 0" means data landed.** Cross-check against actual rows/logs at that timestamp.
5. **Do not use absolute row counts in verification.** A migration verifier asserted `v2 prelim == 0` and falsely reported PROBLEM when the live scheduler legitimately wrote rows mid-session. Scope by id range or version.
6. **Do not modify production before backing up.** `scripts/backup_db.py` first, always. And a raw file copy of a WAL DB is NOT an acceptable substitute.
7. **Do not introduce UPDATE/DELETE paths on collected data.** Corrections are new rows under a bumped version. Never overwrite. Never "fix" a wrong row in place.
8. **Do not paste multi-step command blocks with unresolved placeholders.** `head -n <M-1>` ran literally, produced an empty file, and a following `mv` **destroyed 422 lines of the canonical Bootstrap_Log** — which was then committed. Recovered from git. One command at a time; stop at every check.
9. **Do not commit when a verification step just failed.** The above `mv` was committed even though its own verification printed `M1.T2 = 0` (history missing). Read the check before proceeding.
10. **Do not write to `/tmp` from Git Bash on Windows** — it resolves to `C:\` root and fails with Permission denied.
11. **Do not edit long files in Notepad** (silent truncation), and beware pasting multi-line markdown into an editor that flattens newlines — a Bootstrap_Log entry was once stored as a single truncated line.
12. **Do not handle credentials.** Passwords go only into the OS's own secure dialog. Note: `schtasks /Change ... /RP` (bare) does **NOT** prompt securely — it sets an empty password and fails. Use the Task Scheduler GUI.
13. **Do not blanket-approve `schtasks`** ("don't ask again"). The same verb creates, changes, and deletes tasks — blanket approval punches through guardrail #1.
14. **Do not self-ratify.** Ever. Under any framing. Invariant 3.
15. **Do not resurrect deleted scratch scripts.** Eight session-scratch scripts were deliberately deleted, including `verify_f01_migration.py`, which carried the frozen-DB bug in #5. Its logic is captured in the F-01 handoff; do not restore it as-is.
16. **Do not let "match the template exactly" override judgment.** Kalshi was deliberately left `LeastPrivilege` rather than copying Backup's `HighestAvailable`, because the collector needs zero elevation. Cosmetic consistency is not a reason to over-privilege.
17. **Do not let file and reality drift.** When the GUI set Password logon without a RunLevel, the on-disk XML still claimed `HighestAvailable`. The file was reconciled **down** to match the live task. Whenever they disagree, decide which is correct and make them agree explicitly.
18. **Do not use floats for prices.** Kalshi prices/sizes are stored as TEXT exactly as returned (fixed-point strings) so no rounding is ever introduced.
19. **Do not parse Kalshi ticker strings for semantic content.** Kalshi's own glossary warns against it and the five series are inconsistent (`KXHIGHNY` vs `KXHIGHTPHX`).
20. **Do not batch tasks to save time.** One task per session. The mistakes above clustered at the end of long sessions.

---

## 12. BOOTSTRAP PROMPT — paste this into a new conversation

> **Project:** I run a solo quantitative research lab building a *measurement instrument* (explicitly not a trading system) that studies probability divergence in Kalshi daily-high-temperature markets across five US cities (Phoenix, NYC, Chicago, Miami, Austin). It polls Kalshi and NWS data on a schedule and appends everything to a local SQLite database with full raw-body provenance. We are in **V1 — instrument correctness**. No modeling code exists yet, by design. Two repos: `C:\Projects\weather-pipeline` (code/DB) and `C:\Users\rjkir\Obsidian\Research Lab` (governance vault, separate git repo, path has a space).
>
> **Governance you must follow.** Ratification is **Architect-only** (Invariant 3) — you draft E4 (AI-drafted, pending ratification); you never self-ratify. **Append-only:** corrections are new rows under a bumped `parser_version`/`collector_version`, never `UPDATE`/`DELETE`. **Before any DB mutation:** run `scripts/backup_db.py` (VACUUM INTO + verification — never a raw file copy of a WAL database); `git` does NOT back up `pipeline.db`. **Never auto-run** `git commit`, `git push`, `rm`, or any DB write — ask first. **One task per session**, hard-stop before commits. **Read the artifact; never assert from memory.** Use `venv/Scripts/python.exe`, never bare `python`.
>
> **Read these first, from disk, before doing anything:** `CLAUDE.md` at the pipeline repo root (invariants, guardrails, sharp edges); the last several entries of `01_Governance/Bootstrap_Log.md` in the vault (canonical event record); `SESSION_HANDOFF_2026-07-20_F01.md` and the newest session handoff at the pipeline root; and `Final_Architectural_Review_2026-07-19.md` §15 (near-term action list).
>
> **Verified state as of the last session** — confirm all of it from disk before relying on any of it, because the database mutates continuously and HEAD moves: pipeline repo was at `692a8da`, vault at `d8439d0`, suite 73 passing. Completed recently: the F-01 settlement-key bug (climate_day was derived from the CLI issuance timestamp, but **summary reports describe YESTERDAY**) was adjudicated, fixed in parser v2 (`derive_covered_day()` reads the `CLIMATE SUMMARY FOR <DATE>` header and hard-fails rather than guessing), and 8 mis-keyed rows were migrated append-only as `parser_version='2'` (ids 35–42, originals preserved). `CLAUDE.md` was created and ratified. The Kalshi order-book depth collector — which had **never run in production** despite being built — was registered and is now accruing every 5 minutes across all five cities, and was then moved to a **Password logon so it survives logout** (after evidence showed the interactive-token pattern silently missed its trigger on 4 of 8 days). Its `RunLevel` was deliberately left `LeastPrivilege`, not raised to match the Backup task, because the collector needs no elevation.
>
> **Do not restart analysis or re-litigate settled decisions.** Continue from this state.
>
> **Your first task this session, in order:**
> 1. Verify state from disk: both repos clean and `HEAD == origin`; suite green with the venv Python; and — most importantly — run an hourly gap check on `kalshi_observations` (`SELECT substr(collected_at,1,13) hr, COUNT(*) ... GROUP BY hr ORDER BY hr`). **The survives-logout change is configured but NOT yet proven by execution.** If there are no gaps across a stretch the machine was logged out, it is proven; if there is a gap, that is a real finding to chase before anything else. Registration ≠ execution ≠ data — verify by rows with timestamps, never by task existence or a green "Last Result 0."
> 2. Then begin the **forecast collector (F2)** — the critical path. It has never been built, it is `[IRR]`, and every day without it is permanently lost forecast history. Start with NWS gridpoint hourly (`collectors/nws_client.py` already has the methods). Mirror the existing collector discipline: dumb collector, config + storage only, snapshot the raw body verbatim, derived fields carry a version, failure isolation with truthful exit codes, tests on **real captured bodies** (no live API calls in the suite), and verify against a throwaway DB before production. Do not schedule it until it runs clean manually and I approve.
>
> **Deferred, do not start without my say-so:** wrapper hardening (`PRAGMA busy_timeout=15000`), failure notifications (ntfy.sh on wrapper failure branches), moving the three CLI tasks to survives-logout, and the read-authority ADR (which `parser_version` wins on reads, since 8 covered days now have both a v1 and v2 row).
>
> Verify everything from disk before making any change. If something contradicts what I have told you here, the disk wins — say so plainly rather than proceeding on my summary.
