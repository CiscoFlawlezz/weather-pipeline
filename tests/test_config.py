"""
tests/test_config.py — acceptance tests for core/config.py.

The load-bearing test here is that a MISSING key RAISES rather than
silently returning None or a default. That property is the whole reason
core/config.py exists: a wrong or absent station mapping must fail loudly,
never proceed quietly.
"""

import pytest

from core import config


# --- Happy path: real keys resolve to real values -------------------------

def test_cities_lists_all_five():
    result = config.cities()
    assert set(result) == {"phoenix", "nyc", "chicago", "miami", "austin"}


def test_series_returns_ticker():
    assert config.series("phoenix") == "KXHIGHTPHX"


def test_stations_maps_every_city():
    result = config.stations()
    assert result["phoenix"] == "KPHX"
    assert result["austin"] == "KAUS"
    assert len(result) == 5


def test_station_single_city():
    assert config.station("miami") == "KMIA"


def test_nws_user_agent_present():
    assert "@" in config.nws_user_agent()


def test_base_urls_present():
    assert config.nws_base_url().startswith("https://")
    assert config.kalshi_base_url().startswith("https://")


def test_cli_cadence_has_sweeps():
    # Assert the invariants that matter, not a magic count: the cadence
    # declares a positive number of sweeps, and that number equals the
    # number of *_local sweep times actually configured. This catches
    # config drifting out of sync with itself (e.g. bumping the count but
    # forgetting to add the matching time) without breaking every time the
    # deployed schedule legitimately changes.
    cadence = config.cli_cadence()
    sweeps = cadence["sweeps_per_day"]
    assert isinstance(sweeps, int) and sweeps >= 1
    sweep_times = [k for k in cadence if k.endswith("_local")]
    assert len(sweep_times) == sweeps, (
        f"sweeps_per_day={sweeps} but {len(sweep_times)} *_local times "
        f"configured: {sorted(sweep_times)}"
    )


# --- The load-bearing tests: missing keys RAISE ---------------------------

def test_series_missing_city_raises():
    with pytest.raises(config.ConfigError):
        config.series("atlantis")


def test_station_missing_city_raises():
    with pytest.raises(config.ConfigError):
        config.station("atlantis")


def test_cutoffs_raises_not_configured():
    # cutoffs are deliberately unconfigured; calling must raise, not return {}.
    with pytest.raises(config.ConfigError):
        config.cutoffs()


def test_configerror_is_a_keyerror():
    # Callers may catch either name; the property is contractual.
    assert issubclass(config.ConfigError, KeyError)