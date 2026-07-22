# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A data-collection instrument (not yet a trading system) for a Prediction Market Research Lab studying Kalshi daily-high-temperature markets across five cities (Phoenix, NYC, Chicago, Miami, Austin). It polls Kalshi market data and NWS weather data on a schedule and appends everything to a local SQLite database with full raw-body provenance. The project is in **V1 (instrument correctness)** phase — no modeling/analysis code exists yet by design.

## Commands

```powershell
# Setup
py -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt

# Run the full test suite (no network calls — everything is mocked)
python -m pytest

# Run a single test file / test
python -m pytest tests/test_covered_day.py
python -m pytest tests/test_collect_all.py::test_chicago_failure_does_not_stop_other_cities

# One-time live integration check (touches real APIs)
python test_connections.py

# Run a collector manually (writes to data/pipeline.db by default)
python -m collectors.nws_cli_collector [db_path]
python -m collectors.kalshi_observation_collector [db_path]

# Back up the live DB (VACUUM INTO + verify, never touches the source)
python scripts/backup_db.py
```

There is no lint/format tooling configured (no pytest.ini/pyproject.toml — pytest runs with defaults; test discovery is the `tests/` directory).

Scheduled execution happens via Windows Task Scheduler (`scheduler/*.xml`) invoking the `.bat` wrappers at the repo root (`run_cli_collection.bat`, `run_kalshi_observations.bat`, `run_backup.bat`). Each wrapper: cds to the repo root, calls the collector as a module, retries once on failure (except backup), appends to a dated log in `logs/`, and propagates a non-zero exit code on failure — never a false success.

## Architecture

**Data flow:** `config.yaml` → `core/config.py` (accessors) → collectors (`collectors/`) → `storage/` (schema + snapshot store) → `data/pipeline.db` (SQLite, WAL mode).

### Non-negotiable design invariants

These are load-bearing across the whole codebase — violating them is a bug, not a style choice:

1. **Append-only, never UPDATE/DELETE.** Corrections are new rows (usually under a bumped `parser_version`/`collector_version`), never overwrites of existing rows. This is what makes bugs like F-01 (below) recoverable instead of catastrophic — always preserve the old rows as historical evidence.
2. **Config is the single source of truth (D4).** No collector/module hardcodes a ticker, station ID, or cadence — everything goes through `core/config.py`, which raises `ConfigError` loudly on any missing key rather than silently defaulting. The one known exception: `core/climate_day.py` hardcodes its own city→UTC-offset table and does **not** cross-check it against `config.yaml`'s city list — a known gap (adding a 6th city requires editing both, uncaught).
3. **Snapshot what you cite.** Every raw body fetched from an external API (CLI report, Kalshi order book/market detail) is stored verbatim, content-addressed by SHA-256, via `storage/snapshots.py::SnapshotStore`. Blob + provenance index row are written in one transaction so the store can never hold an orphan blob or a dangling index row. Parsed/derived columns are only trustworthy convenience — the blob is the ground truth and can always re-derive them.
4. **Derived fields carry their parser/collector version.** Any field computed at ingest time (`climate_day`, `report_kind`, top-of-book) must be re-derivable from the raw snapshot + its version tag. This is what makes fixing a parser bug a data migration instead of data loss.
5. **Failure isolation with truthful exit codes.** Collectors iterate all configured cities/tickers independently — one city's exception does not stop the others (`collect_all` pattern in both collector modules). The process exits non-zero if *any* unit failed, and a "duplicate already stored" skip counts as success, not failure. Task Scheduler's result must never be a false green.
6. **`climate_day` is computed in exactly one place:** `core/climate_day.py::climate_day(city, utc_ts)`. It applies each city's **fixed standard-time offset year-round — no DST is ever applied** (a naive local-daylight-time midnight boundary would silently shift settlement by an hour twice a year). No other module is permitted to compute a settlement day.
7. **The covered day comes from the report body, not the fetch/issuance timestamp.** A CLI *summary* report always describes YESTERDAY regardless of when it was issued; a *preliminary* report describes TODAY. `collectors/nws_cli_collector.py::derive_covered_day()` parses the `CLIMATE SUMMARY FOR <DATE>` header as the authority and hard-fails (raises) rather than silently falling back to issuance time if the header can't be parsed. This was F-01, a real settlement-critical bug fixed in parser v2 — see `SESSION_HANDOFF_2026-07-20_F01.md` for the full adjudication if touching this logic again.

### Module layout

- `core/config.py` — all config access goes through named accessors (`cities()`, `series(city)`, `station(city)`, `cli_location_id(city)`, cadence accessors, etc.). Re-reads and re-parses `config.yaml` on every call (deliberately unoptimized at this scale).
- `core/climate_day.py` — the settlement-day authority (see invariant 6 above).
- `collectors/kalshi_client.py` / `collectors/nws_client.py` — thin, isolated raw-fetch clients per external API. All Kalshi-specific parsing lives in one file because Kalshi's API has active breaking changes (e.g. legacy price fields → `_dollars`/`_fp` string fields); isolating it means an API change means editing one module.
- `collectors/nws_cli_collector.py` — CLI Daily Climate Report collector; this is the **settlement ground truth** stream. `PARSER_VERSION` gates the covered-day derivation logic.
- `collectors/kalshi_observation_collector.py` — order-book depth + market-state snapshots, `[ACC][IRR]` (accrual-critical, irreversible): candlestick OHLC does not preserve the bid/ask ladder, so any 5-minute interval not sampled here is lost forever. An "observation" requires both the order-book fetch and the market-detail fetch to succeed before anything is written.
- `storage/schema.py` — the **live, authoritative** table DDL (`ensure_raw_nws_cli`, `ensure_kalshi_observations`), called by collectors at runtime. Uses `CREATE TABLE IF NOT EXISTS`, which does **not** migrate an already-existing table — schema changes to the live DB need an explicit `ALTER TABLE` (see the F-01 migration for the pattern).
- `storage/schema.sql` — **legacy/aspirational**, not wired into the live code path (`collection_runs`, `nws_forecast_snapshots`, `kalshi_markets`, `kalshi_candlesticks`, `kalshi_settlements` are defined here but nothing currently creates or writes them from this file). Don't assume tables named here exist in `pipeline.db` — check `storage/schema.py` and what the collectors actually call.
- `storage/snapshots.py` — `SnapshotStore`, the content-addressed blob store (see invariant 3).

### Status markers you'll see in docstrings

- `E4 — AI-drafted, pending Architect ratification (Invariant 3)`: this codebase distinguishes AI-authored/AI-verified work from human-ratified work. Most of the code currently carries this marker. Don't treat it as "untested" — it means "not yet formally signed off by the project owner," and it's normal for most of the repo right now.
- References to `F-01`, `F1`–`F3`, findings, invariants, "Architect ruling <date>": these point to decisions recorded in commit history, `Final_Architectural_Review_2026-07-19.md`, and `SESSION_HANDOFF_2026-07-20_F01.md`. If a change touches settlement logic (`climate_day`, CLI parsing, config city mappings), read the relevant section of those docs first — they contain hard-won corrections (e.g. F-01's mechanism was originally misdiagnosed as a timezone bug and was actually a report-semantics bug).

### Known sharp edges (don't "fix" without understanding why they're this way)

- `data/pipeline.db` is a **live, mutating** database — Task Scheduler jobs write to it on their own schedule even during a work session. Never assume an absolute row count is stable; scope verification queries by id range or `parser_version`/`collector_version`.
- `collect_ticker`'s docstring in `kalshi_observation_collector.py` claims single-transaction atomicity with `SnapshotStore`, but `SnapshotStore.snapshot()` opens its own connection and commits independently — the guarantee as documented is not fully true. Known, tracked, not yet fixed.
- Two collectors (5-min Kalshi sweep, daily CLI sweep) write to the same SQLite file on separate connections with no `busy_timeout` set — lock contention is possible and currently surfaces as ordinary per-unit failures.
- `config.yaml` contains a real personal email in `nws.user_agent` and is committed to git (deviates from the example-file pattern referenced in code comments as ADR-015).

## Operational guardrails (non-negotiable)

1. Never auto-run git commit, git push, rm, or any DB write (INSERT/UPDATE/DELETE/ALTER) — always ask for approval first.
2. Before any DB mutation: run scripts/backup_db.py (VACUUM INTO + integrity + row-count + hash verification; the correct WAL-safe method — never a raw file copy). git does NOT back up pipeline.db.
3. Ratification is Architect-only (Invariant 3). You draft E4; you never self-ratify.
4. The DB is live — the Task Scheduler writes rows mid-session. Verify by id or parser_version, never by absolute row count.
5. One task per session. Hard-stop before commits. Read the artifact; never assert from memory.

## Governance corpus

**Read-only from here.** The vault is reference/consult only from this repo's Claude Code session — never write to or commit in the Research Lab vault from here. Any vault edit (Bootstrap_Log entries, ADRs) is done deliberately as a separate, vault-anchored action with its own approval.

**Research Lab vault (separate git repo):** `C:\Users\rjkir\Obsidian\Research Lab` (path has a space — quote it in Git Bash).

- `01_Governance/Bootstrap_Log.md` — CANONICAL event record. Read the last few entries at the start of any session for "what happened and why," and check current HEAD from disk — never pin or assume a specific SHA or latest-entry list here; both go stale the moment the scheduler or auto-backup advances the vault.
- `07_References/{AI_and_Tooling,Bibliography,Concepts,Data_Sources}` — ratified reference concepts (ADR-022 hybrid scheme). Canon technical references (Proper Scoring Rules, Kelly, Forecast Verification, etc.) live under `Concepts`.
- ADRs — architecture decision records; locate the exact folder/numbering on disk before writing a new one (do NOT assume from memory). ADR-022 governs the vault folder scheme.

**In this repo:**

- `Final_Architectural_Review_2026-07-19.md` — B− review; §15 carries the F-01 resolution stamp; §13.1/§15 prescribe the covered-day + read-authority direction.
- `SESSION_HANDOFF_2026-07-20_F01.md` — full transition record from the F-01 session.
