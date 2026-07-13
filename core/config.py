"""
core/config.py — single source of truth for pipeline configuration.

Every collector, storage module, and script reads settings through the
accessors here. No module hardcodes a ticker, station ID, or cadence
(D4 convention). Missing keys raise loudly — they are never silently
defaulted, because a silent default is how a wrong station mapping or a
missing cadence corrupts data without anyone noticing.

Governs: RL-ENG-001 (config unification, D4).
Status: E4 — AI-drafted, pending Architect ratification (Invariant 3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


# --- Locate and load the config file --------------------------------------

# config.yaml lives at the repo root, one level above this file's package.
# core/config.py -> parent is core/ -> parent is the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config.yaml"


class ConfigError(KeyError):
    """Raised when a required configuration key is missing or unusable.

    Subclasses KeyError so callers can catch either, but carries a
    pipeline-specific name so failures are unmistakable in a traceback.
    """


def _load() -> dict[str, Any]:
    """Read and parse config.yaml. Raises ConfigError if it is missing."""
    if not _CONFIG_PATH.exists():
        raise ConfigError(
            f"config.yaml not found at expected path: {_CONFIG_PATH}"
        )
    with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(
            f"config.yaml did not parse to a mapping (got {type(data).__name__})"
        )
    return data


def _require(mapping: dict[str, Any], key: str, context: str) -> Any:
    """Return mapping[key] or raise ConfigError naming what was missing."""
    if key not in mapping:
        raise ConfigError(f"missing required key '{key}' in {context}")
    return mapping[key]


# --- Public accessors ------------------------------------------------------

def cities() -> list[str]:
    """Return the list of configured city names, e.g. ['phoenix', ...]."""
    data = _load()
    block = _require(data, "cities", "config root")
    return list(block.keys())


def series(city: str) -> str:
    """Return the Kalshi series ticker for a city.

    Raises ConfigError if the city or its kalshi_series key is absent.
    """
    data = _load()
    cities_block = _require(data, "cities", "config root")
    city_block = _require(cities_block, city, "cities")
    return _require(city_block, "kalshi_series", f"cities.{city}")


def stations() -> dict[str, str]:
    """Return {city: station_id} for every configured city.

    Raises ConfigError if any city is missing its station_id.
    """
    data = _load()
    cities_block = _require(data, "cities", "config root")
    result: dict[str, str] = {}
    for city, city_block in cities_block.items():
        result[city] = _require(city_block, "station_id", f"cities.{city}")
    return result


def station(city: str) -> str:
    """Return the station_id for one city. Raises ConfigError if absent."""
    data = _load()
    cities_block = _require(data, "cities", "config root")
    city_block = _require(cities_block, city, "cities")
    return _require(city_block, "station_id", f"cities.{city}")


def nws_user_agent() -> str:
    """Return the NWS User-Agent string. Raises ConfigError if absent."""
    data = _load()
    nws_block = _require(data, "nws", "config root")
    return _require(nws_block, "user_agent", "nws")


def nws_base_url() -> str:
    """Return the NWS API base URL. Raises ConfigError if absent."""
    data = _load()
    nws_block = _require(data, "nws", "config root")
    return _require(nws_block, "base_url", "nws")


def kalshi_base_url() -> str:
    """Return the Kalshi API base URL. Raises ConfigError if absent."""
    data = _load()
    kalshi_block = _require(data, "kalshi", "config root")
    return _require(kalshi_block, "base_url", "kalshi")


def cli_cadence() -> dict[str, Any]:
    """Return the nws_cli collection cadence block.

    Raises ConfigError if collection.nws_cli is absent.
    """
    data = _load()
    collection_block = _require(data, "collection", "config root")
    return _require(collection_block, "nws_cli", "collection")


def cutoffs() -> dict[str, Any]:
    """Return per-city forecast cutoff times.

    Not yet configured: cutoffs are a model-rung concept (M5), not needed
    by the CLI collector. Raising here — rather than returning {} — keeps
    any premature caller loud instead of silently proceeding without them.
    """
    raise ConfigError(
        "cutoffs are not yet configured; they enter at the model rung (M5). "
        "Add a 'cutoffs' section to config.yaml before calling this."
    )