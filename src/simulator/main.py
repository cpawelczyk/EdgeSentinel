"""Minimal local simulator for the Edge Sentinel vertical slice."""

from asyncio import sleep
from enum import Enum

from fastapi import FastAPI
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


@app.get("/components/detroit-panel-01/health")
async def get_controller_health() -> dict:
    """Return the current health state for Detroit's simulated controller."""
    controller = components["detroit-panel-01"]
    await sleep(controller["delaySeconds"])
    return health_response(controller)


@app.post("/components/detroit-panel-01/fault")
async def set_controller_fault(fault: FaultRequest) -> dict:
    """Manually set controller health and an optional response delay."""
    controller = components["detroit-panel-01"]
    controller["status"] = fault.status

    if fault.delaySeconds is not None:
        controller["delaySeconds"] = fault.delaySeconds

    return {
        **health_response(controller),
        "delaySeconds": controller["delaySeconds"],
    }
