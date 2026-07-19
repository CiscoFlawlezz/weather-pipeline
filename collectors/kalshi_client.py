"""
Kalshi read-only market data client.

WHY THIS EXISTS AS AN ISOLATED MODULE:
Kalshi's API changelog shows active breaking changes (legacy integer
price fields were removed March 2026 in favor of `_dollars` string
fields; fractional trading added `_fp` fields). By keeping ALL Kalshi
parsing in this one file, a future API change means fixing one module,
not hunting through the codebase.

AUTHENTICATION NOTE:
Per the official API docs, market-data endpoints (series, markets,
candlesticks) are served without authentication headers. Your API key
is NOT needed for data collection — it only becomes relevant for
portfolio/order endpoints in a much later milestone. This client
therefore holds no credentials at all, which is also the safest
posture: code that never touches a key can never leak one.

DESIGN RULE (point-in-time integrity):
Every function returns the RAW parsed JSON alongside any convenience
extraction, and callers are expected to store raw responses. If Kalshi
changes its schema, the raw record lets us re-parse history instead of
losing it.
"""

import time
from typing import Optional

import requests

DEFAULT_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Valid candlestick intervals in minutes, per API documentation.
VALID_INTERVALS = (1, 60, 1440)


class KalshiError(Exception):
    """Raised for any non-success Kalshi API response."""


class KalshiClient:
    def __init__(self, base_url: str = DEFAULT_BASE_URL, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # A persistent session reuses TCP connections across calls —
        # faster and friendlier to the API than one connection per request.
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------
    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """GET a path and return parsed JSON, raising KalshiError on failure.

        We raise (rather than return None) so the orchestrator's audit
        log records failures explicitly — 'zero silent failures' is the
        milestone's success criterion.
        """
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise KalshiError(f"Network error calling {url}: {exc}") from exc

        if resp.status_code != 200:
            raise KalshiError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:500]}"
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Public endpoints
    # ------------------------------------------------------------------
    def get_exchange_status(self) -> dict:
        """Cheapest possible connectivity check."""
        return self._get("/exchange/status")

    def get_series(self, series_ticker: str) -> dict:
        """Fetch one series definition. Used to VERIFY candidate tickers
        in config.yaml actually exist — we never assume they do."""
        return self._get(f"/series/{series_ticker}")

    def get_markets(
        self,
        series_ticker: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> dict:
        """List markets, optionally filtered by series and status.

        status examples: 'open', 'closed', 'settled'.
        Returns the raw page including 'cursor' for pagination.
        """
        params: dict = {"limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor
        return self._get("/markets", params=params)

    def get_candlesticks(
        self,
        series_ticker: str,
        market_ticker: str,
        start_ts: int,
        end_ts: int,
        period_interval: int = 60,
    ) -> dict:
        """Fetch candlesticks for one market within a time window.

        start_ts / end_ts are Unix timestamps (seconds).
        period_interval must be 1, 60, or 1440 (minutes) per API docs.

        NOTE: markets settled before Kalshi's historical cutoff move to
        GET /historical/markets/{ticker}/candlesticks. For daily sweeps
        of recent markets this live endpoint is correct; a historical
        backfill module can be added later if we want deep history.
        """
        if period_interval not in VALID_INTERVALS:
            raise ValueError(
                f"period_interval must be one of {VALID_INTERVALS}, "
                f"got {period_interval}"
            )
        params = {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "period_interval": period_interval,
        }
        return self._get(
            f"/series/{series_ticker}/markets/{market_ticker}/candlesticks",
            params=params,
        )

    # ------------------------------------------------------------------
    # Raw fetch (bytes + Date header preserved) for the depth collector
    # ------------------------------------------------------------------
    # M1.T2 needs THREE things _get() throws away:
    #   1. the raw response bytes, to snapshot verbatim (content-addressed);
    #   2. the server Date header, as the per-fetch timestamp used to make
    #      the skew between the two calls of one observation auditable;
    #   3. the parsed JSON, for field extraction.
    # This helper returns all three. It reuses the same session, timeout,
    # and KalshiError as _get so there is one HTTP code path, not two.
    def _get_raw(self, path: str, params: Optional[dict] = None) -> tuple:
        """GET a path; return (parsed_json, raw_bytes, server_date_header).

        server_date_header is the response 'Date' header as a string, or
        None if the server did not send one. Raises KalshiError on any
        network error or non-200 status, exactly like _get.
        """
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise KalshiError(f"Network error calling {url}: {exc}") from exc

        if resp.status_code != 200:
            raise KalshiError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:500]}"
            )

        # resp.content is the raw bytes exactly as received (before any
        # decoding); this is what we snapshot. resp.json() re-parses the
        # same bytes. A malformed body raises ValueError here, which we
        # convert to KalshiError so the collector treats it as a failed
        # fetch and writes no row.
        raw_bytes = resp.content
        server_date = resp.headers.get("Date")
        try:
            parsed = resp.json()
        except ValueError as exc:
            raise KalshiError(f"Malformed JSON from {url}: {exc}") from exc
        return parsed, raw_bytes, server_date

    def get_orderbook_raw(self, ticker: str) -> tuple:
        """Fetch one market's order book. Returns (json, raw_bytes, date).

        The book has the shape {"orderbook_fp": {"yes_dollars": [...],
        "no_dollars": [...]}} where each side is a list of
        [price_string, size_string] pairs. Either side may be empty.
        """
        return self._get_raw(f"/markets/{ticker}/orderbook")

    def get_market_raw(self, ticker: str) -> tuple:
        """Fetch one market's detail object. Returns (json, raw_bytes, date).

        The detail has the shape {"market": {...}} carrying fast-moving
        state (status, volume_fp, open_interest_fp, liquidity_dollars,
        yes_bid/ask, sizes) plus slow-moving reference data.
        """
        return self._get_raw(f"/markets/{ticker}")


# ----------------------------------------------------------------------
# Convenience parsing (kept separate from fetching on purpose)
# ----------------------------------------------------------------------
def summarize_candlestick(c: dict) -> dict:
    """Extract the fields we care about from one raw candlestick.

    Uses the current `_dollars` / `_fp` field names. If Kalshi returns
    the older non-suffixed names on some endpoint, we fall back to them
    rather than crashing — but the RAW candlestick should always be
    stored regardless, so nothing is lost either way.
    """
    def pick(obj: Optional[dict], new_key: str, old_key: str):
        if not obj:
            return None
        return obj.get(new_key, obj.get(old_key))

    price = c.get("price") or {}
    yes_bid = c.get("yes_bid") or {}
    yes_ask = c.get("yes_ask") or {}

    return {
        "end_period_ts": c.get("end_period_ts"),
        "price_close": pick(price, "close_dollars", "close"),
        "price_mean": pick(price, "mean_dollars", "mean"),
        "yes_bid_close": pick(yes_bid, "close_dollars", "close"),
        "yes_ask_close": pick(yes_ask, "close_dollars", "close"),
        "volume": c.get("volume_fp", c.get("volume")),
        "open_interest": c.get("open_interest_fp", c.get("open_interest")),
    }


def yesterday_window() -> tuple[int, int]:
    """Unix-timestamp window covering the last 24 hours.

    Good enough for a connectivity test; the real collector in
    Milestone 1b will compute windows from each market's open/close
    times instead.
    """
    now = int(time.time())
    return now - 24 * 3600, now
