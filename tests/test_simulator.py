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


def test_online_gateway_leaves_its_controllers_reachable(client):
    response = client.get("/components/phoenix-panel-03/health")

    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_offline_phoenix_gateway_blocks_only_phoenix_controllers(client):
    gateway_response = client.post(
        "/components/phoenix-gateway-01/fault",
        json={"status": "offline"},
    )
    phoenix_responses = [
        client.get(f"/components/phoenix-panel-0{panel}/health")
        for panel in range(1, 6)
    ]
    detroit_response = client.get("/components/detroit-panel-03/health")
    atlanta_response = client.get("/components/atlanta-panel-03/health")

    assert gateway_response.status_code == 200
    assert gateway_response.json()["status"] == "offline"
    assert all(response.status_code == 503 for response in phoenix_responses)
    assert components["phoenix-panel-03"]["status"] == HealthState.ONLINE
    assert detroit_response.status_code == 200
    assert atlanta_response.status_code == 200


@pytest.mark.parametrize(
    ("device_id", "component_type", "site_id", "status"),
    [
        ("detroit-gateway-01", "gateway", "detroit", "degraded"),
        ("atlanta-panel-03", "controller", "atlanta", "offline"),
        ("phoenix-panel-03", "controller", "phoenix", "degraded"),
        ("video-management-server-01", "videoServer", "shared", "offline"),
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
