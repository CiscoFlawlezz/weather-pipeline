"""
tests/test_snapshots.py — acceptance tests for storage/snapshots.py.

The load-bearing test is the consistency guarantee: no code path can
create a blob without an index row, or an index row without a blob.
We prove it two ways — a simulated mid-write failure (rolls back to
neither) and audit queries that must always return zero.
"""

import sqlite3

import pytest

from storage.snapshots import SnapshotStore


def _store(tmp_path):
    return SnapshotStore(tmp_path / "snap.db")


# --- Round trip: store, retrieve, hash-verify -----------------------------

def test_store_and_retrieve_roundtrip(tmp_path):
    store = _store(tmp_path)
    body = b"CLIMATE REPORT... MAX TEMPERATURE 104\n"
    digest = store.snapshot(body, url="https://example/cli", component="nws_cli")
    assert store.retrieve(digest) == body


def test_hash_is_content_addressed(tmp_path):
    store = _store(tmp_path)
    d1 = store.snapshot(b"same bytes", url="u1", component="c")
    d2 = store.snapshot(b"same bytes", url="u2", component="c")
    # identical content -> identical hash, stored once
    assert d1 == d2


def test_different_content_different_hash(tmp_path):
    store = _store(tmp_path)
    d1 = store.snapshot(b"body A", url="u", component="c")
    d2 = store.snapshot(b"body B", url="u", component="c")
    assert d1 != d2


# --- Provenance: every fetch event recorded -------------------------------

def test_reseen_content_adds_provenance_row_not_blob(tmp_path):
    store = _store(tmp_path)
    digest = store.snapshot(b"dup", url="u1", component="c", fetch_time_utc="t1")
    store.snapshot(b"dup", url="u2", component="c", fetch_time_utc="t2")
    prov = store.provenance(digest)
    # two provenance rows for one content hash
    assert len(prov) == 2
    urls = {p["url"] for p in prov}
    assert urls == {"u1", "u2"}


def test_provenance_records_component_and_ingest(tmp_path):
    store = _store(tmp_path)
    digest = store.snapshot(b"x", url="u", component="nws_cli")
    prov = store.provenance(digest)
    assert prov[0]["component"] == "nws_cli"
    assert prov[0]["ingest_time_utc"] is not None


# --- Integrity ------------------------------------------------------------

def test_retrieve_missing_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(KeyError):
        store.retrieve("0" * 64)


def test_retrieve_detects_corruption(tmp_path):
    store = _store(tmp_path)
    digest = store.snapshot(b"trustworthy", url="u", component="c")
    # tamper with the stored blob directly, behind the store's back
    conn = sqlite3.connect(store.db_path)
    conn.execute("UPDATE snapshot_blob SET content = ? WHERE hash = ?",
                 (b"tampered", digest))
    conn.commit()
    conn.close()
    with pytest.raises(ValueError):
        store.retrieve(digest)


def test_non_bytes_rejected(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(TypeError):
        store.snapshot("a string, not bytes", url="u", component="c")


# --- The consistency guarantee: no orphans, no danglers -------------------

def test_no_orphans_or_danglers_after_normal_use(tmp_path):
    store = _store(tmp_path)
    for i in range(5):
        store.snapshot(f"body {i}".encode(), url=f"u{i}", component="c")
    assert store.orphan_blob_count() == 0
    assert store.dangling_index_count() == 0


def test_kill_between_writes_rolls_back_to_neither(tmp_path, monkeypatch):
    """Simulate a crash after the blob insert but before the index insert.

    Because both inserts share one transaction (the `with conn:` block),
    an exception before commit must roll BOTH back — leaving neither a
    blob nor an index row. This is the kill-between-write acceptance test.

    We inject the failure at the point where the store builds the index
    row: we replace _utc_now_iso (called between the two INSERTs, to stamp
    the index row) with a function that raises. The blob INSERT has already
    executed inside the transaction; the exception then aborts the block
    before commit, and the `with conn:` context manager rolls everything back.
    """
    import storage.snapshots as snap

    store = snap.SnapshotStore(tmp_path / "snap.db")

    def boom():
        raise RuntimeError("simulated crash mid-transaction")

    monkeypatch.setattr(snap, "_utc_now_iso", boom)

    with pytest.raises(RuntimeError):
        store.snapshot(b"doomed body", url="u", component="c")

    monkeypatch.undo()

    # Audit: the doomed write left neither a blob nor an index row.
    assert store.orphan_blob_count() == 0
    assert store.dangling_index_count() == 0
    conn = sqlite3.connect(store.db_path)
    blobs = conn.execute("SELECT COUNT(*) FROM snapshot_blob").fetchone()[0]
    idx = conn.execute("SELECT COUNT(*) FROM snapshot_index").fetchone()[0]
    conn.close()
    assert blobs == 0
    assert idx == 0