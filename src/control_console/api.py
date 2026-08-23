"""Small REST client for the local EdgeSentinel simulator control API."""

import httpx

from .models import FleetState


DEFAULT_SIMULATOR_URL = "http://127.0.0.1:8000"


class SimulatorApiError(Exception):
    """A concise, user-safe simulator API failure."""


class SimulatorClient:
    def __init__(self, base_url: str = DEFAULT_SIMULATOR_URL, timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        try:
            response = httpx.request(
                method,
                f"{self.base_url}{path}",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise SimulatorApiError("Simulator request failed.") from error

        if not isinstance(body, dict):
            raise SimulatorApiError("Simulator returned an invalid response.")
        return body

    def get_fleet_state(self) -> FleetState:
        try:
            return FleetState.from_payload(self._request("GET", "/fleet/state"))
        except ValueError as error:
            raise SimulatorApiError("Simulator returned an invalid fleet state.") from error

    def set_component_status(self, device_id: str, status: str) -> dict:
        return self._request("POST", f"/components/{device_id}/fault", {"status": status})

    def set_site_status(self, site_id: str, status: str) -> dict:
        return self._request("POST", f"/sites/{site_id}/fault", {"status": status})

    def reset_fleet(self) -> dict:
        return self._request("POST", "/fleet/reset")

    def randomize_fleet(self) -> dict:
        return self._request("POST", "/fleet/randomize")
