"""
scripts/backup_db.py - consistent, verified, versioned snapshot of pipeline.db.

WHY VACUUM INTO AND NOT A FILE COPY
-----------------------------------
pipeline.db runs in WAL mode (storage/schema.sql line 1). In WAL mode, committed
rows may live in pipeline.db-wal and not yet in pipeline.db itself. Copying the
main file mid-write therefore captures a TORN database: it opens, it hashes, it
looks fine, and it is silently missing data. VACUUM INTO takes a read lock and
emits a single transactionally consistent file. It never blocks the collector
and never writes to the live database.

WHAT THIS SCRIPT GUARANTEES
---------------------------
1. Read-only against the live DB. Worst case it produces nothing; it can never
   damage the source.
2. The COPY is verified, not the original. A check that passes because the
   source was healthy tells you nothing about the bytes you would restore from.
3. On any failure, the previous good generation is left untouched. A backup
   system that overwrites a good copy with a corrupt one is worse than none.

Exit codes: 0 = verified good. Non-zero = failure (Task Scheduler shows red).

Status: E4 - AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import gzip
import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

# ---- Configuration -------------------------------------------------------
LIVE_DB = Path(r"C:\Projects\weather-pipeline\data\pipeline.db")
BACKUP_DIR = Path(r"D:\Backups\weather-pipeline")
HEALTH_LOG = Path(r"C:\Projects\weather-pipeline\logs\backup_health.log")

# Tables whose row counts are compared live-vs-snapshot.
COUNTED_TABLES = ["raw_nws_cli", "snapshot_blob", "snapshot_index"]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_line(text: str) -> None:
    """Append one line to the health log and echo it to stdout."""
    line = f"[{utc_now()}] {text}"
    print(line)
    try:
        HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(HEALTH_LOG, "a", encoding="utf-8", newline="") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"WARNING: could not write health log: {e}")


def fail(msg: str, code: int = 1) -> None:
    log_line(f"BACKUP FAILED - {msg}")
    sys.exit(code)


def table_counts(db_path: Path) -> dict[str, int]:
    """Row count per table. Missing table -> -1 (recorded, not fatal)."""
    counts: dict[str, int] = {}
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for t in COUNTED_TABLES:
            try:
                counts[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[t] = -1
    finally:
        conn.close()
    return counts


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    log_line("=" * 60)
    log_line("Backup run starting")

    # --- 1. Preconditions -------------------------------------------------
    if not LIVE_DB.exists():
        fail(f"live DB not found: {LIVE_DB}", 10)

    if not BACKUP_DIR.parent.exists():
        fail(f"backup drive not available: {BACKUP_DIR.parent} "
             f"(is the external drive connected?)", 11)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    live_size = LIVE_DB.stat().st_size
    log_line(f"Live DB: {LIVE_DB} ({live_size:,} bytes)")

    # --- 2. Read live row counts (read-only URI; cannot write) -----------
    try:
        live_counts = table_counts(LIVE_DB)
    except sqlite3.Error as e:
        fail(f"cannot read live DB: {e}", 12)
    log_line(f"Live row counts: {live_counts}")

    # --- 3. VACUUM INTO a temp file --------------------------------------
    # Temp first, so a failure never lands a partial file in the backup dir.
    stamp = datetime.now().strftime("%Y-%m-%d")
    tmp_dir = Path(tempfile.mkdtemp(prefix="pipeline_backup_"))
    tmp_snap = tmp_dir / f"pipeline_{stamp}.db"

    try:
        conn = sqlite3.connect(f"file:{LIVE_DB}?mode=ro", uri=True)
        try:
            # VACUUM INTO requires the target to not exist.
            conn.execute("VACUUM INTO ?", (str(tmp_snap),))
        finally:
            conn.close()
    except sqlite3.Error as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"VACUUM INTO failed: {e}", 13)

    if not tmp_snap.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail("VACUUM INTO reported success but produced no file", 14)

    log_line(f"Snapshot created: {tmp_snap.stat().st_size:,} bytes")

    # --- 4. Verify the SNAPSHOT (not the original) -----------------------
    try:
        conn = sqlite3.connect(f"file:{tmp_snap}?mode=ro", uri=True)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"snapshot unreadable: {e}", 15)

    if result != "ok":
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"snapshot integrity_check returned '{result}' - "
             f"previous generation left untouched", 16)
    log_line("Snapshot integrity_check: ok")

    # --- 5. Row counts must match ----------------------------------------
    snap_counts = table_counts(tmp_snap)
    if snap_counts != live_counts:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"row count mismatch - live={live_counts} snapshot={snap_counts}", 17)
    log_line(f"Row counts match: {snap_counts}")

    # --- 6. Compress ------------------------------------------------------
    tmp_gz = tmp_dir / f"pipeline_{stamp}.db.gz"
    try:
        with open(tmp_snap, "rb") as src, gzip.open(tmp_gz, "wb", compresslevel=9) as dst:
            shutil.copyfileobj(src, dst)
    except OSError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"compression failed: {e}", 18)

    gz_size = tmp_gz.stat().st_size
    log_line(f"Compressed: {gz_size:,} bytes")

    # --- 7. Verify the gzip round-trips ----------------------------------
    # A .gz that cannot be decompressed is not a backup.
    try:
        with gzip.open(tmp_gz, "rb") as f:
            while f.read(1024 * 1024):
                pass
    except OSError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"gzip verification failed - archive is corrupt: {e}", 19)
    log_line("Gzip decompress test: ok")

    # --- 8. Hash and move into place -------------------------------------
    digest = sha256_file(tmp_gz)

    final_gz = BACKUP_DIR / f"pipeline_{stamp}.db.gz"
    final_sha = BACKUP_DIR / f"pipeline_{stamp}.db.gz.sha256"

    try:
        shutil.move(str(tmp_gz), str(final_gz))
        with open(final_sha, "w", encoding="utf-8", newline="") as f:
            f.write(f"{digest}  pipeline_{stamp}.db.gz\n")
    except OSError as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        fail(f"could not write to backup dir: {e}", 20)

    shutil.rmtree(tmp_dir, ignore_errors=True)

    # --- 9. Re-hash what actually landed on disk -------------------------
    # Verifies the bytes at rest, not the bytes we thought we wrote.
    landed = sha256_file(final_gz)
    if landed != digest:
        fail(f"hash mismatch after write - disk copy is corrupt "
             f"(expected {digest[:16]}, got {landed[:16]})", 21)

    generations = len(list(BACKUP_DIR.glob("pipeline_*.db.gz")))

    log_line(f"BACKUP OK  {final_gz.name}  {gz_size:,} bytes  "
             f"sha256 {digest[:16]}...  rows {snap_counts}  "
             f"generations {generations}")
    sys.exit(0)


if __name__ == "__main__":
    main()
