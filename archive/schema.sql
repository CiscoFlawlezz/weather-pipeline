-- ============================================================
-- RETIRED 2026-08-06. THIS FILE CREATES NOTHING.
-- ============================================================
-- Retired into archive/ under Final_Architectural_Review_2026-07-19.md
-- section 16 ("Retire schema.sql into an archive/ with a header, single
-- schema authority in schema.py"), by Architect ruling 2026-08-06.
--
-- STATUS: historical design record. Preserved, not deleted, per the
-- project's append-only discipline: corrections supersede, they never
-- erase. Moved with `git mv`, so the full history follows the file.
--
-- storage/schema.py IS THE SOLE SCHEMA AUTHORITY. Live table DDL is
-- ensure_raw_nws_cli() and ensure_kalshi_observations(), called by the
-- collectors at runtime. DO NOT ADD TABLES HERE. A table added to this
-- file will never be created by anything.
--
-- THE SPECIFIC TRAP THIS FILE SETS:
--   The `PRAGMA journal_mode = WAL;` below HAS NEVER EXECUTED. Nothing
--   in the repository reads, opens, or executes this file. WAL is set at
--   runtime, per connection, by
--   storage/snapshots.py::SnapshotStore._connect(). Any document citing
--   "schema.sql line 1" as the REASON pipeline.db runs in WAL mode is
--   making a false causal claim, however true its conclusion. Known
--   instances are tracked separately and are not corrected by this move.
--
-- NONE of the tables defined below exists in the live database. Architect
-- query, 2026-08-05: data/pipeline.db holds exactly five tables --
-- kalshi_observations, raw_nws_cli, snapshot_blob, snapshot_index,
-- sqlite_sequence. collection_runs, nws_forecast_snapshots,
-- nws_observations, kalshi_markets, kalshi_candlesticks and
-- kalshi_settlements are ABSENT.
--
-- collection_runs below is a live design input, not dead weight. It is
-- the starting point for the run-audit table prescribed by section 15.3
-- (Final_Architectural_Review_2026-07-19.md:207 -- collector, started,
-- finished, status, per-unit counts; the daily completeness query is
-- "the gap audit"). Cite this path when that table is built rather than
-- rediscovering the columns.
--
-- Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
-- ============================================================

-- ============================================================
-- Weather Pipeline Schema — Milestone 1 (SQLite)
-- ============================================================
-- Design rules encoded here:
--   1. APPEND-ONLY: no UPDATEs. Corrections are new rows; history
--      is never rewritten. This is what prevents lookahead bias.
--   2. Every row carries collected_at (when WE saw the data) and,
--      where the source provides it, an issued/period timestamp
--      (when the data was TRUE). Both are required for honest
--      point-in-time joins.
--   3. raw_json columns preserve full source payloads so schema
--      changes upstream never destroy information.

PRAGMA journal_mode = WAL;   -- safer concurrent reads while writing

-- ------------------------------------------------------------
-- Audit log: one row per collection run. The success criterion
-- ("14 days, zero silent failures") is measured from this table.
-- A missing expected row here IS a detected failure.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS collection_runs (
    run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at    TEXT NOT NULL,          -- ISO-8601 UTC
    finished_at   TEXT,
    collector     TEXT NOT NULL,          -- 'nws_forecast' | 'kalshi_sweep' | ...
    status        TEXT NOT NULL,          -- 'success' | 'partial' | 'failed'
    rows_written  INTEGER DEFAULT 0,
    error_detail  TEXT
);

-- ------------------------------------------------------------
-- NWS forecast snapshots (the unrecoverable data — poll often)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nws_forecast_snapshots (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    city               TEXT NOT NULL,      -- key from config.yaml
    forecast_issued_at TEXT,               -- updateTime from NWS payload
    collected_at       TEXT NOT NULL,      -- when we fetched it (UTC)
    raw_json           TEXT NOT NULL       -- full forecast payload
);
CREATE INDEX IF NOT EXISTS idx_fc_city_time
    ON nws_forecast_snapshots (city, collected_at);

-- ------------------------------------------------------------
-- NWS station observations (features, NOT settlement ground truth)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS nws_observations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    station_id   TEXT NOT NULL,
    observed_at  TEXT,                     -- timestamp from the payload
    collected_at TEXT NOT NULL,
    raw_json     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obs_station_time
    ON nws_observations (station_id, observed_at);

-- ------------------------------------------------------------
-- Kalshi market definitions (strike ranges, close times, status)
-- Appended each sweep; latest row per ticker = current known state.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kalshi_markets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker        TEXT NOT NULL,
    series_ticker TEXT NOT NULL,
    status        TEXT,
    collected_at  TEXT NOT NULL,
    raw_json      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mkt_ticker ON kalshi_markets (ticker);

-- ------------------------------------------------------------
-- Kalshi candlesticks (recoverable, swept daily)
-- UNIQUE constraint makes re-sweeps idempotent: refetching the same
-- window inserts nothing new instead of duplicating rows.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kalshi_candlesticks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL,
    end_period_ts   INTEGER NOT NULL,     -- Unix ts from Kalshi
    period_interval INTEGER NOT NULL,     -- 1 | 60 | 1440 minutes
    yes_bid_close   TEXT,                 -- _dollars strings kept as TEXT:
    yes_ask_close   TEXT,                 -- exact decimal, no float rounding
    price_close     TEXT,
    price_mean      TEXT,
    volume          TEXT,
    open_interest   TEXT,
    collected_at    TEXT NOT NULL,
    raw_json        TEXT NOT NULL,
    UNIQUE (ticker, end_period_ts, period_interval)
);

-- ------------------------------------------------------------
-- Kalshi settlements (the market-side ground truth)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS kalshi_settlements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker       TEXT NOT NULL UNIQUE,
    result       TEXT,                    -- 'yes' | 'no'
    settled_time TEXT,
    collected_at TEXT NOT NULL,
    raw_json     TEXT NOT NULL
);
