"""tests/test_collect_all.py — multi-city collection loop (M2 expansion).

Proves the six required behaviors of collect_all():
  1. Phoenix still succeeds.
  2. All five configured cities are attempted.
  3. Duplicate detection still works (skip is a SUCCESS, not a failure).
  4. One city failing does not stop the others.
  5. Exit code is non-zero if any city failed.
  6. Exit code is zero only when all cities succeeded.

collect_city() is NOT modified by this task. These tests mock it, so no
network is touched and Phoenix's proven path is never exercised here --
it is covered by its own tests and by live verification.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from collectors import nws_cli_collector as m
from core import config

REPO_ROOT = Path(__file__).resolve().parents[1]


# ----------------------------------------------------------------
# Requirement 2: every configured city is attempted, from config
# ----------------------------------------------------------------

def test_collect_all_attempts_every_configured_city(monkeypatch):
    """The city list comes from config, not a hardcoded literal."""
    attempted = []

    def fake_collect_city(city, db_path):
        attempted.append(city)
        return f"{city}: stored FAKE-{city}"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")

    assert attempted == list(config.cities()), (
        f"collect_all attempted {attempted}, config declares "
        f"{list(config.cities())}")
    assert len(results) == 5, f"expected 5 results, got {len(results)}"


def test_collect_all_includes_all_five_named_cities(monkeypatch):
    """Explicit: phoenix, nyc, chicago, miami, austin are all attempted."""
    attempted = []

    def fake_collect_city(city, db_path):
        attempted.append(city)
        return f"{city}: stored FAKE-{city}"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    m.collect_all("unused.db")

    for expected in ("phoenix", "nyc", "chicago", "miami", "austin"):
        assert expected in attempted, f"{expected} was never attempted"


# ----------------------------------------------------------------
# Requirement 1: Phoenix still succeeds
# ----------------------------------------------------------------

def test_phoenix_still_succeeds(monkeypatch):
    def fake_collect_city(city, db_path):
        return f"{city}: stored FAKE-{city}"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")

    phoenix = [r for r in results if r.city == "phoenix"]
    assert len(phoenix) == 1, "phoenix missing from results"
    assert phoenix[0].ok is True, f"phoenix not ok: {phoenix[0]}"


def test_collect_all_passes_db_path_through(monkeypatch):
    """The db_path argument reaches collect_city unchanged."""
    seen = []

    def fake_collect_city(city, db_path):
        seen.append(db_path)
        return f"{city}: stored"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    m.collect_all("some/specific/path.db")

    assert seen == ["some/specific/path.db"] * 5, f"db_path not passed: {seen}"


# ----------------------------------------------------------------
# Requirement 3: duplicate skip is a SUCCESS, not a failure
# ----------------------------------------------------------------

def test_duplicate_skip_counts_as_success(monkeypatch):
    """collect_city returns a 'skipped' string on duplicate. That is success:
    the row already exists. It must NOT make the run exit non-zero."""
    def fake_collect_city(city, db_path):
        return f"{city}: product FAKE-{city} already stored - skipped"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")

    assert all(r.ok for r in results), (
        "a duplicate skip was treated as a failure: "
        f"{[(r.city, r.ok) for r in results]}")
    assert m.exit_code_for(results) == 0, (
        "duplicate skips must exit 0, not signal failure")


# ----------------------------------------------------------------
# Requirement 4: one city failing does not stop the others
# ----------------------------------------------------------------

def test_chicago_failure_does_not_stop_other_cities(monkeypatch):
    """THE core requirement. Chicago raises; the other four must still run."""
    attempted = []

    def fake_collect_city(city, db_path):
        attempted.append(city)
        if city == "chicago":
            raise RuntimeError("simulated chicago network failure")
        return f"{city}: stored FAKE-{city}"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")

    for other in ("phoenix", "nyc", "miami", "austin"):
        assert other in attempted, (
            f"{other} was never attempted after chicago failed -- "
            "failure isolation is broken")

    by_city = {r.city: r for r in results}
    assert by_city["chicago"].ok is False, "chicago should be marked failed"
    for other in ("phoenix", "nyc", "miami", "austin"):
        assert by_city[other].ok is True, (
            f"{other} should have succeeded despite chicago failing")


def test_failure_message_names_the_exception(monkeypatch):
    """A failed city's message must identify what went wrong."""
    def fake_collect_city(city, db_path):
        if city == "chicago":
            raise RuntimeError("simulated boom")
        return f"{city}: stored"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")
    chicago = [r for r in results if r.city == "chicago"][0]

    assert "RuntimeError" in chicago.message, (
        f"exception type not in message: {chicago.message!r}")
    assert "simulated boom" in chicago.message, (
        f"exception detail not in message: {chicago.message!r}")


def test_config_error_isolates_like_any_other_failure(monkeypatch):
    """Architect ruling 2026-07-15: a malformed config for one city must NOT
    prevent the others from collecting. Record it failed, continue, exit 1."""
    from core.config import ConfigError

    attempted = []

    def fake_collect_city(city, db_path):
        attempted.append(city)
        if city == "chicago":
            raise ConfigError("missing required key 'cli_location_id'")
        return f"{city}: stored"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")

    assert len(attempted) == 5, (
        f"ConfigError halted the run; only attempted {attempted}")
    assert m.exit_code_for(results) == 1


def test_every_city_failing_still_attempts_all_five(monkeypatch):
    attempted = []

    def fake_collect_city(city, db_path):
        attempted.append(city)
        raise RuntimeError(f"{city} boom")

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    results = m.collect_all("unused.db")

    assert len(attempted) == 5, f"only attempted {attempted}"
    assert all(not r.ok for r in results)
    assert m.exit_code_for(results) == 1


# ----------------------------------------------------------------
# Requirements 5 & 6: truthful exit codes
# ----------------------------------------------------------------

def test_exit_code_zero_when_all_succeed(monkeypatch):
    def fake_collect_city(city, db_path):
        return f"{city}: stored"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    assert m.exit_code_for(m.collect_all("unused.db")) == 0


def test_exit_code_nonzero_when_any_city_failed(monkeypatch):
    def fake_collect_city(city, db_path):
        if city == "miami":
            raise RuntimeError("boom")
        return f"{city}: stored"

    monkeypatch.setattr(m, "collect_city", fake_collect_city)
    assert m.exit_code_for(m.collect_all("unused.db")) == 1, (
        "a single city failure must produce a non-zero exit code, or Task "
        "Scheduler records a false success")


# ----------------------------------------------------------------
# The __main__ contract, end to end via subprocess.
# This is the only test that proves the ACTUAL exit code the wrapper sees.
# ----------------------------------------------------------------

def _run_main(tmp_path, injected_source):
    """Run the collector's __main__ in a subprocess with collect_city patched
    via a sitecustomize-style shim. Returns (returncode, stdout+stderr)."""
    shim = tmp_path / "shim.py"
    shim.write_text(injected_source, encoding="utf-8")
    env = dict(os.environ)
    # The shim lives in tmp_path, so the repo root is NOT on sys.path by
    # default -- cwd alone does not put it there. PYTHONPATH does.
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (str(REPO_ROOT) + os.pathsep + existing
                         if existing else str(REPO_ROOT))
    proc = subprocess.run(
        [sys.executable, str(shim), str(tmp_path / "test.db")],
        cwd=str(REPO_ROOT), env=env,
        capture_output=True, text=True, timeout=60)
    return proc.returncode, proc.stdout + proc.stderr


def test_main_exits_zero_when_all_cities_succeed(tmp_path):
    source = '''
import sys, runpy
from collectors import nws_cli_collector as m
m.collect_city = lambda city, db: f"{city}: stored FAKE"
sys.argv = ["nws_cli_collector", sys.argv[1]]
runpy.run_module("collectors.nws_cli_collector", run_name="__main__")
'''
    rc, out = _run_main(tmp_path, source)
    assert rc == 0, f"expected exit 0, got {rc}. Output:\n{out}"
    for city in ("phoenix", "nyc", "chicago", "miami", "austin"):
        assert city in out, f"{city} missing from output:\n{out}"


def test_main_exits_nonzero_when_a_city_fails(tmp_path):
    source = '''
import sys, runpy
from collectors import nws_cli_collector as m

def fake(city, db):
    if city == "chicago":
        raise RuntimeError("simulated chicago failure")
    return f"{city}: stored FAKE"

m.collect_city = fake
sys.argv = ["nws_cli_collector", sys.argv[1]]
runpy.run_module("collectors.nws_cli_collector", run_name="__main__")
'''
    rc, out = _run_main(tmp_path, source)
    assert rc != 0, (
        f"expected non-zero exit, got {rc}. Task Scheduler would record a "
        f"FALSE SUCCESS. Output:\n{out}")
    for city in ("phoenix", "nyc", "miami", "austin"):
        assert city in out, f"{city} missing -- isolation broken:\n{out}"
