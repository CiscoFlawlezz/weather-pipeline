"""
storage/snapshots.py — content-addressed snapshot store with provenance index.

Purpose (Invariant 4, "snapshot what you cite"):
Every raw body we ingest (a CLI Daily Climate Report, a Kalshi rules page,
an API response) is stored verbatim, addressed by the SHA-256 hash of its
own bytes. Alongside every blob, exactly one index row records where it came
from and when. Blob and index row are written in the SAME database
transaction, so the store can never hold an orphan blob (no index row) or a
dangling index row (no blob). If the process is killed mid-write, the
transaction rolls back and neither exists — the store stays consistent.

Design:
- Hash algorithm: SHA-256 (fixed by ADR before the store holds objects).
- Blob storage: the blob bytes live IN the SQLite database, in the same
  file as the index, so a single transaction spans both. This sidesteps
  the classic failure of writing a file to disk and a DB row separately
  (two writes that can diverge). Snapshots are small (KB-scale text), so
  in-DB storage is appropriate here.
- Append-only: a hash that already exists is a no-op re-store (idempotent);
  its index row is preserved, and a new provenance row is added recording
  that this content was seen again from this source at this time.

Status: E4 — AI-drafted, pending Architect ratification (Invariant 3).
Governs / governed by: M1.T6 hashing ADR.
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


HASH_ALGORITHM = "sha256"


def _utc_now_iso() -> str:
    """Current time as an ISO-8601 UTC string (ingest timestamp)."""
    return datetime.now(timezone.utc).isoformat()


def _hash_bytes(content: bytes) -> str:
    """Return the hex SHA-256 of content."""
    return hashlib.sha256(content).hexdigest()


class SnapshotStore:
    """A content-addressed store backed by a single SQLite file.

    Two tables:
      snapshot_blob(hash PRIMARY KEY, content BLOB, byte_len, algorithm)
      snapshot_index(id, hash, url, component, fetch_time_utc, ingest_time_utc)

    One blob row per unique content hash. One index row per (fetch event),
    so re-seeing the same content from the same source is recorded as a new
    provenance row without duplicating the blob.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot_blob (
                    hash       TEXT PRIMARY KEY,
                    content    BLOB NOT NULL,
                    byte_len   INTEGER NOT NULL,
                    algorithm  TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshot_index (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash            TEXT NOT NULL,
                    url             TEXT NOT NULL,
                    component       TEXT NOT NULL,
                    fetch_time_utc  TEXT,
                    ingest_time_utc TEXT NOT NULL,
                    FOREIGN KEY (hash) REFERENCES snapshot_blob(hash)
                )
                """
            )

    def snapshot(
        self,
        content: bytes,
        url: str,
        component: str,
        fetch_time_utc: str | None = None,
    ) -> str:
        """Store content and record its provenance. Return the content hash.

        blob + index row are committed together. If anything raises before
        commit, the context manager rolls back and neither persists.
        """
        if not isinstance(content, (bytes, bytearray)):
            raise TypeError("content must be bytes; snapshot raw bodies verbatim")

        content = bytes(content)
        digest = _hash_bytes(content)

        conn = self._connect()
        try:
            with conn:  # single transaction: commits on success, rolls back on error
                # INSERT OR IGNORE keeps the store idempotent: identical
                # content is stored exactly once, but we still add a fresh
                # provenance row every time it is seen.
                conn.execute(
                    """
                    INSERT OR IGNORE INTO snapshot_blob (hash, content, byte_len, algorithm)
                    VALUES (?, ?, ?, ?)
                    """,
                    (digest, content, len(content), HASH_ALGORITHM),
                )
                ingest_time = _utc_now_iso()
                conn.execute(
                    """
                    INSERT INTO snapshot_index
                        (hash, url, component, fetch_time_utc, ingest_time_utc)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (digest, url, component, fetch_time_utc, ingest_time),
                )
        finally:
            conn.close()
        return digest

    def retrieve(self, digest: str) -> bytes:
        """Return the stored bytes for a hash, verifying integrity.

        Re-hashes on read: if the stored content no longer matches its hash,
        the store is corrupt and we raise rather than return bad evidence.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT content FROM snapshot_blob WHERE hash = ?", (digest,)
            ).fetchone()
        finally:
            conn.close()
        if row is None:
            raise KeyError(f"no snapshot with hash {digest}")
        content = row[0]
        if _hash_bytes(content) != digest:
            raise ValueError(
                f"integrity failure: stored content does not match hash {digest}"
            )
        return content

    def provenance(self, digest: str) -> list[dict]:
        """Return all index rows for a hash, newest ingest first."""
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT id, hash, url, component, fetch_time_utc, ingest_time_utc
                FROM snapshot_index WHERE hash = ?
                ORDER BY ingest_time_utc DESC, id DESC
                """,
                (digest,),
            ).fetchall()
        finally:
            conn.close()
        return [
            {
                "id": r[0],
                "hash": r[1],
                "url": r[2],
                "component": r[3],
                "fetch_time_utc": r[4],
                "ingest_time_utc": r[5],
            }
            for r in rows
        ]

    def orphan_blob_count(self) -> int:
        """Blobs with no index row. Must always be zero."""
        conn = self._connect()
        try:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM snapshot_blob b
                WHERE NOT EXISTS (
                    SELECT 1 FROM snapshot_index i WHERE i.hash = b.hash
                )
                """
            ).fetchone()[0]
        finally:
            conn.close()
        return n

    def dangling_index_count(self) -> int:
        """Index rows pointing at a missing blob. Must always be zero."""
        conn = self._connect()
        try:
            n = conn.execute(
                """
                SELECT COUNT(*) FROM snapshot_index i
                WHERE NOT EXISTS (
                    SELECT 1 FROM snapshot_blob b WHERE b.hash = i.hash
                )
                """
            ).fetchone()[0]
        finally:
            conn.close()
        return n