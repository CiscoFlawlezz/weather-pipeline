"""
collectors/kalshi_observation_collector.py -- Kalshi order-book depth +
market-state observation collector (M1.T2).

WHY THIS EXISTS:
Candlestick OHLC permanently destroys the bid/ask ladder. This collector
preserves it. Every configured city's open markets are polled; for each
market ONE observation is taken, where an observation is:

    fetch order book  AND  fetch market detail  -> BOTH succeed  -> write one row

This is [ACC][IRR] data: any interval not sampled here is lost forever.

ATOMICITY (Architect ruling 2026-07-19):
True simultaneity across two REST endpoints is physically impossible and is
NOT required. What IS required: both fetches must succeed before any write,
and the write is one SQLite transaction. If either fetch fails, the WHOLE
observation is discarded -- no partial row, ever. The two server 'Date'
headers are recorded so the skew between the fetches is measurable and
never hidden.

DUPLICATE POLICY (Architect ruling 2026-07-19, option i):
Depth changes every poll; two polls are legitimately distinct observations.
Every successful poll is a new row. No uniqueness constraint. The snapshot
store deduplicates identical raw bytes at the blob level regardless.

SCOPE (Architect ruling 2026-07-19):
All five cities. Open markets discovered live via get_markets(status=open);
never a hardcoded ticker list.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone
from typing import NamedTuple, Optional

from core import config
from collectors.kalshi_client import KalshiClient, KalshiError
from storage.schema import ensure_kalshi_observations
from storage.snapshots import SnapshotStore

COLLECTOR_VERSION = "1"

# Small pause between markets so a five-city sweep never bursts the API.
# At ~60 markets x 2 calls this keeps us far under the read ceiling.
INTER_MARKET_SLEEP_SECONDS = 0.2

# One retry of a whole observation (both fetches) mirrors the R5 wrapper's
# retry-once pattern. If the retry also fails the observation is discarded.
FETCH_RETRIES = 1
RETRY_SLEEP_SECONDS = 2.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------
# Parsing -- pure functions, no network, exercised directly by tests
# ----------------------------------------------------------------------
def extract_ladders(orderbook_json: dict) -> tuple:
    """Return (yes_levels, no_levels) as lists of [price_str, size_str].

    Reads orderbook_fp.yes_dollars / no_dollars. A missing or empty side
    becomes []. Never raises on a well-formed-but-empty book; raises
    KeyError only if orderbook_fp itself is absent (a malformed body),
    which the caller treats as a failed fetch.
    """
    ob = orderbook_json["orderbook_fp"]  # KeyError if absent -> malformed
    yes_levels = ob.get("yes_dollars") or []
    no_levels = ob.get("no_dollars") or []
    return yes_levels, no_levels


def _best_bid(levels: list) -> tuple:
    """Best (highest-price) bid from a ladder side. Returns (price, size).

    Kalshi lists levels ascending by price; the best bid is the last one.
    We do not rely on order: we scan for the max price so a reordered
    payload can never silently give a wrong top-of-book. Empty -> (None, None).
    """
    best_p = None
    best_s = None
    for level in levels:
        price = level[0]
        if best_p is None or float(price) > float(best_p):
            best_p = price
            best_s = level[1] if len(level) > 1 else None
    return best_p, best_s


def derive_top_of_book(yes_levels: list, no_levels: list) -> dict:
    """Derive yes/no bid & ask (as strings) from the two bid ladders.

    On Kalshi the book is two sets of BIDS. A yes ask is the cross of the
    best no bid: yes_ask = 1 - best_no_bid (dollar strings). Asks are only
    derived when the opposing side has depth; otherwise None. Prices are
    kept as strings; the single subtraction for the cross is computed in
    integer cents to avoid float drift, then reformatted to a 4dp string
    matching the API's own format.
    """
    yes_bid, yes_bid_size = _best_bid(yes_levels)
    no_bid, no_bid_size = _best_bid(no_levels)

    def cross(bid_price: Optional[str]) -> Optional[str]:
        if bid_price is None:
            return None
        # dollars string -> integer cents -> 1.0000 - x -> dollars string
        cents = round(float(bid_price) * 100)
        crossed = 100 - cents
        return f"{crossed / 100:.4f}"

    yes_ask = cross(no_bid)   # yes ask implied by best no bid
    no_ask = cross(yes_bid)   # no ask implied by best yes bid

    return {
        "yes_bid_dollars": yes_bid,
        "yes_ask_dollars": yes_ask,
        "no_bid_dollars": no_bid,
        "no_ask_dollars": no_ask,
        "yes_bid_size_fp": yes_bid_size,
        "no_ask_size_fp": None,  # not directly reported; left null
    }


def extract_market_state(market_json: dict) -> dict:
    """Pull the fast-moving Option B fields from a market detail object.

    Slow-moving reference data is deliberately NOT extracted here; it lives
    in kalshi_markets and remains recoverable from the raw snapshot.
    Missing fields become None rather than raising -- the raw snapshot is
    the source of truth, this is a convenience index.
    """
    m = market_json.get("market", {})
    return {
        "status": m.get("status"),
        "volume_fp": m.get("volume_fp"),
        "volume_24h_fp": m.get("volume_24h_fp"),
        "open_interest_fp": m.get("open_interest_fp"),
        "liquidity_dollars": m.get("liquidity_dollars"),
        # market-reported top-of-book, kept for cross-checking the ladder
        "m_yes_bid_dollars": m.get("yes_bid_dollars"),
        "m_yes_ask_dollars": m.get("yes_ask_dollars"),
        "m_no_bid_dollars": m.get("no_bid_dollars"),
        "m_no_ask_dollars": m.get("no_ask_dollars"),
        "m_yes_bid_size_fp": m.get("yes_bid_size_fp"),
        "m_yes_ask_size_fp": m.get("yes_ask_size_fp"),
    }


# ----------------------------------------------------------------------
# One observation -- fetch BOTH, then write atomically
# ----------------------------------------------------------------------
def _fetch_both(client: KalshiClient, ticker: str) -> tuple:
    """Fetch order book and market detail. Return the raw materials.

    Returns (ob_json, ob_bytes, ob_date, mk_json, mk_bytes, mk_date).
    Raises KalshiError if EITHER fetch fails, so the caller writes nothing.
    Order book first, then market detail; both must return before we build
    a row. Retries the WHOLE pair once on failure.
    """
    last_exc = None
    for attempt in range(FETCH_RETRIES + 1):
        try:
            ob_json, ob_bytes, ob_date = client.get_orderbook_raw(ticker)
            mk_json, mk_bytes, mk_date = client.get_market_raw(ticker)
            return ob_json, ob_bytes, ob_date, mk_json, mk_bytes, mk_date
        except KalshiError as exc:
            last_exc = exc
            if attempt < FETCH_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)
    raise last_exc


def collect_ticker(client: KalshiClient, store: SnapshotStore,
                   conn: sqlite3.Connection, city: str, ticker: str,
                   base_url: str) -> str:
    """Take ONE observation for one ticker and append one row.

    Fetch both responses first. Only if both succeed do we snapshot the two
    raw bodies and insert one row -- all inside a single transaction. A
    failure anywhere before commit leaves nothing behind (the snapshot
    calls happen inside the transaction window, and the row insert is last).
    """
    (ob_json, ob_bytes, ob_date,
     mk_json, mk_bytes, mk_date) = _fetch_both(client, ticker)

    # Parse BEFORE writing. A malformed book raises KeyError here, before
    # any snapshot or row -> treated as a failed observation, nothing stored.
    yes_levels, no_levels = extract_ladders(ob_json)
    top = derive_top_of_book(yes_levels, no_levels)
    state = extract_market_state(mk_json)

    collected_at = _utc_now_iso()

    with conn:  # single transaction: snapshots + row commit together
        ob_hash = store.snapshot(
            ob_bytes,
            url=f"{base_url}/markets/{ticker}/orderbook",
            component="kalshi_orderbook",
            fetch_time_utc=ob_date,
        )
        mk_hash = store.snapshot(
            mk_bytes,
            url=f"{base_url}/markets/{ticker}",
            component="kalshi_market",
            fetch_time_utc=mk_date,
        )
        conn.execute(
            """
            INSERT INTO kalshi_observations
                (ticker, city, collected_at, orderbook_fetch_utc,
                 market_fetch_utc, status, volume_fp, volume_24h_fp,
                 open_interest_fp, liquidity_dollars, yes_bid_dollars,
                 yes_ask_dollars, no_bid_dollars, no_ask_dollars,
                 yes_bid_size_fp, yes_ask_size_fp, orderbook_yes_json,
                 orderbook_no_json, orderbook_snapshot_hash,
                 market_snapshot_hash, ingest_time_utc, collector_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker, city, collected_at, ob_date, mk_date,
                state["status"], state["volume_fp"], state["volume_24h_fp"],
                state["open_interest_fp"], state["liquidity_dollars"],
                top["yes_bid_dollars"], top["yes_ask_dollars"],
                top["no_bid_dollars"], top["no_ask_dollars"],
                top["yes_bid_size_fp"], state["m_yes_ask_size_fp"],
                json.dumps(yes_levels), json.dumps(no_levels),
                ob_hash, mk_hash, _utc_now_iso(), COLLECTOR_VERSION,
            ),
        )
    return (f"{city}/{ticker}: stored | yes_lv={len(yes_levels)} "
            f"no_lv={len(no_levels)} | yb={top['yes_bid_dollars']} "
            f"ya={top['yes_ask_dollars']} | ob {ob_hash[:12]}...")


# ----------------------------------------------------------------------
# Sweep orchestration -- per-ticker isolation, truthful exit code
# ----------------------------------------------------------------------
class TickerResult(NamedTuple):
    city: str
    ticker: str
    ok: bool
    message: str


def open_tickers_for_city(client: KalshiClient, city: str) -> list:
    """Return the list of open market tickers for a city's series."""
    series_ticker = config.series(city)
    page = client.get_markets(series_ticker=series_ticker, status="open")
    markets = page.get("markets", []) or []
    return [m["ticker"] for m in markets if m.get("ticker")]


def collect_all(db_path: str) -> list:
    """Sweep every open market of every configured city once.

    Per-ticker isolation: one ticker's failure (network, malformed body)
    does not stop the rest. Discovery failure for a city marks that city's
    entry failed but continues to the next city. Never raises.
    """
    results: list = []
    client = KalshiClient(base_url=config.kalshi_base_url())
    store = SnapshotStore(db_path)
    conn = sqlite3.connect(db_path)
    try:
        ensure_kalshi_observations(conn)
        base_url = config.kalshi_base_url()
        for city in config.cities():
            try:
                tickers = open_tickers_for_city(client, city)
            except Exception as exc:
                results.append(TickerResult(
                    city, "*", False,
                    f"{city}: DISCOVERY FAILED - {type(exc).__name__}: {exc}"))
                continue
            for ticker in tickers:
                try:
                    msg = collect_ticker(client, store, conn, city,
                                         ticker, base_url)
                    results.append(TickerResult(city, ticker, True, msg))
                except Exception as exc:
                    results.append(TickerResult(
                        city, ticker, False,
                        f"{city}/{ticker}: FAILED - {type(exc).__name__}: {exc}"))
                time.sleep(INTER_MARKET_SLEEP_SECONDS)
    finally:
        conn.close()
    return results


def exit_code_for(results) -> int:
    """0 only if every attempted ticker succeeded; 1 if any failed.

    An empty sweep (no open markets anywhere) is exit 0 -- nothing failed.
    """
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    import sys
    from pathlib import Path
    db = sys.argv[1] if len(sys.argv) > 1 else "data/pipeline.db"
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    results = collect_all(db)
    for r in results:
        print(r.message)
    print(f"-- {len(results)} observations attempted, "
          f"{sum(1 for r in results if r.ok)} ok")
    sys.exit(exit_code_for(results))