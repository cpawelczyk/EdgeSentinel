"""One-shot local monitoring collector for the Edge Sentinel simulator."""

import json
import time
from datetime import datetime, timezone

import httpx


INVENTORY = [
    {
        "deviceId": "detroit-panel-01",
        "siteId": "detroit",
        "componentType": "controller",
        "url": "http://127.0.0.1:8000/components/detroit-panel-01/health",
    },
    {
        "deviceId": "detroit-gateway-01",
        "siteId": "detroit",
        "componentType": "gateway",
        "url": "http://127.0.0.1:8000/components/detroit-gateway-01/health",
    },
    {
        "deviceId": "access-control-server-01",
        "siteId": "shared",
        "componentType": "accessControlServer",
        "url": "http://127.0.0.1:8000/components/access-control-server-01/health",
    },
]


def base_record(component: dict) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deviceId": component["deviceId"],
        "siteId": component["siteId"],
        "componentType": component["componentType"],
        "checkType": "httpHealth",
    }


def collect_component(component: dict) -> dict:
    """Poll one simulator health endpoint and normalize the result."""
    started_at = time.perf_counter()

    try:
        response = httpx.get(component["url"], timeout=5.0)
        response.raise_for_status()
        health = response.json()
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

        return {
            **base_record(component),
            "status": health["status"],
            "latencyMs": latency_ms,
            "failureReason": None,
        }
    except httpx.TimeoutException:
        failure_reason = "timeout"
    except httpx.HTTPStatusError:
        failure_reason = "httpError"
    except httpx.RequestError:
        failure_reason = "connectionFailure"

    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    return {
        **base_record(component),
        "status": "unknown",
        "latencyMs": latency_ms,
        "failureReason": failure_reason,
    }


def main() -> None:
    for component in INVENTORY:
        print(json.dumps(collect_component(component)))


if __name__ == "__main__":
    main()
