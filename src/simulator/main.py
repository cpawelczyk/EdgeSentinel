"""Minimal local simulator for the Edge Sentinel vertical slice."""

from asyncio import sleep
from enum import Enum
import random

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class HealthState(str, Enum):
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class FaultRequest(BaseModel):
    status: HealthState
    delaySeconds: float | None = Field(default=None, ge=0)


app = FastAPI(title="Edge Sentinel Simulator")

components = {
    "detroit-gateway-01": {
        "deviceId": "detroit-gateway-01",
        "siteId": "detroit",
        "componentType": "gateway",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "detroit-panel-01": {
        "deviceId": "detroit-panel-01",
        "siteId": "detroit",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "detroit-panel-02": {
        "deviceId": "detroit-panel-02",
        "siteId": "detroit",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "detroit-panel-03": {
        "deviceId": "detroit-panel-03",
        "siteId": "detroit",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "detroit-panel-04": {
        "deviceId": "detroit-panel-04",
        "siteId": "detroit",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "detroit-panel-05": {
        "deviceId": "detroit-panel-05",
        "siteId": "detroit",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "atlanta-gateway-01": {
        "deviceId": "atlanta-gateway-01",
        "siteId": "atlanta",
        "componentType": "gateway",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "atlanta-panel-01": {
        "deviceId": "atlanta-panel-01",
        "siteId": "atlanta",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "atlanta-panel-02": {
        "deviceId": "atlanta-panel-02",
        "siteId": "atlanta",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "atlanta-panel-03": {
        "deviceId": "atlanta-panel-03",
        "siteId": "atlanta",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "atlanta-panel-04": {
        "deviceId": "atlanta-panel-04",
        "siteId": "atlanta",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "atlanta-panel-05": {
        "deviceId": "atlanta-panel-05",
        "siteId": "atlanta",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "phoenix-gateway-01": {
        "deviceId": "phoenix-gateway-01",
        "siteId": "phoenix",
        "componentType": "gateway",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "phoenix-panel-01": {
        "deviceId": "phoenix-panel-01",
        "siteId": "phoenix",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "phoenix-panel-02": {
        "deviceId": "phoenix-panel-02",
        "siteId": "phoenix",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "phoenix-panel-03": {
        "deviceId": "phoenix-panel-03",
        "siteId": "phoenix",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "phoenix-panel-04": {
        "deviceId": "phoenix-panel-04",
        "siteId": "phoenix",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "phoenix-panel-05": {
        "deviceId": "phoenix-panel-05",
        "siteId": "phoenix",
        "componentType": "controller",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "access-control-server-01": {
        "deviceId": "access-control-server-01",
        "siteId": "shared",
        "componentType": "accessControlServer",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
    "video-management-server-01": {
        "deviceId": "video-management-server-01",
        "siteId": "shared",
        "componentType": "videoServer",
        "status": HealthState.ONLINE,
        "delaySeconds": 0.0,
    },
}

SITE_IDS = ("detroit", "atlanta", "phoenix")


def health_response(component: dict) -> dict:
    return {
        "deviceId": component["deviceId"],
        "siteId": component["siteId"],
        "componentType": component["componentType"],
        "status": component["status"],
    }


def get_component(device_id: str) -> dict:
    component = components.get(device_id)
    if component is None:
        raise HTTPException(status_code=404, detail=f"Component '{device_id}' was not found.")

    return component


def controller_is_blocked_by_gateway(component: dict) -> bool:
    if component["componentType"] != "controller":
        return False

    gateway = components.get(f"{component['siteId']}-gateway-01")
    return gateway is not None and gateway["status"] == HealthState.OFFLINE


def component_state(component: dict) -> dict:
    """Return stored state together with its dependency-aware observable state."""
    stored_status = component["status"].value
    effective_status = "unreachable" if controller_is_blocked_by_gateway(component) else stored_status
    return {
        "deviceId": component["deviceId"],
        "siteId": component["siteId"],
        "componentType": component["componentType"],
        "status": stored_status,
        "delaySeconds": component["delaySeconds"],
        "effectiveStatus": effective_status,
    }


def reset_fleet() -> None:
    """Restore every simulator component to its healthy, immediate-response state."""
    for component in components.values():
        component["status"] = HealthState.ONLINE
        component["delaySeconds"] = 0.0


def randomize_fleet(randomizer=random) -> tuple[str | None, list[str]]:
    """Create one controlled, demo-friendly fleet state from a healthy baseline."""
    reset_fleet()

    gateways = [component for component in components.values() if component["componentType"] == "gateway"]
    non_gateways = [component for component in components.values() if component["componentType"] != "gateway"]
    gateway_outage = None
    if randomizer.random() < 0.25:
        gateway = randomizer.choice(gateways)
        gateway["status"] = HealthState.OFFLINE
        gateway_outage = gateway["deviceId"]

    for component in randomizer.sample(non_gateways, k=2):
        component["status"] = randomizer.choice((HealthState.DEGRADED, HealthState.OFFLINE))

    online_components = [
        component for component in non_gateways if component["status"] == HealthState.ONLINE
    ]
    delayed_components = randomizer.sample(online_components, k=min(2, len(online_components)))
    for component in delayed_components:
        component["delaySeconds"] = randomizer.choice((0.5, 1.0, 2.0))

    return gateway_outage, [component["deviceId"] for component in delayed_components]


@app.get("/components/{device_id}/health")
async def get_component_health(device_id: str) -> dict:
    """Return the current health state for a simulated component."""
    component = get_component(device_id)
    if controller_is_blocked_by_gateway(component):
        raise HTTPException(
            status_code=503,
            detail="Controller is unreachable because its site gateway is offline.",
        )

    await sleep(component["delaySeconds"])
    return health_response(component)


@app.post("/components/{device_id}/fault")
async def set_component_fault(device_id: str, fault: FaultRequest) -> dict:
    """Manually set component health and an optional response delay."""
    component = get_component(device_id)
    component["status"] = fault.status

    if fault.delaySeconds is not None:
        component["delaySeconds"] = fault.delaySeconds

    return {
        **health_response(component),
        "delaySeconds": component["delaySeconds"],
    }


@app.post("/sites/{site_id}/fault")
async def set_site_fault(site_id: str, fault: FaultRequest) -> dict:
    """Set stored state for a site's gateway and every controller in that site."""
    if site_id not in SITE_IDS:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' was not found.")

    affected_components = [component for component in components.values() if component["siteId"] == site_id]
    for component in affected_components:
        component["status"] = fault.status
        if fault.delaySeconds is not None:
            component["delaySeconds"] = fault.delaySeconds

    affected_ids = [component["deviceId"] for component in affected_components]
    return {
        "siteId": site_id,
        "status": fault.status.value,
        "affectedComponentIds": affected_ids,
        "affectedComponentCount": len(affected_ids),
    }


@app.post("/fleet/reset")
async def reset_fleet_state() -> dict:
    """Restore the entire fleet to a healthy baseline."""
    reset_fleet()
    component_ids = list(components)
    return {
        "componentCount": len(component_ids),
        "status": HealthState.ONLINE.value,
        "affectedComponentIds": component_ids,
    }


@app.post("/fleet/randomize")
async def randomize_fleet_state() -> dict:
    """Apply one bounded randomized state suitable for a local demonstration."""
    gateway_outage, delayed_component_ids = randomize_fleet()
    return {
        "components": [component_state(component) for component in components.values()],
        "gatewayOutage": gateway_outage,
        "delayedComponentIds": delayed_component_ids,
    }


@app.get("/fleet/state")
async def get_fleet_state() -> dict:
    """Return the fleet's stored and dependency-aware observable state."""
    return {"components": [component_state(component) for component in components.values()]}
