"""
core/climate_day.py — the single authority for "which climate day is this?"

A Kalshi temperature market settles on a specific local climate day. That
day's boundary is defined in LOCAL STANDARD TIME and does NOT shift with
Daylight Saving Time. Using local *daylight* time would move the boundary
by an hour twice a year, producing off-by-one-day settlements every spring
and fall — bugs that masquerade as market miscalibration.

This module converts a UTC timestamp to the correct local climate day by
applying each city's FIXED standard-time UTC offset year-round, then taking
the calendar date. No DST is ever applied. No other module in the pipeline
is permitted to compute a settlement day (lint-grade rule).

Standard-time offsets (fixed, year-round):
    phoenix : UTC-7  (Arizona — never observes DST; MST all year)
    nyc     : UTC-5  (Eastern Standard Time)
    chicago : UTC-6  (Central Standard Time)
    miami   : UTC-5  (Eastern Standard Time)
    austin  : UTC-6  (Central Standard Time)

Note on Phoenix: Arizona does not observe DST, so its wall clock already
equals standard time year-round. Applying the fixed -7 offset is therefore
correct in every month — Phoenix is the natural control case that a naive
"local daylight midnight" implementation gets right by accident in summer
and the other four cities get wrong.

Status: E4 — AI-drafted, pending Architect ratification (Invariant 3).
Governs: D1 (one settlement-day function).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


# Fixed standard-time offsets in hours, applied year-round (never DST).
# These intentionally do NOT come from a DST-aware timezone database:
# the whole point is that the boundary is anchored to standard time.
_STANDARD_OFFSET_HOURS: dict[str, int] = {
    "phoenix": -7,
    "nyc": -5,
    "chicago": -6,
    "miami": -5,
    "austin": -6,
}


class ClimateDayError(KeyError):
    """Raised when asked for a city with no registered standard offset."""


def _standard_offset(city: str) -> timedelta:
    if city not in _STANDARD_OFFSET_HOURS:
        raise ClimateDayError(
            f"no standard-time offset registered for city '{city}'. "
            f"Known cities: {sorted(_STANDARD_OFFSET_HOURS)}"
        )
    return timedelta(hours=_STANDARD_OFFSET_HOURS[city])


def climate_day(city: str, utc_ts: datetime) -> date:
    """Return the local climate day (in local STANDARD time) for a UTC moment.

    Args:
        city: one of the registered city keys (phoenix, nyc, chicago,
            miami, austin).
        utc_ts: a timezone-aware datetime. If naive, it is assumed to be
            UTC (and we are explicit about that assumption rather than
            silently guessing a local zone).

    Returns:
        The calendar date of the local climate day, computed by shifting
        the UTC instant by the city's fixed standard-time offset.

    Raises:
        ClimateDayError: if the city is not registered.
    """
    if utc_ts.tzinfo is None:
        utc_ts = utc_ts.replace(tzinfo=timezone.utc)
    else:
        utc_ts = utc_ts.astimezone(timezone.utc)

    local_standard = utc_ts + _standard_offset(city)
    return local_standard.date()