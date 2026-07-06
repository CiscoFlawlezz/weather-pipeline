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
