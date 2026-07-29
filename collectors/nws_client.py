"""
National Weather Service (api.weather.gov) client.

WHY POLLING FREQUENCY MATTERS HERE (the pipeline's core asymmetry):
Kalshi candlesticks can be re-fetched after the fact; the *current*
NWS forecast, once superseded, is not served by this API. A missed
forecast snapshot is treated as unrecoverable until we verify whether
the NCEI/IEM forecast archives can fill gaps (open research task).
So this client is built for frequent snapshotting, and the caller must
stamp every snapshot with collection time.

API MECHANICS (verified against NWS docs):
- Free, no API key. NWS asks for a descriptive User-Agent with contact
  info so they can reach you instead of blocking you.
- Two-step lookup: /points/{lat},{lon} returns the grid metadata and
  the URLs for that grid's forecast products. Grid mappings rarely
  change, so get_points() caches them per city for the process
  lifetime. EXCEPTION: get_points_raw() / get_hourly_forecast_raw()
  (the raw-capture path, added for the forecast collector) do NOT use
  this cache -- every call is a fresh fetch. See get_points_raw()'s
  docstring for why.
"""

from typing import NamedTuple, Optional

import requests

DEFAULT_BASE_URL = "https://api.weather.gov"


class NWSError(Exception):
    """Raised for any non-success NWS API response."""


class HourlyForecastRaw(NamedTuple):
    """Raw materials from the points -> forecastHourly fetch chain.

    A NamedTuple rather than a bare tuple: this is a public client method
    whose return value collector code and tests will unpack, unlike the
    private _fetch_both-style helpers elsewhere in this repo. Field names
    prevent a silent mis-ordering bug at the call site.
    """
    points_json: dict
    points_bytes: bytes
    points_date: Optional[str]
    forecast_json: dict
    forecast_bytes: bytes
    forecast_date: Optional[str]


class PointsRaw(NamedTuple):
    """Raw materials from a /points lookup.

    A NamedTuple for the same reason as HourlyForecastRaw: this is a
    public method whose return value collector code and tests unpack,
    and field names prevent a silent mis-ordering bug at the call site.
    """
    points_json: dict
    points_bytes: bytes
    points_date: Optional[str]


class NWSClient:
    def __init__(
        self,
        user_agent: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 30,
    ):
        if "example.com" in user_agent:
            # Fail loudly rather than send a placeholder contact address.
            raise ValueError(
                "Set a real contact email in config.yaml -> nws.user_agent "
                "(NWS uses it to contact you about traffic problems)."
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/geo+json"}
        )
        # Cache of lat/lon -> points metadata (grid rarely changes).
        self._points_cache: dict[tuple[float, float], dict] = {}

    def _get(self, url: str, params: Optional[dict] = None) -> dict:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NWSError(f"Network error calling {url}: {exc}") from exc
        if resp.status_code != 200:
            raise NWSError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:500]}"
            )
        return resp.json()

    # ------------------------------------------------------------------
    # Raw fetch (bytes + Date header preserved) for the forecast collector
    # ------------------------------------------------------------------
    # Mirrors KalshiClient._get_raw (collectors/kalshi_client.py) so both
    # API clients share one raw-capture idiom. _get() above returns only
    # resp.json(), discarding the exact bytes NWS sent -- re-serializing
    # the parsed dict (json.dumps) would produce different bytes (key
    # order, whitespace) and therefore a different SHA-256, which would
    # be a FALSE provenance claim in the snapshot store (Invariant 3).
    def _get_raw(self, url: str, params: Optional[dict] = None) -> tuple:
        """GET a url; return (parsed_json, raw_bytes, server_date_header).

        server_date_header is the response 'Date' header as a string, or
        None if the server did not send one -- never assume NWS sends
        one. Raises NWSError on a network error or non-200 status,
        matching _get's behavior for those two cases.

        DIVERGES from _get on a malformed JSON body: _get's final line
        (`return resp.json()`) sits OUTSIDE its try/except, so a
        malformed body there propagates as an uncaught
        json.JSONDecodeError, never converted to NWSError. This method
        DOES catch that case and raises NWSError. This is a deliberate
        improvement, not a bug to fix on either side -- but it means the
        two methods are NOT interchangeable for a caller that only
        catches NWSError; a caller wrapping _get would also need to
        catch ValueError to get equivalent coverage.
        """
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except requests.RequestException as exc:
            raise NWSError(f"Network error calling {url}: {exc}") from exc
        if resp.status_code != 200:
            raise NWSError(
                f"HTTP {resp.status_code} from {url}: {resp.text[:500]}"
            )
        raw_bytes = resp.content
        server_date = resp.headers.get("Date")
        try:
            parsed = resp.json()
        except ValueError as exc:
            raise NWSError(f"Malformed JSON from {url}: {exc}") from exc
        return parsed, raw_bytes, server_date

    # ------------------------------------------------------------------
    def get_points(self, lat: float, lon: float) -> dict:
        """Resolve coordinates to NWS grid metadata (cached)."""
        key = (round(lat, 4), round(lon, 4))
        if key not in self._points_cache:
            self._points_cache[key] = self._get(
                f"{self.base_url}/points/{key[0]},{key[1]}"
            )
        return self._points_cache[key]

    def get_hourly_forecast(self, lat: float, lon: float) -> dict:
        """Fetch the hourly forecast for a location.

        Follows the forecastHourly URL returned by the points lookup,
        as the NWS docs instruct — we never construct grid URLs by hand.
        """
        points = self.get_points(lat, lon)
        url = points["properties"]["forecastHourly"]
        return self._get(url)

    def get_points_raw(self, lat: float, lon: float) -> PointsRaw:
        """Resolve coordinates to NWS grid metadata; raw materials.

        Returns a PointsRaw NamedTuple (points_json, points_bytes,
        points_date) -- documented and field-named, not a bare tuple,
        for the same silent-mis-ordering reason as HourlyForecastRaw.

        Deliberately does NOT use the get_points() in-memory cache. The
        real reason is NOT "so we always get a fresh snapshot" -- within
        one scheduled run (one process, one poll per city) the cache
        would never be hit anyway, so bypassing it is a no-op as
        deployed. The real reason: IF a long-lived process ever did hit
        the cache, the collector would snapshot the cached bytes stamped
        with a fetch time those bytes never actually had at THIS fetch --
        a false provenance record, the same class of error _get_raw
        exists to prevent by not re-serializing parsed JSON. Always
        fetching fresh here removes that failure mode entirely rather
        than relying on cache-timing luck.

        rounded_coords is the (lat, lon) rounded to 4 decimal places. In
        get_points() this rounding was purely a cache key and had no
        effect on correctness. Here there is no cache, so this rounding
        now DETERMINES which URL is fetched -- i.e. which grid point,
        i.e. which forecast. Whether NWS's /points endpoint actually
        requires or tolerates only 4 decimal places is UNVERIFIED against
        a real response as of this writing; confirm against a live
        capture before trusting this precision (see the forecast
        collector's fixture-capture step).
        """
        rounded_coords = (round(lat, 4), round(lon, 4))
        return PointsRaw(*self._get_raw(
            f"{self.base_url}/points/{rounded_coords[0]},{rounded_coords[1]}"
        ))

    def get_hourly_forecast_raw(self, lat: float, lon: float) -> HourlyForecastRaw:
        """Fetch the hourly forecast; raw materials for BOTH HTTP calls.

        Mirrors get_hourly_forecast()'s points -> forecastHourly chain,
        but preserves the raw bytes and Date header of both responses so
        the forecast collector can snapshot each verbatim instead of
        re-deriving them from parsed JSON.

        NOTE: points_json["properties"]["forecastHourly"] raises a bare
        KeyError if the key is absent -- unchanged from the existing
        get_hourly_forecast() above, deliberately not wrapped in
        NWSError here either, for consistency with that method. Callers
        that need per-unit failure isolation (e.g. a per-city collection
        loop) must catch bare Exception, not narrow to except NWSError,
        or a malformed points response would escape isolation.
        """
        points_json, points_bytes, points_date = self.get_points_raw(lat, lon)
        url = points_json["properties"]["forecastHourly"]
        forecast_json, forecast_bytes, forecast_date = self._get_raw(url)
        return HourlyForecastRaw(
            points_json, points_bytes, points_date,
            forecast_json, forecast_bytes, forecast_date,
        )

    def get_latest_observation(self, station_id: str) -> dict:
        """Latest observation from a specific station (e.g. KPHX).

        This is the SAME kind of station data that feeds the NWS Daily
        Climate Report Kalshi settles on — but the official settlement
        value comes from the Climate Report itself, so observations are
        features, never ground truth. Ground-truth ingestion (CLI
        climate reports) is a Milestone 1b task.
        """
        return self._get(
            f"{self.base_url}/stations/{station_id}/observations/latest"
        )


def extract_forecast_issued_time(forecast_json: dict) -> Optional[str]:
    """Pull the forecast generation timestamp out of a forecast response.

    Storing WHEN a forecast was issued (not just when we collected it)
    is what makes honest point-in-time joins possible later.
    """
    props = forecast_json.get("properties", {})
    return props.get("updateTime") or props.get("generatedAt")
