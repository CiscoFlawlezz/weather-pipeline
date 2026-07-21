"""
storage/schema.py — append-only table definitions for collected raw data.

raw_nws_cli holds one row PER STORED CLI product. Append-only: an amended
or later report is a NEW ROW sharing the same climate_day, never an
overwrite. report_kind records whether the parsed values came from a
preliminary same-day report or a later/corrected one, so reconciliation
can weight them correctly. high/low are nullable (a report may show MM).

Status: E4 — AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations
import sqlite3


def ensure_raw_nws_cli(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_nws_cli (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            station_id        TEXT NOT NULL,
            location_id       TEXT NOT NULL,
            product_id        TEXT,
            issuance_time_utc TEXT,
            climate_day       TEXT,
            report_kind       TEXT,
            covered_day_issuance_mismatch INTEGER,
            high_temp_f       INTEGER,
            low_temp_f        INTEGER,
            snapshot_hash     TEXT NOT NULL,
            ingest_time_utc   TEXT NOT NULL,
            parser_version    TEXT NOT NULL
        )
        """
    )


def ensure_kalshi_observations(conn: sqlite3.Connection) -> None:
    """Append-only Kalshi order-book + market-state observations (M1.T2).

    One row per successful collection cycle for one ticker. A cycle is
    two fetches (order book + market detail) that BOTH succeed; if either
    fails, no row is written (transactional atomicity of the write).

    Depth is irreversible: candlestick OHLC does not preserve the bid/ask
    ladder. Both ladders are stored verbatim as JSON text (an empty side
    is stored as "[]"). Prices and sizes are kept as TEXT exactly as the
    API returns them (fixed-point strings) so no float rounding is ever
    introduced. Three timestamps are recorded so any skew between the two
    fetches is measurable and auditable, never hidden.

    Slow-moving reference data (settlement rules, strike geometry,
    expiration) is NOT duplicated here; it lives in kalshi_markets. The
    raw market response is snapshotted, so that data remains recoverable.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS kalshi_observations (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker                  TEXT NOT NULL,
            city                    TEXT NOT NULL,
            collected_at            TEXT NOT NULL,
            orderbook_fetch_utc     TEXT,
            market_fetch_utc        TEXT,
            status                  TEXT,
            volume_fp               TEXT,
            volume_24h_fp           TEXT,
            open_interest_fp        TEXT,
            liquidity_dollars       TEXT,
            yes_bid_dollars         TEXT,
            yes_ask_dollars         TEXT,
            no_bid_dollars          TEXT,
            no_ask_dollars          TEXT,
            yes_bid_size_fp         TEXT,
            yes_ask_size_fp         TEXT,
            orderbook_yes_json      TEXT NOT NULL,
            orderbook_no_json       TEXT NOT NULL,
            orderbook_snapshot_hash TEXT NOT NULL,
            market_snapshot_hash    TEXT NOT NULL,
            ingest_time_utc         TEXT NOT NULL,
            collector_version       TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_kobs_ticker_time
            ON kalshi_observations (ticker, collected_at)
        """
    )