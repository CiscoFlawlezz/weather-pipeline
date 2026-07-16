"""
collectors/nws_cli_collector.py — CLI Daily Climate Report collector (M2.T4).

fetch latest CLI -> snapshot raw body -> parse high/low -> append row.
Parser built against a real captured Phoenix sample (2026-07-13). Amendments
and later reports append as new rows; a re-fetch of the identical product_id
is skipped. high/low may be None when the report shows MM (missing).

Status: E4 — AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from typing import NamedTuple

import requests

from core import config
from core.climate_day import climate_day
from storage.schema import ensure_raw_nws_cli
from storage.snapshots import SnapshotStore

PARSER_VERSION = "1"
API_BASE = "https://api.weather.gov"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_int_after_label(line: str):
    """OBSERVED VALUE = first token after MAXIMUM/MINIMUM. None if MM/absent."""
    m = re.match(r"\s*(MAXIMUM|MINIMUM)\s+(\S+)", line)
    if not m:
        return None
    token = m.group(2)
    if token.upper() == "MM":
        return None
    return int(token) if re.fullmatch(r"-?\d+", token) else None


def parse_high_low(product_text: str):
    """Return (high_f, low_f) from the first MAXIMUM/MINIMUM lines."""
    high = low = None
    for line in product_text.splitlines():
        s = line.strip()
        if s.startswith("MAXIMUM") and high is None:
            high = _first_int_after_label(line)
        elif s.startswith("MINIMUM") and low is None:
            low = _first_int_after_label(line)
    return high, low


def parse_report_kind(product_text: str) -> str:
    """Classify: 'preliminary' if VALID ... AS OF appears, else 'summary'."""
    upper = product_text.upper()
    if "VALID TODAY AS OF" in upper or "VALID AS OF" in upper:
        return "preliminary"
    return "summary"


def fetch_latest_cli(location_id: str) -> dict:
    url = f"{API_BASE}/products/types/CLI/locations/{location_id}/latest"
    resp = requests.get(url, headers={"User-Agent": config.nws_user_agent()},
                        timeout=30)
    resp.raise_for_status()
    return resp.json()


def already_have_product(conn, product_id) -> bool:
    if not product_id:
        return False
    return conn.execute(
        "SELECT 1 FROM raw_nws_cli WHERE product_id = ? LIMIT 1", (product_id,)
    ).fetchone() is not None


def collect_city(city: str, db_path: str) -> str:
    station = config.station(city)
    location_id = config.cli_location_id(city)
    product = fetch_latest_cli(location_id)
    raw_text = product.get("productText", "")
    product_id = product.get("id") or product.get("@id", "")
    issuance = product.get("issuanceTime")
    raw_bytes = raw_text.encode("utf-8")

    store = SnapshotStore(db_path)
    conn = sqlite3.connect(db_path)
    try:
        ensure_raw_nws_cli(conn)
        if already_have_product(conn, product_id):
            return f"{city}: product {product_id} already stored - skipped"

        digest = store.snapshot(
            raw_bytes,
            url=f"{API_BASE}/products/types/CLI/locations/{location_id}/latest",
            component="nws_cli", fetch_time_utc=issuance)

        ts = (datetime.fromisoformat(issuance.replace("Z", "+00:00"))
              if issuance else datetime.now(timezone.utc))
        cday = climate_day(city, ts).isoformat()
        high, low = parse_high_low(raw_text)
        kind = parse_report_kind(raw_text)

        with conn:
            conn.execute(
                """
                INSERT INTO raw_nws_cli
                    (station_id, location_id, product_id, issuance_time_utc,
                     climate_day, report_kind, high_temp_f, low_temp_f,
                     snapshot_hash, ingest_time_utc, parser_version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (station, location_id, product_id, issuance, cday, kind,
                 high, low, digest, _utc_now_iso(), PARSER_VERSION))
        return (f"{city}: stored {product_id} | climate_day {cday} | "
                f"{kind} | high={high} low={low} | snap {digest[:12]}...")
    finally:
        conn.close()


class CityResult(NamedTuple):
    """Outcome of one city's collection attempt.

    ok=True covers BOTH outcomes collect_city returns normally: a row was
    stored, OR the product was already stored and was skipped. A duplicate
    skip is a success -- the data is present. Only an exception is a failure.
    """
    city: str
    ok: bool
    message: str


def collect_all(db_path: str) -> list[CityResult]:
    """Attempt every configured city; isolate failures; return one result each.

    Each city is attempted independently. A failure in one city -- network,
    parse, or ConfigError -- does NOT prevent the remaining cities from being
    attempted (Architect ruling 2026-07-15: maximize non-backfillable accrual,
    report truthfully). Never raises; the caller reads the results.
    """
    results: list[CityResult] = []
    for city in config.cities():
        try:
            results.append(CityResult(city, True, collect_city(city, db_path)))
        except Exception as exc:
            results.append(CityResult(
                city, False, f"{city}: FAILED - {type(exc).__name__}: {exc}"))
    return results


def exit_code_for(results) -> int:
    """0 only if every city succeeded; 1 if any failed.

    Task Scheduler reads this. A false success here would hide missed
    collection, so any failure must propagate.
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
    sys.exit(exit_code_for(results))