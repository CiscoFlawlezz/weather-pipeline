"""
Milestone 1a proof-of-integration script.

Run this ONCE on your machine:  python test_connections.py

It performs, in order:
  1. Kalshi connectivity check (exchange status — cheapest call)
  2. Series verification: tests every candidate series ticker in
     config.yaml against the live API and reports EXISTS / NOT FOUND.
     (config tickers are candidates, not assumptions — this is the
     empirical check that replaces guessing.)
  3. For the first verified series: lists open markets, then pulls
     hourly candlesticks for one recently settled market.
  4. NWS connectivity: points lookup + hourly forecast for the first
     city, and the latest observation from its configured station.

Success criterion for Milestone 1a: all four sections print OK, and
the candlestick section shows real prices. Nothing is stored yet —
storage and scheduling are Milestone 1b, and building them before
proving the integrations work would be building on sand.
"""

import sys
from pathlib import Path

import yaml

from collectors.kalshi_client import (
    KalshiClient,
    KalshiError,
    summarize_candlestick,
    yesterday_window,
)
from collectors.nws_client import NWSClient, NWSError


def load_config() -> dict:
    cfg_path = Path(__file__).parent / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def main() -> int:
    cfg = load_config()
    failures = 0

    # ------------------------------------------------------------
    section("1. Kalshi connectivity")
    kalshi = KalshiClient(base_url=cfg["kalshi"]["base_url"])
    try:
        status = kalshi.get_exchange_status()
        print(f"OK — exchange status: {status}")
    except KalshiError as e:
        print(f"FAILED: {e}")
        return 1  # nothing else Kalshi-side can work

    # ------------------------------------------------------------
    section("2. Verifying candidate series tickers from config.yaml")
    verified_series = []
    for city, info in cfg["cities"].items():
        ticker = info["kalshi_series"]
        try:
            kalshi.get_series(ticker)
            print(f"  {city:10s} {ticker:15s} EXISTS")
            verified_series.append((city, ticker))
        except KalshiError:
            print(f"  {city:10s} {ticker:15s} NOT FOUND — fix config.yaml")
            failures += 1

    if not verified_series:
        print("No candidate series verified; cannot continue Kalshi tests.")
        return 1

    # ------------------------------------------------------------
    city, series = verified_series[0]
    section(f"3. Markets + candlesticks for {series} ({city})")

    try:
        open_mkts = kalshi.get_markets(series_ticker=series, status="open",
                                       limit=10).get("markets", [])
        print(f"Open markets: {len(open_mkts)}")
        for m in open_mkts[:5]:
            print(f"  {m.get('ticker')}  closes {m.get('close_time')}")

        settled = kalshi.get_markets(series_ticker=series, status="settled",
                                     limit=5).get("markets", [])
        if not settled:
            print("No recently settled markets returned (may be past the "
                  "historical cutoff — acceptable for 1a; backfill module "
                  "handles deep history later).")
        else:
            target = settled[0]["ticker"]
            start_ts, end_ts = yesterday_window()
            candles = kalshi.get_candlesticks(
                series, target, start_ts, end_ts,
                period_interval=cfg["kalshi"]["candlestick_interval"],
            ).get("candlesticks", [])
            print(f"Candlesticks for {target} (last 24h): {len(candles)}")
            for c in candles[:3]:
                print(f"  {summarize_candlestick(c)}")
            if not candles:
                print("  (Empty window is possible if the market settled "
                      ">24h ago — rerun tomorrow against a fresher market "
                      "before declaring failure.)")
    except KalshiError as e:
        print(f"FAILED: {e}")
        failures += 1

    # ------------------------------------------------------------
    section("4. NWS forecast + observation")
    try:
        nws = NWSClient(user_agent=cfg["nws"]["user_agent"],
                        base_url=cfg["nws"]["base_url"])
    except ValueError as e:
        print(f"CONFIG ERROR: {e}")
        return 1

    first_city = next(iter(cfg["cities"]))
    info = cfg["cities"][first_city]
    try:
        fc = nws.get_hourly_forecast(info["lat"], info["lon"])
        periods = fc["properties"]["periods"][:3]
        print(f"Hourly forecast for {first_city} "
              f"(issued {fc['properties'].get('updateTime')}):")
        for p in periods:
            print(f"  {p['startTime']}  {p['temperature']}°"
                  f"{p['temperatureUnit']}  {p['shortForecast']}")

        obs = nws.get_latest_observation(info["station_id"])
        t = obs["properties"].get("temperature", {})
        print(f"Latest observation at {info['station_id']}: "
              f"{t.get('value')} {t.get('unitCode')} "
              f"at {obs['properties'].get('timestamp')}")
    except NWSError as e:
        print(f"FAILED: {e}")
        failures += 1

    # ------------------------------------------------------------
    section("RESULT")
    if failures == 0:
        print("All integration checks passed. Milestone 1a complete.")
        print("Next: verify station IDs against each market's rules page, "
              "flip 'verified: true' in config.yaml, then build 1b "
              "(storage + scheduled collection).")
    else:
        print(f"{failures} check(s) failed — see output above. Fix config "
              "or report the exact error text back for diagnosis.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
