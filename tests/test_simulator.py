import sys
import random
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


SIMULATOR_PATH = Path(__file__).parents[1] / "src" / "simulator"
sys.path.insert(0, str(SIMULATOR_PATH))

from main import HealthState, app, components, randomize_fleet  # noqa: E402


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


def test_individual_fault_endpoint_preserves_its_response_contract(client):
    response = client.post(
        "/components/detroit-panel-01/fault",
        json={"status": "offline", "delaySeconds": 0},
    )

    assert response.status_code == 200
    assert response.json() == {
        "deviceId": "detroit-panel-01",
        "siteId": "detroit",
        "componentType": "controller",
        "status": "offline",
        "delaySeconds": 0,
    }


def test_site_fault_changes_gateway_and_all_controllers(client):
    response = client.post(
        "/sites/detroit/fault",
        json={"status": "offline", "delaySeconds": 1.5},
    )

    assert response.status_code == 200
    assert response.json()["siteId"] == "detroit"
    assert response.json()["status"] == "offline"
    assert response.json()["affectedComponentCount"] == 6
    assert set(response.json()["affectedComponentIds"]) == {
        "detroit-gateway-01",
        "detroit-panel-01",
        "detroit-panel-02",
        "detroit-panel-03",
        "detroit-panel-04",
        "detroit-panel-05",
    }
    assert all(
        component["status"] == HealthState.OFFLINE and component["delaySeconds"] == 1.5
        for component in components.values()
        if component["siteId"] == "detroit"
    )


def test_site_restore_returns_all_affected_components_online(client):
    client.post("/sites/atlanta/fault", json={"status": "offline", "delaySeconds": 2})
    response = client.post("/sites/atlanta/fault", json={"status": "online", "delaySeconds": 0})

    assert response.status_code == 200
    assert all(
        component["status"] == HealthState.ONLINE and component["delaySeconds"] == 0
        for component in components.values()
        if component["siteId"] == "atlanta"
    )


def test_unknown_site_returns_not_found(client):
    response = client.post("/sites/unknown/fault", json={"status": "offline"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Site 'unknown' was not found."


def test_fleet_reset_restores_every_component_and_clears_delays(client):
    client.post("/components/detroit-panel-01/fault", json={"status": "offline", "delaySeconds": 2})
    client.post("/components/video-management-server-01/fault", json={"status": "degraded", "delaySeconds": 1})

    response = client.post("/fleet/reset")

    assert response.status_code == 200
    assert response.json()["componentCount"] == len(components)
    assert response.json()["status"] == "online"
    assert all(component["status"] == HealthState.ONLINE for component in components.values())
    assert all(component["delaySeconds"] == 0 for component in components.values())


def test_fleet_randomize_is_controlled_and_resettable(client):
    gateway_outage, delayed_component_ids = randomize_fleet(random.Random(7))

    assert gateway_outage in {None, "detroit-gateway-01", "atlanta-gateway-01", "phoenix-gateway-01"}
    assert len(delayed_component_ids) <= 2
    assert {component["status"] for component in components.values()} <= set(HealthState)
    assert any(component["status"] == HealthState.ONLINE for component in components.values())

    response = client.post("/fleet/reset")
    assert response.status_code == 200
    assert all(component["status"] == HealthState.ONLINE for component in components.values())


def test_fleet_randomize_endpoint_returns_controlled_state_structure(client):
    response = client.post("/fleet/randomize")

    assert response.status_code == 200
    body = response.json()
    assert len(body["components"]) == len(components)
    assert body["gatewayOutage"] is None or body["gatewayOutage"].endswith("gateway-01")
    assert set(body["delayedComponentIds"]) <= set(components)
    assert any(component["status"] == "online" for component in body["components"])


def test_fleet_state_returns_all_components_and_dependency_aware_status(client):
    client.post("/components/phoenix-gateway-01/fault", json={"status": "offline"})
    response = client.get("/fleet/state")

    assert response.status_code == 200
    fleet_components = {component["deviceId"]: component for component in response.json()["components"]}
    assert len(fleet_components) == len(components)
    assert fleet_components["phoenix-panel-01"] == {
        "deviceId": "phoenix-panel-01",
        "siteId": "phoenix",
        "componentType": "controller",
        "status": "online",
        "delaySeconds": 0.0,
        "effectiveStatus": "unreachable",
    }


def test_fleet_state_includes_shared_services_and_reset_restores_them(client):
    client.post(
        "/components/access-control-server-01/fault",
        json={"status": "offline", "delaySeconds": 1},
    )
    state_response = client.get("/fleet/state")
    state = {component["deviceId"]: component for component in state_response.json()["components"]}

    assert state["access-control-server-01"]["siteId"] == "shared"
    assert state["access-control-server-01"]["status"] == "offline"
    assert "video-management-server-01" in state

    client.post("/fleet/reset")
    assert components["access-control-server-01"]["status"] == HealthState.ONLINE
    assert components["access-control-server-01"]["delaySeconds"] == 0.0
