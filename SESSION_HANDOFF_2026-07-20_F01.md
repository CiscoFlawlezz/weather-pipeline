# Session Handoff — F-01 climate_day Adjudication, Fix, Migration & Ratification
**Date:** 2026-07-20 (into 2026-07-21 UTC) · **Author:** AI (drafting engineer) · **Status:** E4 for this document itself, pending Architect ratification (Invariant 3)

> **Purpose.** Transition record for a Principal Engineer continuing this project *without* access to the originating conversation. Everything below is grounded in artifacts on disk or in git history; where a claim is inductive or unverified, it is marked as such. Commit SHAs are the authoritative anchors.

**Anchor SHAs (verify these resolve before trusting anything else):**
- Pipeline repo (`C:\Projects\weather-pipeline`) HEAD: `2d4fca1` — F-01 commits: `fa0a99f` (parser v2), `96ba6b9` (review doc added), `2d4fca1` (§15 stamp).
- Vault repo (`C:\Users\rjkir\Obsidian\Research Lab`) HEAD: `d3b16f2` — F-01 commits: `5cd052d` (log restore + RESOLVED entry), `d3b16f2` (MIGRATION entry).
- Pre-migration DB backup: `backups/pipeline_pre_f01_migration_20260720_224306.db` (34 rows).

---

## PART 1 — SESSION SUMMARY (chronological)

**1. State verification (open).** *Investigated:* repo cleanliness, suite, branch sync. *Why:* session-opening discipline — never act from memory. *Evidence:* `git status`, `rev-parse HEAD`/`origin/main`, `pytest`. *Conclusion:* clean; HEAD==origin `d1cccfe`; 69 tests passed. *Confidence:* high (terminal output). *Status:* closed.

**2. F-01 adjudication — read the CLI product bodies.** *Investigated:* whether `climate_day` is mis-keyed. *Why:* the architectural review's §1 flagged it as "probably live, settlement-critical," graded E4 (inference from two session-log rows, not from product bodies). The whole session was gated on converting this to real evidence. *Evidence:* queried `raw_nws_cli` for the contradictory rows; retrieved snapshot BLOBs by hash via `storage/snapshots.py::SnapshotStore.retrieve()`; read the `...CLIMATE SUMMARY FOR <DATE>...` header + TODAY/YESTERDAY block in each. Read 5 bodies (PHX summary id3, PHX prelim id4, PHX summary id5, PHX prelim id14, NYC summary id6), then mechanically checked all 8 summary bodies. *Conclusion:* **CONFIRMED with correction** (see Part 2). *Confidence:* high — verified across 8/8 summary + 2/2 preliminary bodies. *Status:* closed.

**3. Parser v2 built & committed (`fa0a99f`).** *Investigated/decided:* how to derive covered day from the body. *Why:* the confirmed fix. *Evidence:* read `collectors/nws_cli_collector.py` in full before editing (real signatures, real column names). Built `derive_covered_day(product_text, issuance_day) -> (covered_day, marker, flag)`; bumped `PARSER_VERSION` to `"2"`; added `covered_day_issuance_mismatch` column; hard-fail (ValueError) on unparseable header; regression tests on real captured PHX bodies committed as fixtures. *Conclusion:* 73 tests pass (was 69, +4). *Confidence:* high. *Status:* closed (code). Ratified.

**4. Review doc committed + resolution-stamped (`96ba6b9`, `2d4fca1`).** *Investigated:* where the "architectural review" and "RL-FIX-001 register" live. *Why:* to record F-01's resolution. *Evidence:* `grep`/`find` across vault and pipeline, `git log --all`. *Conclusion:* the review existed only as an **untracked file the Architect placed at the pipeline repo root mid-session**; the "RL-FIX-001 / F-01…F-15 register" **does not exist** and never did (see Part 2/3). Committed the review as-is, then appended a §15 resolution stamp. *Confidence:* high. *Status:* closed.

**5. Migration of 8 mis-keyed rows (`d3b16f2` log; DB ids 35–42).** *Investigated:* re-derive existing wrong rows. *Why:* Architect authorized migration after the fix landed. *Evidence:* file backup of `pipeline.db` (34 rows, verified) → `ALTER TABLE ADD COLUMN` → dry-run with per-row assertions (all 8 clean) → single-transaction insert of 8 v2 rows → independent post-write verification. *Conclusion:* 8 corrected rows appended as `parser_version='2'`; originals untouched; count 34→42. *Confidence:* high. *Status:* closed. Ratified (scoped by row id).

**6. Architect ratification pass.** *Investigated:* verify each E4 artifact against disk, then Architect stamps. *Why:* Invariant 3 — only the Architect ratifies; the AI verifies. *Evidence:* per-item disk checks. *Conclusion:* 6 artifacts RATIFIED (items 1–6 in Part 2). *Confidence:* high. *Status:* stamps given verbally; **the ratification RECORD is not yet written to the log — this is the top open item.**

**7. Two live incidents surfaced (both handled):**
- **Bootstrap_Log paste corruption (twice).** The F-01 log entry was first committed (`9381dfd`) flattened to a single truncated line; a botched `head`/`mv` recovery then overwrote the working log with only the entry, committing it (`7dbd184`, 422 deletions). Recovered by rebuilding from git history one command at a time; full history restored (`5cd052d`). Root cause: pasting multi-step command blocks with unresolved placeholders instead of one command at a time. *Status:* closed, recorded in the log entry itself.
- **Mid-session live collection.** During ratification, the Task Scheduler **Amendment (23:30 local)** job fired and wrote 5 legitimate production rows (ids 43–47, one per city, all `flag=0`, correctly keyed). First live end-to-end evidence that v2 works in production. A verification script (`verify_f01_migration.py`) falsely reported PROBLEM because it hard-coded `v2 prelim == 0` (frozen-DB assumption). Script bug, not data fault. *Status:* closed; script flagged for non-reuse.

---

## PART 2 — FINDINGS

### F-01 — climate_day derived from issuance time instead of covered day
- **Description:** `collect_city` (v1) set `climate_day` from the product's issuance timestamp. CLI **summary** reports describe the PRIOR day, so summary rows were keyed one day late.
- **Evidence supporting:** all 8 summary bodies on disk carry a `YESTERDAY` block and no `TODAY` block; each stored `climate_day` was exactly one day *after* the `CLIMATE SUMMARY FOR <DATE>` header day. Preliminaries carry `VALID TODAY` + a `TODAY` block and were keyed correctly.
- **Evidence against:** none once bodies were read. (Beforehand, the *timestamp* pattern was ambiguous — see the corrected sub-claim below.)
- **Final adjudication:** **CONFIRMED (with mechanism correction).**
- **Confidence:** high, for all bodies currently on disk.
- **Remaining uncertainty:** the invariant is inductive about NWS CLI format generally; a future oddly-formatted product could violate it. Mitigated: the parser hard-fails rather than guessing.

### F-01 mechanism — CORRECTED sub-finding (KT Rank 5)
- **Old claim (review §1):** summaries are mis-keyed *because they are issued after local midnight / the next morning* — a timezone/post-midnight effect; remedy = recompute from issuance in local standard time.
- **Correction:** the trigger is **report semantics, not issuance hour.** Every `summary` describes YESTERDAY regardless of when issued (an 8 PM summary still covers the prior day). The post-midnight timing was coincidental correlation. The proposed recompute-from-issuance remedy would **not** have fixed it. Covered day must come from the body.
- **Adjudication:** **CORRECTED.** *Confidence:* high (8/8 bodies).

### "RL-FIX-001 register with findings F-01…F-15" — REFUTED (confabulation)
- **Description:** prior-session memory described a fix register with stable IDs F-01–F-15, evidence grades, and acceptance criteria, at `RL-FIX-001_Architectural_Fix_Register.md`.
- **Evidence against:** no such file on disk (vault or pipeline); no such string in vault git history (`git log --all`); the review doc uses **prose sections**, not F-IDs. The only real finding IDs in git are `F1–F3` (Milestone 1b, commit `406080b`) and `F7` (`ccbe391`) — an older single-digit series.
- **Adjudication:** **REFUTED.** No register was created; F-01's resolution was recorded in-place in the review + Bootstrap_Log instead. *Confidence:* high.

### Review doc existence — PARTIALLY CORRECTED
- **Old belief:** `Final_Architectural_Review_2026-07-19.md` was tracked in the vault.
- **Reality:** it was **untracked and absent** until the Architect placed it at the *pipeline* repo root mid-session; now committed there (`96ba6b9`). *Adjudication:* corrected. *Confidence:* high.

### v2 works live — CONFIRMED (bonus, unplanned)
- 5 scheduler-collected rows (ids 43–47) keyed correctly with `flag=0`. First production evidence of the fix end-to-end. *Confidence:* high. *Note:* these rows are ordinary pipeline output, **not** part of the ratified F-01 work.

### Still unverified (carried forward, NOT touched this session)
- **F-13 / 11am ET settlement rule, MIA/AUS special handling** — untouched, still open E4. The review notes one interpretation touches `climate_day`; read the MIAHIGH/AUSHIGH PDFs first.
- Other review findings: F2 forecast collection not running (`[IRR]`), missing `collection_runs` audit rows, scheduler logon type, `UNIQUE(product_id)`, auto-backup ADR, tested restore. All open E4.

---

## PART 3 — CHANGES TO PROJECT UNDERSTANDING

**A. The climate_day bug's mechanism.**
OLD: "summaries mis-keyed because issued after local midnight (timezone effect)." → NEW: "summaries always describe YESTERDAY by report semantics, independent of issuance hour." → WHY: reading the actual bodies showed summaries issued at 1:35 AM *and* the semantic YESTERDAY block; the issuance-hour correlation didn't survive contact with the artifacts. The proposed timezone remedy would have failed.

**B. The fix register.**
OLD: "RL-FIX-001 tracks 15 findings F-01…F-15 with grades and acceptance criteria." → NEW: "No such register exists or ever existed; findings live as prose in the review; real IDs are F1–F3/F7." → WHY: `grep`/`find`/`git log --all` returned nothing. This was memory confabulation. **Treat any richly-structured recollection not backed by a file as a hypothesis until proven on disk.**

**C. Where the review doc lives.**
OLD: "tracked in the vault." → NEW: "was untracked, placed at pipeline repo root mid-session, now committed there." → WHY: searches found it only after the Architect placed it.

**D. The database is LIVE during sessions.**
OLD (implicit): "the DB is a frozen artifact I can assert row counts about." → NEW: "Task Scheduler writes production rows mid-session; any absolute row count is a snapshot, not an invariant." → WHY: the Amendment job fired at 23:30 local and added 5 rows during ratification. Verification scripts must be scoped by id or parser_version, never by total count.

**E. Log-editing is a real hazard.**
OLD (implicit): "appending to a markdown log is trivial." → NEW: "multi-line paste into the log flattened and truncated it twice; recovery required rebuilding from git." → WHY: two corrupt commits (`9381dfd`, `7dbd184`). Lesson institutionalized (Part 6).

---

## PART 4 — CURRENT PROJECT STATE

**Architecture.** Append-only, snapshot-first, dual-timestamp. Collectors are "dumb" (config + storage only). Derived fields (`climate_day`, `report_kind`, top-of-book) are computed *inside* collectors at ingest — acceptable **only** because raw bytes + `parser_version` make re-derivation possible. Keep that invariant sacred.

**Collectors.** `collectors/nws_cli_collector.py` (CLI, **parser v2, live via Task Scheduler for all five cities** — see live rows 43–47). `collectors/kalshi_observation_collector.py` (order-book depth, built, tests pass; **scheduling status not re-verified this session** — was flagged `[ACC][IRR]` highest-priority elsewhere; confirm from disk next session). `collectors/nws_client.py`, `collectors/kalshi_client.py` (raw fetch layers).

**Storage.** `storage/snapshots.py` — content-addressed store; blob bytes live **inside** `pipeline.db` (SQLite WAL); blob + provenance index written in one transaction (no orphans/danglers). `storage/schema.py` — append-only table DDL; now includes `covered_day_issuance_mismatch INTEGER` on `raw_nws_cli`.

**Parser.** v2. `derive_covered_day()` reads the `CLIMATE SUMMARY FOR <DATE>` header (authority) + TODAY/YESTERDAY marker; cross-checks against issuance-derived day; stores a mismatch bitfield (bit0: covered≠issuance; bit1: marker-offset inconsistent); **hard-fails on unparseable header — no silent fallback.**

**Database.** `data/pipeline.db`, WAL. As of last checkpoint: 47 rows in `raw_nws_cli` — v1 prelim 26, v1 summary 8, v2 summary 8 (migration, ids 35–42), v2 prelim 5 (live, ids 43–47). The 8 v1 summaries retain their original (wrong) days as historical evidence. **Both a v1 and v2 row exist for the 8 migrated days.**

**Governance.** Five Invariants; Invariant 3 (Architect-only ratification) is central. Bootstrap_Log (`01_Governance/Bootstrap_Log.md`) is the canonical event record. This session's 6 artifacts were ratified verbally; the **written ratification record is still outstanding.**

**Research.** No V2 forecasting work this session; premature until V1 instrument correctness is fully ratified and read-authority is decided.

**Documentation.** `Final_Architectural_Review_2026-07-19.md` now committed (pipeline root) with a §15 resolution stamp. Session logs `SESSION_LOG_2026-07-15.md`, `-16.md` at pipeline root (note: logs live in *both* the pipeline repo and the vault historically — clarify canonical home).

**Automation.** Task Scheduler CLI jobs (Primary 18:00 / Amendment 23:30 / Final 00:30 local) are **live and firing** (confirmed by rows 43–47). `config.yaml` `collection.nws_cli` may still say `sweeps_per_day: 2` — reconcile with the deployed 3-run schedule (open).

**Testing.** pytest, **73 passing, 0 failing.** New: `tests/test_covered_day.py` (4 tests) + real fixtures `tests/fixtures/cli_phx_{summary,preliminary}_2026-07-15.txt`.

**Known risks.** (1) Double-counting on `climate_day` joins until read-authority is decided. (2) Auto-backup `.gitignore` gap — git does not back up `pipeline.db`; only the manual file backup does. (3) DB mutates mid-session (scheduler). (4) The mechanism invariant is inductive.

**Known technical debt.** Seven untracked scratch scripts in pipeline root (see Part 5). `verify_f01_migration.py` has a frozen-DB bug — do not reuse as-is. `config.yaml` sweep count. Logs' canonical home ambiguity.

**Current blockers.** None blocking *this* work. For downstream (V2/reads): the read-authority decision.

**Critical path.** Write ratification record → decide read-authority (ADR) → confirm Kalshi collector scheduling (`[ACC][IRR]`) → then remaining review findings (forecast collector is `[IRR]`, highest external-cost).

**Outstanding milestones.** V1 instrument correctness (climate_day now fixed; other findings open) → V2 forecasting validation → V3 gated deployment. Still in V1.

---

## PART 5 — IMPORTANT PATHWAYS

**Repositories**
- `C:\Projects\weather-pipeline` — code, DB, tests, automation. HEAD `2d4fca1`.
- `C:\Users\rjkir\Obsidian\Research Lab` — governance/knowledge vault (separate git repo). HEAD `d3b16f2`. Path has a space → quote in Git Bash.

**Governance (vault)**
- `01_Governance/Bootstrap_Log.md` — **canonical event record.** Every milestone/fix/finding entry lives here. Format: `## DATE — TITLE`, then `**Type/Status/…:**` fields, `### FINDINGS`, `### AI PROCESS NOTES (KT Rank 5)`. Future engineers: this is the first file to read for "what happened and why."
- `07_References/{AI_and_Tooling,Bibliography,Concepts,Data_Sources}` — canon reference concepts (ADR-022 hybrid scheme). Note: the earlier-assumed `Concepts/`-only layout was wrong; this is the real structure.

**Documentation (pipeline root)**
- `Final_Architectural_Review_2026-07-19.md` — the B− review; §15 carries the F-01 resolution stamp. Its non-climate_day findings remain open E4. Roadmap for outstanding work lives in its §15 (Immediate Actions) and §16 (Medium-Term).
- `SESSION_LOG_2026-07-15.md`, `SESSION_LOG_2026-07-16.md` — prior session logs.

**Collectors**
- `collectors/nws_cli_collector.py` — CLI collector. Key symbols: `PARSER_VERSION="2"` (l.30), `derive_covered_day` (l.76), `parse_report_kind`, `parse_high_low`, `collect_city`, `collect_all`, `exit_code_for`. `collect_all` isolates per-city failures (Architect ruling: maximize accrual, report truthfully).
- `collectors/kalshi_observation_collector.py` — depth collector (Option B). Confirm scheduling next session.
- `collectors/nws_client.py`, `collectors/kalshi_client.py` — raw fetch.

**Storage**
- `storage/snapshots.py` — `SnapshotStore(db_path)`; methods `snapshot()`, `retrieve(digest)->bytes`, `provenance()`, `orphan_blob_count()`, `dangling_index_count()`. Blobs stored in-DB.
- `storage/schema.py` — `ensure_raw_nws_cli`, `ensure_kalshi_observations`. `raw_nws_cli` now has `covered_day_issuance_mismatch INTEGER`. Note: `CREATE TABLE IF NOT EXISTS` does NOT alter existing tables — schema changes to a live DB need explicit `ALTER TABLE`.

**Core**
- `core/climate_day.py` — `climate_day(city, utc_ts)->date`, fixed standard-time offsets keyed by **lowercase full city name** (`phoenix/nyc/chicago/miami/austin`); raises `ClimateDayError` on unknown city. The bug was never here — it was fed the wrong input.
- `core/config.py` — `cities()` (returns lowercase names), `station()`, `cli_location_id()`, cadence accessors. `config.yaml` at repo root is the declared single source; note the `climate_day` offset dict duplicates the city list (no cross-check — review weakness #11).

**Config**
- `config.yaml` — city→station/series/cli_location_id mappings (all five confirmed against Kalshi settlement sources + Architect rules-page reads). `issuedby == cli_location_id`. Do NOT parse Kalshi ticker strings for semantics (vendor inconsistency: `KXHIGHNY` vs `KXHIGHTPHX`).

**Tests**
- `tests/test_covered_day.py` — F-01 regression (4 tests) on real fixtures.
- `tests/fixtures/cli_phx_summary_2026-07-15.txt`, `cli_phx_preliminary_2026-07-15.txt` — real captured bodies (public NWS text; committed deliberately, per review §16).
- `tests/test_climate_day.py`, `tests/test_kalshi_observations.py` — existing.

**Automation**
- Task Scheduler XML exports in `scheduler/` (Primary/Amendment/Final); `run_cli_collection.bat` wrapper. **Live and firing.**

**Backups**
- `backups/pipeline_pre_f01_migration_20260720_224306.db` — pre-migration snapshot (34 rows), rollback-of-last-resort. `logs/backup_*.log` — auto-backup logs (note the historical gap: the auto-backup committed against a `.gitignore` excluding `data/`/`*.db`, so it backed up zero irreplaceable data — verify remediation).

**Scratch (untracked, pipeline root — decide delete/keep)**
- `query_f01.py`, `read_blob.py`, `read_blobs.py`, `capture_fixtures.py`, `validate_summaries.py`, `migrate_f01_dryrun.py`, `migrate_f01_apply.py`, `verify_f01_migration.py` (⚠ frozen-DB bug — do not reuse as-is).

---

## PART 6 — KNOWLEDGE FUTURE ENGINEERS MUST NOT LOSE

- **Read the artifact, never assert from memory (F1 discipline).** This session's central win *and* its central embarrassment both came from this: reading the bodies confirmed F-01 and corrected its mechanism; failing to check disk had produced a confabulated 15-finding register. Memory summaries are E4 testimony, not observations.
- **Covered day is a property stated in the artifact**, not a function of issuance time. This is the scientific invariant behind parser v2. `report_kind` (TODAY vs YESTERDAY) is the semantic discriminator; the header is the authority for the value.
- **Append-only is sacred.** Corrections are NEW rows under a new `parser_version`, never overwrites. This is why the mis-key was recoverable rather than catastrophic, and why both v1 and v2 rows now coexist. Never `UPDATE`/`DELETE` existing rows to "fix" data.
- **parser_version is the re-derivation lifeline.** Derived-at-ingest fields are only safe because raw bytes + version let you recompute. Every row must carry its parser_version.
- **The DB is live during sessions.** The scheduler writes production rows mid-work. Verification must be scoped by id/parser_version, NEVER by absolute row count. (`verify_f01_migration.py` violated this — learn from it.)
- **`CREATE TABLE IF NOT EXISTS` will not migrate a live table.** Schema changes to `pipeline.db` need explicit `ALTER TABLE`.
- **git does not back up `pipeline.db`** (it's gitignored). `git push` is an off-machine *code* fact, not a data backup. Before any DB mutation: WAL-checkpoint and file-copy the DB, verify the copy.
- **Log-editing is dangerous.** Pasting multi-line content into `Bootstrap_Log.md` flattened and truncated it twice this session. **Rule: one command at a time; never paste a multi-step block with an unresolved placeholder; verify before every commit; recover from git, never force-push.**
- **Never use `/tmp` from Git Bash on Windows** (resolves to `C:\` root → Permission denied). Use repo-local scratch files.
- **Never edit long files in Notepad** (silent truncation). Use an editor that preserves content, or heredocs.
- **Windows editors save CRLF.** Preserve LF (`core.autocrlf=false`); use `newline=""` on read/write when byte-fidelity matters (fixtures, line endings).
- **Ratification is Architect-only (Invariant 3).** The AI verifies; it cannot self-ratify under any framing. "Canon" status of a reference document ≠ per-claim ratification.
- **Do not parse Kalshi ticker strings for semantics.** Vendor inconsistency is documented; apparent regularity is a hypothesis about vendor discipline, not a property of the data.
- **Kalshi settles on the NWS CLI Daily Climate Report**, not raw METAR. `issuedby == cli_location_id` for all five cities.

---

## PART 7 — OPEN QUESTIONS (ranked)

1. **Read authority — which parser_version wins on reads?** *Priority:* highest (blocks any downstream read/V2). *Impact:* high — unfiltered joins double-count 8 days now, more later. *Difficulty:* low-moderate (a rule + maybe a view). *Next:* write an ADR; candidate rule "max(parser_version) per product_id," possibly via a `current_climate_day` view. **Likely irreversible/structural → ADR, not a log line.**
2. **Ratification record not yet written.** *Priority:* high (Invariant 3 compliance). *Impact:* the 6 verbal stamps aren't captured on disk. *Difficulty:* trivial. *Next:* append a ratification entry to Bootstrap_Log (one command at a time).
3. **Kalshi depth collector scheduling** (`[ACC][IRR]`). *Priority:* high — every unsampled interval is permanently lost. *Impact:* high. *Difficulty:* low. *Next:* verify from disk whether it's scheduled; if not, schedule it.
4. **F-13 / 11am ET rule + MIA/AUS handling.** *Priority:* medium-high; touches `climate_day`. *Difficulty:* medium. *Next:* read MIAHIGH/AUSHIGH PDFs first (per review), then encode.
5. **Forecast collector (F2), `[IRR]`.** *Priority:* high external cost (unrecoverable p-side history). *Difficulty:* medium. *Next:* build + schedule.
6. **`collection_runs` audit rows + completeness query.** *Priority:* medium — the V1 gate is a promise until gaps are queryable. *Difficulty:* low-medium.
7. **`config.yaml` sweep count** vs deployed 3-run schedule. *Priority:* low. *Difficulty:* trivial.
8. **Canonical home for session logs** (pipeline vs vault — currently both). *Priority:* low. *Difficulty:* trivial.
9. **Auto-backup remediation status.** *Priority:* medium (data-loss risk). *Next:* verify what the backup actually captures vs `.gitignore`.

---

## PART 8 — RECOMMENDED NEXT SESSION

**Immediate priorities (in order):**
1. **State verification from disk** — both repos' HEAD==origin, suite green, DB row counts by parser_version/kind. Expect the DB to have grown (scheduler).
2. **Write the ratification record** to Bootstrap_Log (one command at a time). Closes the highest-compliance gap.
3. **Read-authority ADR** — decide and document the parser_version read rule. Do this before any code that reads `climate_day`.
4. **Confirm Kalshi collector scheduling** — `[ACC][IRR]`, highest accrual cost.

**Suggested verification order:** repos clean → suite 73 → `raw_nws_cli` counts by (parser_version, report_kind) → confirm the 8 migration rows (ids 35–42) still correct by header-match (frozen-DB-independent) → confirm scheduler still firing.

**Files to open first:** `01_Governance/Bootstrap_Log.md` (what happened); `Final_Architectural_Review_2026-07-19.md` §15/§16 (roadmap); `collectors/nws_cli_collector.py` (the fix); `storage/schema.py` (the new column); `config.yaml` (city mappings).

**Dependencies to understand before coding:** append-only invariant; parser_version re-derivation; that the DB is live; that `climate_day` derives from the body; read-authority is undecided.

**Risks of proceeding incorrectly:** building any read/join before deciding read-authority will double-count the 8 migrated days; mutating the DB without a file backup risks the sole irreplaceable corpus; pasting into the log carelessly corrupts the canonical record.

**Expected deliverables:** ratification record committed; read-authority ADR; Kalshi scheduling confirmed/fixed; scratch scripts cleaned.

---

## PART 9 — EXECUTIVE HANDOFF

**If another engineer sat down tomorrow with only this document:**

- **Understand first:** This is an append-only, snapshot-first measurement instrument for Kalshi daily-high temperature markets, in V1 (correctness) phase. `climate_day` is the settlement key and was mis-derived; it is now fixed (parser v2, `fa0a99f`) and 8 historical rows are migrated (ids 35–42). Ratification is Architect-only. The Bootstrap_Log is the source of truth for history.
- **Mistakes to avoid:** asserting anything from memory without reading the artifact (a confabulated "F-01…F-15 register" cost real time this session); using absolute row counts in verification (the DB is live); pasting multi-line blocks into the log (it corrupted twice); assuming `CREATE TABLE IF NOT EXISTS` migrates a live table; trusting `git push` as a DB backup (it isn't — `pipeline.db` is gitignored).
- **Work on next:** write the ratification record; decide read-authority via ADR; confirm the Kalshi depth collector is scheduled (`[ACC][IRR]`).
- **Do NOT touch yet:** F-13 / 11am ET rule / MIA-AUS handling (read the PDFs first — it may touch `climate_day`); V2 forecasting (premature); any downstream read of `climate_day` (blocked on read-authority); the v1 rows (they are preserved evidence — never overwrite).
- **Single most important insight from today:** **The covered day is stated in the product body; deriving it from the issuance timestamp was the bug. More broadly — read the artifact, because the timestamp (a convenient proxy) and memory (a confabulated register) both lied, and only the bytes told the truth.**

---

### Ledger of ratifications (verbal this session; RECORD PENDING)
1. Parser v2 code (`fa0a99f`) — RATIFIED.
2. Review doc (`96ba6b9`) — RATIFIED as canon; non-climate_day findings remain open E4.
3. §15 resolution stamp (`2d4fca1`) — RATIFIED; mechanism correction = verified-on-current-bodies, not universal law; "migration NOT yet done" line reflects fix-time state, since completed.
4. Migration (ids 35–42, `d3b16f2`) — RATIFIED, scoped by row id; backup intact; append-only; originals preserved. (Live rows 43–47 are NOT part of this — ordinary pipeline output.)
5. Bootstrap_Log RESOLVED entry — RATIFIED.
6. Bootstrap_Log MIGRATION entry — RATIFIED; "34→42" = migration delta, not current total.

**This handoff document is itself E4, pending Architect ratification (Invariant 3).**
