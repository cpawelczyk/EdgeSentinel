"""Minimal local simulator for the Edge Sentinel vertical slice."""

from asyncio import sleep
from enum import Enum

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
