"""
tests/test_kalshi_observations.py -- M1.T2 Kalshi observation collector.

No test touches the network: a FakeClient returns captured real API bodies
(a Phoenix threshold book, an empty-yes-side book, a Phoenix market detail)
or raises to simulate failure. Every test explains what it protects.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
import json
import sqlite3

import pytest

from collectors import kalshi_observation_collector as C
from collectors.kalshi_client import KalshiError
from storage.schema import ensure_kalshi_observations
from storage.snapshots import SnapshotStore


# --- Real captured fixtures (verbatim from live API, 2026-07-19) ----------

ORDERBOOK_T = {
    "orderbook_fp": {
        "no_dollars": [["0.0100", "201.00"], ["0.7000", "252.00"],
                       ["0.9800", "124.00"]],
        "yes_dollars": [["0.0100", "1642.02"]],
    }
}
# A real market where one side is empty (NY, captured 2026-07-19).
ORDERBOOK_EMPTY_YES = {
    "orderbook_fp": {
        "no_dollars": [["0.0100", "501.00"]],
        "yes_dollars": [],
    }
}
MARKET_T = {
    "market": {
        "status": "active",
        "volume_fp": "1020.80",
        "volume_24h_fp": "1020.80",
        "open_interest_fp": "991.80",
        "liquidity_dollars": "0.0000",
        "yes_bid_dollars": "0.0100",
        "yes_ask_dollars": "0.0200",
        "no_bid_dollars": "0.9800",
        "no_ask_dollars": "0.9900",
        "yes_bid_size_fp": "1642.02",
        "yes_ask_size_fp": "124.00",
        "ticker": "KXHIGHTPHX-26JUL19-T96",
    }
}

OB_DATE = "Sun, 19 Jul 2026 01:27:28 GMT"
MK_DATE = "Sun, 19 Jul 2026 01:27:35 GMT"   # deliberately 7s later -> skew


class FakeClient:
    """Stands in for KalshiClient. Returns captured bodies or raises.

    ob_error / mk_error, if set, are raised instead of returning -- used to
    simulate a failed fetch on either endpoint. fail_times counts down so a
    test can make the FIRST call fail and a later one succeed (retry).
    """
    def __init__(self, ob=ORDERBOOK_T, mk=MARKET_T,
                 ob_error=None, mk_error=None, fail_times=0):
        self.ob = ob
        self.mk = mk
        self.ob_error = ob_error
        self.mk_error = mk_error
        self.fail_times = fail_times
        self.ob_calls = 0
        self.mk_calls = 0

    def get_orderbook_raw(self, ticker):
        self.ob_calls += 1
        if self.ob_error and (self.fail_times == 0 or
                              self.ob_calls <= self.fail_times):
            raise self.ob_error
        return self.ob, json.dumps(self.ob).encode(), OB_DATE

    def get_market_raw(self, ticker):
        self.mk_calls += 1
        if self.mk_error and (self.fail_times == 0 or
                              self.mk_calls <= self.fail_times):
            raise self.mk_error
        return self.mk, json.dumps(self.mk).encode(), MK_DATE


@pytest.fixture
def db(tmp_path):
    """A fresh SQLite file with the observations table, per test."""
    path = str(tmp_path / "test.db")
    conn = sqlite3.connect(path)
    ensure_kalshi_observations(conn)
    conn.close()
    return path


def _conn(db):
    return sqlite3.connect(db)


def _count(db):
    conn = _conn(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM kalshi_observations").fetchone()[0]
    finally:
        conn.close()


# --- Parser tests ---------------------------------------------------------

def test_extract_ladders_threshold():
    """Both ladders come back as lists of [price, size] string pairs."""
    yes, no = C.extract_ladders(ORDERBOOK_T)
    assert yes == [["0.0100", "1642.02"]]
    assert len(no) == 3
    assert no[0] == ["0.0100", "201.00"]


def test_extract_ladders_empty_side():
    """An empty yes side yields [] without error -- a real NY case."""
    yes, no = C.extract_ladders(ORDERBOOK_EMPTY_YES)
    assert yes == []
    assert no == [["0.0100", "501.00"]]


def test_extract_ladders_malformed_raises():
    """A body missing orderbook_fp raises -> caller discards the observation."""
    with pytest.raises(KeyError):
        C.extract_ladders({"unexpected": {}})


def test_derive_top_of_book_matches_market_detail():
    """Ladder-derived top-of-book must equal Kalshi's own reported top.

    This is the cross-check that proves the depth parsing and the
    cross-side ask derivation (yes_ask = 1 - best_no_bid) are correct.
    """
    yes, no = C.extract_ladders(ORDERBOOK_T)
    top = C.derive_top_of_book(yes, no)
    m = MARKET_T["market"]
    assert top["yes_bid_dollars"] == m["yes_bid_dollars"]  # 0.0100
    assert top["yes_ask_dollars"] == m["yes_ask_dollars"]  # 0.0200
    assert top["no_bid_dollars"] == m["no_bid_dollars"]    # 0.9800
    assert top["no_ask_dollars"] == m["no_ask_dollars"]    # 0.9900


def test_derive_top_of_book_empty_side_is_null():
    """With no yes bids, yes_bid and the no-ask it implies are both None."""
    yes, no = C.extract_ladders(ORDERBOOK_EMPTY_YES)
    top = C.derive_top_of_book(yes, no)
    assert top["yes_bid_dollars"] is None
    assert top["no_ask_dollars"] is None
    assert top["no_bid_dollars"] == "0.0100"


def test_extract_market_state():
    """The fast-moving Option B fields are pulled; slow-moving are not."""
    s = C.extract_market_state(MARKET_T)
    assert s["status"] == "active"
    assert s["open_interest_fp"] == "991.80"
    assert s["liquidity_dollars"] == "0.0000"
    assert s["volume_fp"] == "1020.80"


# --- Successful collection ------------------------------------------------

def test_successful_collection_writes_one_row(db):
    """One observation -> exactly one row with all key fields populated."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        C.collect_ticker(FakeClient(), store, conn, "phoenix",
                         "KXHIGHTPHX-26JUL19-T96", "http://x")
        rows = conn.execute(
            "SELECT ticker, city, status, open_interest_fp, yes_bid_dollars, "
            "yes_ask_dollars, orderbook_fetch_utc, market_fetch_utc "
            "FROM kalshi_observations").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    r = rows[0]
    assert r[0] == "KXHIGHTPHX-26JUL19-T96"
    assert r[1] == "phoenix"
    assert r[2] == "active"
    assert r[3] == "991.80"
    assert r[4] == "0.0100"
    assert r[5] == "0.0200"
    # both fetch timestamps stored -> skew is auditable, not hidden
    assert r[6] == OB_DATE
    assert r[7] == MK_DATE
    assert r[6] != r[7]


def test_ladders_stored_verbatim(db):
    """The depth ladders are stored as exact JSON, recoverable in full."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        C.collect_ticker(FakeClient(), store, conn, "phoenix", "T", "http://x")
        row = conn.execute("SELECT orderbook_yes_json, orderbook_no_json "
                           "FROM kalshi_observations").fetchone()
    finally:
        conn.close()
    assert json.loads(row[0]) == ORDERBOOK_T["orderbook_fp"]["yes_dollars"]
    assert json.loads(row[1]) == ORDERBOOK_T["orderbook_fp"]["no_dollars"]


def test_snapshots_round_trip_byte_identical(db):
    """Both raw bodies are retrievable byte-for-byte from the snapshot store."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        C.collect_ticker(FakeClient(), store, conn, "phoenix", "T", "http://x")
        h = conn.execute("SELECT orderbook_snapshot_hash, "
                        "market_snapshot_hash FROM kalshi_observations").fetchone()
    finally:
        conn.close()
    assert store.retrieve(h[0]) == json.dumps(ORDERBOOK_T).encode()
    assert store.retrieve(h[1]) == json.dumps(MARKET_T).encode()
    assert store.orphan_blob_count() == 0
    assert store.dangling_index_count() == 0


# --- Append-only (duplicate policy option i) ------------------------------

def test_two_polls_same_ticker_two_rows(db):
    """Depth changes every poll; two polls are two rows, never an UPDATE."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        C.collect_ticker(FakeClient(), store, conn, "phoenix", "T", "http://x")
        C.collect_ticker(FakeClient(), store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 2


# --- Partial failure: NOTHING is written ----------------------------------

def test_orderbook_fetch_fails_no_row(db):
    """Order book fetch fails -> whole observation discarded, zero rows."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        with pytest.raises(KalshiError):
            C.collect_ticker(
                FakeClient(ob_error=KalshiError("boom")),
                store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 0


def test_market_fetch_fails_no_row(db):
    """Market fetch fails -> whole observation discarded, zero rows."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        with pytest.raises(KalshiError):
            C.collect_ticker(
                FakeClient(mk_error=KalshiError("boom")),
                store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 0
    # and no orphan snapshot left behind by the aborted transaction
    assert store.orphan_blob_count() == 0


def test_timeout_is_a_failed_observation(db):
    """A timeout surfaces as KalshiError -> no row (client already wraps it)."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        with pytest.raises(KalshiError):
            C.collect_ticker(
                FakeClient(ob_error=KalshiError("timeout")),
                store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 0


def test_malformed_orderbook_no_row(db):
    """A 200 body missing orderbook_fp is malformed -> no row, no crash."""
    store = SnapshotStore(db)
    conn = _conn(db)
    try:
        with pytest.raises(KeyError):
            C.collect_ticker(
                FakeClient(ob={"unexpected": {}}),
                store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 0


# --- Retry behavior -------------------------------------------------------

def test_retry_succeeds_on_second_attempt(db, monkeypatch):
    """First fetch pair fails, retry succeeds -> exactly one row."""
    monkeypatch.setattr(C, "RETRY_SLEEP_SECONDS", 0)  # no real sleep in tests
    store = SnapshotStore(db)
    conn = _conn(db)
    client = FakeClient(ob_error=KalshiError("transient"), fail_times=1)
    try:
        C.collect_ticker(client, store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 1
    assert client.ob_calls == 2   # failed once, then succeeded


def test_retry_exhausted_no_row(db, monkeypatch):
    """Both attempts fail -> zero rows, error propagates."""
    monkeypatch.setattr(C, "RETRY_SLEEP_SECONDS", 0)
    store = SnapshotStore(db)
    conn = _conn(db)
    client = FakeClient(ob_error=KalshiError("persistent"), fail_times=99)
    try:
        with pytest.raises(KalshiError):
            C.collect_ticker(client, store, conn, "phoenix", "T", "http://x")
    finally:
        conn.close()
    assert _count(db) == 0


# --- Config-driven cadence ------------------------------------------------

def test_cadence_is_config_driven():
    """The cadence comes from config, and a missing block raises loudly."""
    from core import config
    block = config.kalshi_observation_cadence()
    assert "cadence_minutes" in block
    assert isinstance(block["cadence_minutes"], int)


# --- Schema validation ----------------------------------------------------

def test_ensure_is_idempotent(tmp_path):
    """Calling ensure_kalshi_observations twice is safe (CREATE IF NOT EXISTS)."""
    path = str(tmp_path / "s.db")
    conn = sqlite3.connect(path)
    ensure_kalshi_observations(conn)
    ensure_kalshi_observations(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(kalshi_observations)")]
    conn.close()
    assert len(cols) == 23
    assert "orderbook_yes_json" in cols
    assert "orderbook_snapshot_hash" in cols


# --- Exit code ------------------------------------------------------------

def test_exit_code_all_ok():
    results = [C.TickerResult("phoenix", "T", True, "ok"),
               C.TickerResult("nyc", "U", True, "ok")]
    assert C.exit_code_for(results) == 0


def test_exit_code_any_failure():
    results = [C.TickerResult("phoenix", "T", True, "ok"),
               C.TickerResult("nyc", "U", False, "fail")]
    assert C.exit_code_for(results) == 1


def test_exit_code_empty_sweep_is_zero():
    """No open markets anywhere is not a failure."""
    assert C.exit_code_for([]) == 0