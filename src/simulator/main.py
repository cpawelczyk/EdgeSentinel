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
    "access-control-server-01": {
        "deviceId": "access-control-server-01",
        "siteId": "shared",
        "componentType": "accessControlServer",
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


@app.get("/components/{device_id}/health")
async def get_component_health(device_id: str) -> dict:
    """Return the current health state for a simulated component."""
    component = get_component(device_id)
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
