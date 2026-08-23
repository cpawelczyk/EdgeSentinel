"""Simulator state mapping used by the control console."""

from dataclasses import dataclass


SUPPORTED_STATUSES = frozenset({"online", "degraded", "offline", "unreachable"})
SITE_IDS = ("detroit", "phoenix", "atlanta")


def visual_status(status: str, effective_status: str) -> str:
    """Prefer the dependency-aware state when choosing a visual treatment."""
    if effective_status in SUPPORTED_STATUSES:
        return effective_status
    if status in SUPPORTED_STATUSES:
        return status
    return "offline"


@dataclass(frozen=True)
class DeviceState:
    device_id: str
    site_id: str
    component_type: str
    status: str
    delay_seconds: float
    effective_status: str

    @property
    def display_status(self) -> str:
        return visual_status(self.status, self.effective_status)

    @classmethod
    def from_payload(cls, payload: dict) -> "DeviceState":
        required = ("deviceId", "siteId", "componentType", "status", "delaySeconds", "effectiveStatus")
        if not isinstance(payload, dict) or any(field not in payload for field in required):
            raise ValueError("Simulator returned an incomplete component state.")

        device_id = payload["deviceId"]
        site_id = payload["siteId"]
        component_type = payload["componentType"]
        status = payload["status"]
        effective_status = payload["effectiveStatus"]
        delay_seconds = payload["delaySeconds"]
        if not all(isinstance(value, str) for value in (device_id, site_id, component_type, status, effective_status)):
            raise ValueError("Simulator returned an invalid component state.")
        if not isinstance(delay_seconds, (int, float)):
            raise ValueError("Simulator returned an invalid component delay.")

        return cls(
            device_id=device_id,
            site_id=site_id,
            component_type=component_type,
            status=status,
            delay_seconds=float(delay_seconds),
            effective_status=effective_status,
        )


@dataclass(frozen=True)
class FleetState:
    devices: tuple[DeviceState, ...]

    @classmethod
    def from_payload(cls, payload: dict) -> "FleetState":
        components = payload.get("components") if isinstance(payload, dict) else None
        if not isinstance(components, list):
            raise ValueError("Simulator returned an invalid fleet state.")
        return cls(tuple(DeviceState.from_payload(component) for component in components))

    @property
    def by_id(self) -> dict[str, DeviceState]:
        return {device.device_id: device for device in self.devices}

    def for_site(self, site_id: str) -> tuple[DeviceState, ...]:
        return tuple(device for device in self.devices if device.site_id == site_id)
