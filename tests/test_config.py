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
    cadence = config.cli_cadence()
    assert cadence["sweeps_per_day"] == 2


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