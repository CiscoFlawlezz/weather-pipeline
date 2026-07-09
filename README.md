# Weather Pipeline — Milestone 1a

Proof-of-integration skeleton for the Prediction Market Research Lab
weather data pipeline. **Scope:** verify that Kalshi market data and
NWS forecast/observation data are both reachable and parseable.
No storage, no scheduling yet — those are Milestone 1b.

## Setup (Windows)

```powershell
# 1. From the folder containing this README:
py -m venv venv
.\venv\Scripts\activate

# 2. Install the two dependencies:
pip install -r requirements.txt

# 3. REQUIRED: open config.yaml and set your real email in
#    nws.user_agent (the script refuses to run with the placeholder —
#    NWS asks for a contact address in the User-Agent).

# 4. Run the integration test:
python test_connections.py
```

If PowerShell blocks the venv activation script, run once:
`Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

## What the test proves

1. Kalshi API reachable (exchange status)
2. Which candidate weather series tickers in `config.yaml` actually
   exist (empirical verification — only Phoenix was pre-verified)
3. Live open markets + real candlestick data for one settled market
4. NWS points → hourly forecast chain, plus a live station observation

## Known limitations (deliberate, documented)

- **No authentication:** market-data reads are public per Kalshi's
  docs. Your API key is intentionally unused until a much later
  milestone — code that never holds a key can never leak one.
- **Station IDs unverified:** every `station_id` in config.yaml must
  be checked against the official rules page of the corresponding
  Kalshi market before Milestone 1b begins. A wrong station silently
  corrupts everything downstream. Flip `verified: true` per city as
  you confirm each one.
- **This code has not run against the live APIs yet.** It was written
  in a sandbox without network access to kalshi.com/weather.gov, so
  the first run on your machine IS the integration test. If anything
  errors, paste the exact output back for diagnosis.
- **Historical cutoff:** markets settled before Kalshi's cutoff move
  to separate `/historical/` endpoints. Deep backfill is a future
  module; daily sweeps of recent markets use the live endpoints here.

## Project structure

```
weather-pipeline/
├── config.yaml            # cities, tickers, stations (verification flags)
├── requirements.txt
├── test_connections.py    # Milestone 1a: run this
├── collectors/
│   ├── kalshi_client.py   # all Kalshi parsing isolated here
│   └── nws_client.py      # all NWS logic isolated here
└── storage/
    └── schema.sql         # append-only schema, used starting in 1b
```

## Milestone 1b (next, after 1a passes)

- `storage/db.py` — SQLite writer implementing schema.sql
- CLI climate report ingestion (the actual settlement ground truth)
- `run_collection.py` orchestrator with the `collection_runs` audit log
- Windows Task Scheduler jobs (multiple daily NWS snapshots +
  one nightly Kalshi sweep)
- Success criterion: 14 consecutive days, zero silent failures

