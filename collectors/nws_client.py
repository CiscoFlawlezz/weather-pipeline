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
  change, so we cache them per city for the process lifetime.
"""

from typing import Optional

import requests

DEFAULT_BASE_URL = "https://api.weather.gov"


class NWSError(Exception):
    """Raised for any non-success NWS API response."""


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
