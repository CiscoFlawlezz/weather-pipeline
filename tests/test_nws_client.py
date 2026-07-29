"""tests/test_nws_client.py — NWSClient raw-fetch methods (F2 prerequisite).

Proves the reason _get_raw exists: json.dumps(resp.json()) is NOT the body
NWS sent. A parsed-then-re-serialized body can differ from the original
bytes in separator whitespace, ensure_ascii escaping of non-ASCII
characters, and float repr -- producing a DIFFERENT SHA-256, which would be
a false provenance claim in the snapshot store (Invariant 3). The
non-ASCII assertion is the load-bearing one: a "fix" that normalizes
separators (e.g. json.dumps(..., separators=(',', ':'))) would defeat a
whitespace-only test, but cannot defeat the ensure_ascii divergence.

Also proves get_points_raw / get_hourly_forecast_raw's actual wire
behavior (call ordering, which URL each fetch uses, coordinate rounding
reaching the URL) and _get_raw's three documented failure modes,
including the one that DIVERGES from _get (malformed JSON).

No network, no fixture: session.get is mocked directly.

Status: E4 -- AI-drafted, pending Architect ratification (Invariant 3).
"""
from __future__ import annotations

import hashlib
import json
from unittest.mock import MagicMock

import pytest
import requests

from collectors.nws_client import HourlyForecastRaw, NWSClient, NWSError, PointsRaw


def _make_client() -> NWSClient:
    return NWSClient(user_agent="test-agent (test@example.org)")


def _mock_response(status_code=200, content=b"{}", headers=None, json_value=None,
                    json_side_effect=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.headers = headers if headers is not None else {}
    resp.text = content.decode("utf-8", errors="replace")
    if json_side_effect is not None:
        resp.json.side_effect = json_side_effect
    elif json_value is not None:
        resp.json.return_value = json_value
    else:
        # Best-effort default: parse content if it happens to be valid
        # JSON; if a test deliberately passed a malformed body and did
        # not supply json_value/json_side_effect, surface that as the
        # same ValueError resp.json() would raise, instead of crashing
        # this helper during mock construction.
        try:
            resp.json.return_value = json.loads(content)
        except ValueError:
            resp.json.side_effect = ValueError("Expecting value")
    return resp


# ----------------------------------------------------------------------
# _get_raw: the false-provenance test the method exists to prevent
# ----------------------------------------------------------------------

def test_get_raw_returns_byte_identical_body_not_a_reserialization(monkeypatch):
    """raw_bytes must be exactly what the server sent, not json.dumps(parsed).

    Non-canonical whitespace AND a non-ASCII value are both present. The
    non-ASCII value ("c": "é") is the load-bearing part of this test:
    json.dumps's default ensure_ascii=True escapes it to "\\u00e9", which
    differs from the raw UTF-8 bytes regardless of separator choice --
    so this assertion survives a "fix" that merely normalizes whitespace
    (e.g. separators=(',', ':')), unlike a whitespace-only comparison.
    """
    non_canonical_body = '{"b": 1,\n  "a": 2,\n  "c": "é"}'.encode("utf-8")

    mock_resp = _mock_response(content=non_canonical_body)
    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    parsed, raw_bytes, date_header = client._get_raw("https://api.weather.gov/fake")

    assert raw_bytes == non_canonical_body, (
        "raw_bytes must be byte-identical to what the server sent")

    reserialized = json.dumps(parsed).encode()
    assert hashlib.sha256(raw_bytes).hexdigest() != hashlib.sha256(reserialized).hexdigest(), (
        "a re-serialization of the parsed JSON hashed the same as the raw "
        "bytes -- this test no longer proves raw_bytes is load-bearing")


def test_get_raw_date_header_is_none_when_absent(monkeypatch):
    """Never assume NWS sends a Date header -- absence must surface as None."""
    mock_resp = _mock_response(content=b'{"ok": true}', headers={})
    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    _, _, date_header = client._get_raw("https://api.weather.gov/fake")

    assert date_header is None


def test_get_raw_date_header_is_returned_when_present(monkeypatch):
    mock_resp = _mock_response(
        content=b'{"ok": true}',
        headers={"Date": "Wed, 29 Jul 2026 18:00:00 GMT"},
    )
    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    _, _, date_header = client._get_raw("https://api.weather.gov/fake")

    assert date_header == "Wed, 29 Jul 2026 18:00:00 GMT"


# ----------------------------------------------------------------------
# _get_raw: the three documented failure modes
# ----------------------------------------------------------------------

def test_get_raw_raises_nwserror_on_non_200_status(monkeypatch):
    mock_resp = _mock_response(status_code=404, content=b"not found")
    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    with pytest.raises(NWSError):
        client._get_raw("https://api.weather.gov/fake")


def test_get_raw_raises_nwserror_on_request_exception(monkeypatch):
    client = _make_client()

    def raise_network_error(*a, **k):
        raise requests.RequestException("connection refused")

    monkeypatch.setattr(client.session, "get", raise_network_error)

    with pytest.raises(NWSError):
        client._get_raw("https://api.weather.gov/fake")


def test_get_raw_raises_nwserror_on_malformed_json(monkeypatch):
    """The case that DIVERGES from _get (see _get_raw's docstring). Pinned."""
    mock_resp = _mock_response(content=b"not json{")
    mock_resp.json.side_effect = ValueError("Expecting value")
    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    with pytest.raises(NWSError):
        client._get_raw("https://api.weather.gov/fake")


# ----------------------------------------------------------------------
# get_points_raw: coordinate rounding is now semantic (Amendment 2)
# ----------------------------------------------------------------------

def test_get_points_raw_returns_points_raw_namedtuple(monkeypatch):
    body = json.dumps({"properties": {"forecastHourly": "https://x"}}).encode()
    mock_resp = _mock_response(content=body)
    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    result = client.get_points_raw(40.7789, -73.9692)

    assert isinstance(result, PointsRaw)
    assert result.points_json == json.loads(body)
    assert result.points_bytes == body


def test_get_points_raw_never_uses_the_points_cache(monkeypatch):
    """The entire substance of Amendment 3's docstring, as an assertion.

    get_points_raw() deliberately bypasses get_points()'s in-memory
    _points_cache -- reusing it would risk snapshotting cached bytes
    stamped with a fetch time those bytes never actually had (a false
    provenance record). A docstring saying so does not fail if someone
    later "optimizes" this method to reuse the cache; only a call-count
    assertion does. Two calls, identical coordinates, two HTTP fetches.
    """
    mock_resp = _mock_response(content=b'{"properties": {}}')
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return mock_resp

    client = _make_client()
    monkeypatch.setattr(client.session, "get", fake_get)

    client.get_points_raw(40.7789, -73.9692)
    client.get_points_raw(40.7789, -73.9692)

    assert len(calls) == 2, (
        f"get_points_raw must never serve from the cache -- identical "
        f"coordinates called twice must produce two HTTP fetches, got "
        f"{len(calls)} call(s)")


def test_get_points_raw_phoenix_trailing_zero_lost_at_yaml_parse(monkeypatch):
    """Pins the real config.yaml phoenix coordinate case, not a coordinate
    that happens to round to four non-zero decimals.

    (a) 33.4484, -112.0740 are phoenix's real production coordinates from
        config.yaml (cities.phoenix.lat / .lon).
    (b) config.yaml writes lon as -112.0740 (four decimal places in the
        text), but YAML parses that to the float -112.074 -- the trailing
        zero is gone before round(lon, 4) or any pipeline code ever sees
        it. This is a YAML-parse artifact, not a round() bug and not
        something to "fix" in config.yaml (the float is the same number).
    (c) Whether NWS's /points endpoint cares about variable decimal
        precision (four decimals for nine of ten coordinates, three for
        this one) is UNVERIFIED pending the live capture in step 3/4.
        Per the Architect's calibration: 4 vs 3 decimals of longitude is
        ~11m vs ~110m, both well inside one ~2.5km NWS grid cell -- very
        likely harmless in substance. This test only pins what the code
        CURRENTLY produces on the wire, so step 4 has something concrete
        to confirm or contradict against a real response.
    """
    mock_resp = _mock_response(content=b'{"properties": {}}')
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return mock_resp

    client = _make_client()
    monkeypatch.setattr(client.session, "get", fake_get)

    client.get_points_raw(33.4484, -112.0740)  # phoenix, config.yaml values

    assert len(calls) == 1
    assert calls[0] == "https://api.weather.gov/points/33.4484,-112.074", (
        f"expected the trailing-zero-collapsed wire URL, got {calls[0]}")


def test_get_points_raw_rounds_coordinates_to_four_decimals_on_the_wire(monkeypatch):
    """The rounding determines which URL is fetched -- pin it on the wire,
    not just on the return value. 8 decimal places in, 4 decimal places
    must reach session.get."""
    mock_resp = _mock_response(content=b'{"properties": {}}')
    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return mock_resp

    client = _make_client()
    monkeypatch.setattr(client.session, "get", fake_get)

    client.get_points_raw(40.778912345, -73.969234567)

    assert len(calls) == 1
    assert calls[0] == "https://api.weather.gov/points/40.7789,-73.9692", (
        f"expected coordinates rounded to 4 decimals on the wire, got {calls[0]}")


# ----------------------------------------------------------------------
# get_hourly_forecast_raw: the two-step chain, and its six fields
# ----------------------------------------------------------------------

def test_get_hourly_forecast_raw_returns_six_populated_fields(monkeypatch):
    forecast_url = "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly"
    points_body = json.dumps({"properties": {"forecastHourly": forecast_url}}).encode()
    forecast_body = json.dumps(
        {"properties": {"periods": [{"number": 1, "temperature": 88}]}}
    ).encode()

    points_resp = _mock_response(
        content=points_body, headers={"Date": "Wed, 29 Jul 2026 18:00:00 GMT"})
    forecast_resp = _mock_response(
        content=forecast_body, headers={"Date": "Wed, 29 Jul 2026 18:05:00 GMT"})

    def fake_get(url, params=None, timeout=None):
        return forecast_resp if url == forecast_url else points_resp

    client = _make_client()
    monkeypatch.setattr(client.session, "get", fake_get)

    result = client.get_hourly_forecast_raw(40.7789, -73.9692)

    assert isinstance(result, HourlyForecastRaw)
    assert result.points_json == json.loads(points_body)
    assert result.points_bytes == points_body
    assert result.points_date == "Wed, 29 Jul 2026 18:00:00 GMT"
    assert result.forecast_json == json.loads(forecast_body)
    assert result.forecast_bytes == forecast_body
    assert result.forecast_date == "Wed, 29 Jul 2026 18:05:00 GMT"


def test_get_hourly_forecast_raw_fetches_points_then_forecast_url_from_points_body(monkeypatch):
    """/points is fetched first; the SECOND fetch uses the forecastHourly
    URL taken from the points body, not a constructed grid URL."""
    forecast_url = "https://api.weather.gov/gridpoints/OKX/33,37/forecast/hourly"
    points_body = json.dumps({"properties": {"forecastHourly": forecast_url}}).encode()
    forecast_body = json.dumps({"properties": {"periods": []}}).encode()

    points_resp = _mock_response(content=points_body)
    forecast_resp = _mock_response(content=forecast_body)

    calls = []

    def fake_get(url, params=None, timeout=None):
        calls.append(url)
        return forecast_resp if url == forecast_url else points_resp

    client = _make_client()
    monkeypatch.setattr(client.session, "get", fake_get)

    client.get_hourly_forecast_raw(40.7789, -73.9692)

    assert len(calls) == 2, f"expected exactly 2 HTTP calls, got {len(calls)}"
    assert calls[0] == "https://api.weather.gov/points/40.7789,-73.9692", (
        f"first call must be the /points lookup, got {calls[0]}")
    assert calls[1] == forecast_url, (
        "second call must use the forecastHourly URL taken from the "
        f"points body, not a constructed grid URL; got {calls[1]}")


def test_get_hourly_forecast_raw_raises_keyerror_when_forecasthourly_missing(monkeypatch):
    """A points body missing properties.forecastHourly raises bare
    KeyError, NOT NWSError -- pinning the behavior documented on
    get_hourly_forecast_raw (unchanged from the existing
    get_hourly_forecast(), deliberately not wrapped)."""
    points_body = json.dumps({"properties": {}}).encode()  # no forecastHourly
    mock_resp = _mock_response(content=points_body)

    client = _make_client()
    monkeypatch.setattr(client.session, "get", lambda *a, **k: mock_resp)

    with pytest.raises(KeyError):
        client.get_hourly_forecast_raw(40.7789, -73.9692)
