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
            high_temp_f       INTEGER,
            low_temp_f        INTEGER,
            snapshot_hash     TEXT NOT NULL,
            ingest_time_utc   TEXT NOT NULL,
            parser_version    TEXT NOT NULL
        )
        """
    )