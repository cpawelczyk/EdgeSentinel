import httpx
import pytest

from src.control_console.api import SimulatorApiError, SimulatorClient
from src.control_console.models import DeviceState, FleetState, visual_status


def component_payload(device_id="detroit-panel-01", status="online", effective_status="online"):
    return {
        "deviceId": device_id,
        "siteId": "detroit",
        "componentType": "controller",
        "status": status,
        "delaySeconds": 0,
        "effectiveStatus": effective_status,
    }


def test_fleet_state_mapping_preserves_stored_and_effective_status():
    fleet = FleetState.from_payload(
        {"components": [component_payload(status="online", effective_status="unreachable")]}
    )

    device = fleet.by_id["detroit-panel-01"]
    assert device.status == "online"
    assert device.effective_status == "unreachable"
    assert device.display_status == "unreachable"


@pytest.mark.parametrize(
    ("status", "effective_status", "expected"),
    [
        ("online", "online", "online"),
        ("degraded", "degraded", "degraded"),
        ("offline", "offline", "offline"),
        ("online", "unreachable", "unreachable"),
    ],
)
def test_status_to_visual_state(status, effective_status, expected):
    assert visual_status(status, effective_status) == expected


def test_invalid_fleet_state_is_rejected():
    with pytest.raises(ValueError, match="invalid fleet state"):
        FleetState.from_payload({"components": "not-a-list"})


def test_simulator_unavailable_is_a_concise_client_error(monkeypatch):
    def request(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("src.control_console.api.httpx.request", request)

    with pytest.raises(SimulatorApiError, match="Simulator request failed"):
        SimulatorClient().get_fleet_state()


def test_component_control_request_is_constructed_correctly(monkeypatch):
    observed = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "offline"}

    def request(method, url, **kwargs):
        observed.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr("src.control_console.api.httpx.request", request)
    SimulatorClient().set_component_status("detroit-panel-01", "offline")

    assert observed == {
        "method": "POST",
        "url": "http://127.0.0.1:8000/components/detroit-panel-01/fault",
        "json": {"status": "offline"},
        "timeout": 3.0,
    }


@pytest.mark.parametrize(
    ("method_name", "expected_path"),
    [
        ("reset_fleet", "/fleet/reset"),
        ("randomize_fleet", "/fleet/randomize"),
    ],
)
def test_global_control_requests_use_correct_endpoints(monkeypatch, method_name, expected_path):
    observed = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {}

    def request(method, url, **kwargs):
        observed.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr("src.control_console.api.httpx.request", request)
    getattr(SimulatorClient(), method_name)()

    assert observed["method"] == "POST"
    assert observed["url"] == f"http://127.0.0.1:8000{expected_path}"
    assert observed["json"] is None
