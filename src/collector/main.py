"""Local monitoring collector for the Edge Sentinel simulator."""

import argparse
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


def transition_record(previous_status: str, record: dict) -> dict | None:
    current_status = record["status"]
    if previous_status == current_status:
        return None

    transition = "statusChanged"
    if previous_status in {"offline", "unknown"} and current_status == "online":
        transition = "recovered"

    return {
        "eventType": "statusTransition",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deviceId": record["deviceId"],
        "previousStatus": previous_status,
        "currentStatus": current_status,
        "transition": transition,
    }


def run_pass(
    previous_statuses: dict,
    inventory: list = INVENTORY,
    collect=collect_component,
    output=print,
) -> None:
    """Collect one record for every component and print status changes."""
    for component in inventory:
        record = collect(component)
        output(json.dumps(record))

        previous_status = previous_statuses.get(record["deviceId"])
        if previous_status is not None:
            transition = transition_record(previous_status, record)
            if transition is not None:
                output(json.dumps(transition))

        previous_statuses[record["deviceId"]] = record["status"]


def positive_interval(value: str) -> float:
    interval = float(value)
    if interval <= 0:
        raise argparse.ArgumentTypeError("interval must be greater than zero")
    return interval


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Edge Sentinel simulator health endpoints.")
    parser.add_argument("--once", action="store_true", help="Poll each component once and exit.")
    parser.add_argument(
        "--interval",
        type=positive_interval,
        default=5.0,
        help="Seconds between polling passes in continuous mode (default: 5).",
    )
    return parser.parse_args(arguments)


def run_collector(
    once: bool,
    interval: float,
    inventory: list = INVENTORY,
    collect=collect_component,
    output=print,
    sleep=time.sleep,
) -> None:
    previous_statuses = {}

    try:
        while True:
            run_pass(previous_statuses, inventory, collect, output)
            if once:
                return
            sleep(interval)
    except KeyboardInterrupt:
        output("Collector stopped.")


def main(arguments: list[str] | None = None) -> None:
    args = parse_arguments(arguments)
    run_collector(args.once, args.interval)


if __name__ == "__main__":
    main()
