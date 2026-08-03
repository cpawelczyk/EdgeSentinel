import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


SIMULATOR_PATH = Path(__file__).parents[1] / "src" / "simulator"
sys.path.insert(0, str(SIMULATOR_PATH))

from main import HealthState, app, components  # noqa: E402


@pytest.fixture(autouse=True)
def reset_component_state():
    for component in components.values():
        component["status"] = HealthState.ONLINE
        component["delaySeconds"] = 0.0

    yield

    for component in components.values():
        component["status"] = HealthState.ONLINE
        component["delaySeconds"] = 0.0


@pytest.fixture
def client():
    return TestClient(app)


def test_controller_health_starts_online(client):
    response = client.get("/components/detroit-panel-01/health")

    assert response.status_code == 200
    assert response.json() == {
        "deviceId": "detroit-panel-01",
        "siteId": "detroit",
        "componentType": "controller",
        "status": "online",
    }


def test_controller_can_be_set_to_degraded(client):
    fault_response = client.post(
        "/components/detroit-panel-01/fault",
        json={"status": "degraded"},
    )
    health_response = client.get("/components/detroit-panel-01/health")

    assert fault_response.status_code == 200
    assert health_response.json()["status"] == "degraded"


def test_controller_can_be_set_to_offline(client):
    fault_response = client.post(
        "/components/detroit-panel-01/fault",
        json={"status": "offline"},
    )
    health_response = client.get("/components/detroit-panel-01/health")

    assert fault_response.status_code == 200
    assert health_response.json()["status"] == "offline"


@pytest.mark.parametrize(
    ("device_id", "component_type", "site_id", "status"),
    [
        ("detroit-gateway-01", "gateway", "detroit", "degraded"),
        ("access-control-server-01", "accessControlServer", "shared", "offline"),
    ],
)
def test_existing_components_share_the_health_and_fault_contract(
    client, device_id, component_type, site_id, status
):
    fault_response = client.post(
        f"/components/{device_id}/fault",
        json={"status": status},
    )
    health_response = client.get(f"/components/{device_id}/health")

    assert fault_response.status_code == 200
    assert health_response.json() == {
        "deviceId": device_id,
        "siteId": site_id,
        "componentType": component_type,
        "status": status,
    }


def test_unknown_component_returns_not_found(client):
    response = client.get("/components/unknown-component/health")

    assert response.status_code == 404
