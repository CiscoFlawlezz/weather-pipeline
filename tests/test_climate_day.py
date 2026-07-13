"""
tests/test_climate_day.py — acceptance suite for core/climate_day.py.

Two jobs:
  1. Prove climate_day() assigns the correct LOCAL STANDARD day across
     both DST transitions for all five cities.
  2. Prove the tests BITE: a deliberately naive UTC-midnight implementation
     must FAIL this same suite. If the naive version passed, the tests
     would be testing nothing.

Key idea for the boundary cases: pick a UTC instant that is late evening in
the city's local standard time. Because the city is west of UTC, that
evening-local instant has already rolled past UTC midnight into the *next*
UTC date — so the correct climate day (local) and the UTC date differ. A
naive "just take the UTC date" or "local daylight midnight" implementation
gets these wrong.
"""

from datetime import date, datetime, timezone

import pytest

from core.climate_day import climate_day, ClimateDayError


# --------------------------------------------------------------------------
# Helper: build a UTC-aware datetime tersely.
# --------------------------------------------------------------------------
def utc(y, mo, d, h, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# 1. Basic correctness — an evening-local instant that has crossed UTC midnight
#    For a UTC-5 city (nyc/miami) at 23:00 local standard = 04:00 UTC next day.
#    So 04:00 UTC on Jan 2 is still climate day Jan 1 locally.
# --------------------------------------------------------------------------
def test_evening_local_stays_on_prior_day_nyc():
    # 2026-01-01 23:00 EST == 2026-01-02 04:00 UTC
    assert climate_day("nyc", utc(2026, 1, 2, 4, 0)) == date(2026, 1, 1)


def test_evening_local_stays_on_prior_day_austin():
    # 2026-01-01 23:00 CST == 2026-01-02 05:00 UTC
    assert climate_day("austin", utc(2026, 1, 2, 5, 0)) == date(2026, 1, 1)


def test_midday_local_is_same_day_all_cities():
    # 18:00 UTC is early-mid afternoon local for all five; same calendar day.
    t = utc(2026, 6, 15, 18, 0)
    for city in ("phoenix", "nyc", "chicago", "miami", "austin"):
        assert climate_day(city, t) == date(2026, 6, 15)


# --------------------------------------------------------------------------
# 2. DST transitions — the boundary must NOT move.
#    US DST 2026: spring forward Sun Mar 8; fall back Sun Nov 1.
#    In SUMMER, a naive "local daylight midnight" boundary sits an hour off
#    from the correct standard-time boundary. We probe the hour where they
#    disagree.
#
#    For a UTC-6 standard city (chicago/austin) in summer:
#      standard boundary: day ends at 00:00 CST = 06:00 UTC
#      daylight boundary (wrong): day ends at 00:00 CDT = 05:00 UTC
#    An instant at 05:30 UTC falls AFTER the wrong boundary but BEFORE the
#    correct one, so correct climate day = the earlier date.
# --------------------------------------------------------------------------
def test_summer_boundary_uses_standard_not_daylight_chicago():
    # 2026-07-10 05:30 UTC.
    #   Correct (CST, -6): 2026-07-09 23:30 -> climate day 2026-07-09
    #   Naive (CDT, -5):   2026-07-10 00:30 -> would say 2026-07-10 (WRONG)
    assert climate_day("chicago", utc(2026, 7, 10, 5, 30)) == date(2026, 7, 9)


def test_summer_boundary_uses_standard_not_daylight_nyc():
    # UTC-5 standard city in summer.
    #   Correct (EST, -5): 2026-07-10 04:30 UTC -> 2026-07-09 23:30 -> 07-09
    #   Naive (EDT, -4):   -> 2026-07-10 00:30 -> would say 07-10 (WRONG)
    assert climate_day("nyc", utc(2026, 7, 10, 4, 30)) == date(2026, 7, 9)


def test_spring_forward_day_boundary_austin():
    # Around spring-forward (Mar 8 2026), boundary stays at CST (-6).
    # 2026-03-09 05:30 UTC -> CST 2026-03-08 23:30 -> climate day 03-08
    assert climate_day("austin", utc(2026, 3, 9, 5, 30)) == date(2026, 3, 8)


def test_fall_back_day_boundary_chicago():
    # Around fall-back (Nov 1 2026), boundary stays at CST (-6).
    # 2026-11-02 05:30 UTC -> CST 2026-11-01 23:30 -> climate day 11-01
    assert climate_day("chicago", utc(2026, 11, 2, 5, 30)) == date(2026, 11, 1)


# --------------------------------------------------------------------------
# 3. Phoenix control — Arizona never observes DST, so summer and winter
#    behave identically. The same UTC instant maps the same way year-round.
# --------------------------------------------------------------------------
def test_phoenix_summer_and_winter_identical_offset():
    # 06:30 UTC = 23:30 MST previous day (-7), in both seasons.
    assert climate_day("phoenix", utc(2026, 1, 10, 6, 30)) == date(2026, 1, 9)
    assert climate_day("phoenix", utc(2026, 7, 10, 6, 30)) == date(2026, 7, 9)


# --------------------------------------------------------------------------
# 4. Naive input handling and errors
# --------------------------------------------------------------------------
def test_naive_datetime_assumed_utc():
    # A naive datetime is treated as UTC, explicitly, not as local.
    naive = datetime(2026, 1, 2, 4, 0)  # no tzinfo
    assert climate_day("nyc", naive) == date(2026, 1, 1)


def test_non_utc_aware_is_converted():
    # Pass an instant expressed in a +02:00 zone; must convert to UTC first.
    from datetime import timedelta
    plus2 = timezone(timedelta(hours=2))
    # 2026-01-02 06:00 +02:00 == 2026-01-02 04:00 UTC == nyc climate day 01-01
    t = datetime(2026, 1, 2, 6, 0, tzinfo=plus2)
    assert climate_day("nyc", t) == date(2026, 1, 1)


def test_unknown_city_raises():
    with pytest.raises(ClimateDayError):
        climate_day("atlantis", utc(2026, 1, 1, 12))


# --------------------------------------------------------------------------
# 5. THE BITE: a naive UTC-midnight implementation must FAIL these cases.
#    We define the naive version here and assert it disagrees with the real
#    one on the boundary instants. If this test ever fails, it means the
#    naive implementation would have passed the suite — i.e. the suite has
#    stopped biting and is no longer protecting anything.
# --------------------------------------------------------------------------
def _naive_utc_date(city, utc_ts):
    """The WRONG implementation: just take the UTC calendar date."""
    if utc_ts.tzinfo is None:
        utc_ts = utc_ts.replace(tzinfo=timezone.utc)
    return utc_ts.astimezone(timezone.utc).date()


def test_naive_implementation_would_be_wrong():
    boundary_cases = [
        ("nyc", utc(2026, 1, 2, 4, 0), date(2026, 1, 1)),
        ("austin", utc(2026, 1, 2, 5, 0), date(2026, 1, 1)),
        ("chicago", utc(2026, 7, 10, 5, 30), date(2026, 7, 9)),
        ("phoenix", utc(2026, 7, 10, 6, 30), date(2026, 7, 9)),
    ]
    for city, t, correct in boundary_cases:
        # The real function is right...
        assert climate_day(city, t) == correct
        # ...and the naive UTC-date version is wrong on the same instant.
        assert _naive_utc_date(city, t) != correct