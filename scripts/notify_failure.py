"""
scripts/notify_failure.py -- ntfy.sh POST on a wrapper's real failure branch.

WHY THIS EXISTS
----------------
A silent stoppage is invisible until someone looks -- that is exactly how
~22h of Kalshi collection loss during the 2026-07-22 DNS outage went
unnoticed for two days. This script turns a wrapper's already-truthful
non-zero exit into an immediate push notification.

CONTRACT WITH THE CALLING WRAPPER
----------------------------------
This script is advisory, never authoritative. The wrapper calls it AFTER
it has already decided it failed and AFTER it has already saved the exit
code it intends to return. This script's own outcome -- success, a caught
failure, or even a hard crash (bad import, uncaught exception) -- must
never change what the wrapper returns: the wrapper's `exit /b !RC!` line
runs unconditionally on the line after this call, using the RC value it
saved BEFORE invoking this script, never this script's own errorlevel.
That architectural fact (not anything in this file) is what makes the
wrapper's exit code safe even if this file crashes outright.

What this file still owes the wrapper is to never go dark. A silent
notifier is the exact failure class this task exists to kill, so every
path below prints a visible line -- never a bare, silent return:
  1. secrets.yaml missing / notify not configured -> SKIPPED line, return.
  2. the ntfy POST itself fails (network, timeout, non-2xx) -> SKIPPED
     line with the reason, return.
  3. anything else unexpected -> still print a line before giving up.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# The wrapper invokes this file by absolute path (never `python -m`, and
# never guaranteed to run from the repo root -- see the cd-failure branch,
# which calls this BEFORE cd succeeds). When Python runs a script by path,
# it puts the script's own directory on sys.path[0], not the repo root, so
# `import core` fails unless the repo root is added explicitly here first.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from core.config import ConfigError, notify_config

# Kept short deliberately: the Kalshi wrapper fires every 5 minutes, and
# failures cluster during network outages -- exactly when a long timeout
# would hurt most. MultipleInstancesPolicy=IgnoreNew on the Kalshi task
# means this can never overlap the next sweep either way (confirmed against
# scheduler/WeatherPipeline_Kalshi.xml); this timeout only bounds how long
# a single wrapper invocation's own exit is delayed.
TIMEOUT_SECONDS = 5


def send(wrapper: str, rc: str) -> None:
    try:
        cfg = notify_config()
    except ConfigError as exc:
        print(f"[notify_failure] SKIPPED: notifications not configured ({exc})")
        return

    url = f"{cfg['server'].rstrip('/')}/{cfg['topic']}"
    message = f"{wrapper} failed (exit {rc})"

    try:
        resp = requests.post(
            url, data=message.encode("utf-8"), timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        print(f"[notify_failure] SKIPPED: ntfy POST failed: {exc}")
        return

    if resp.status_code >= 300:
        print(
            f"[notify_failure] SKIPPED: ntfy returned HTTP {resp.status_code}: "
            f"{resp.text[:200]}"
        )
        return

    print(
        f"[notify_failure] SENT: {wrapper} failure (exit {rc}) -> {url} "
        f"(HTTP {resp.status_code})"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wrapper", required=True)
    parser.add_argument("--rc", required=True)
    args = parser.parse_args()

    try:
        send(args.wrapper, args.rc)
    except Exception as exc:  # last-resort: this must never propagate
        print(f"[notify_failure] SKIPPED: unexpected error: {exc}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
