"""Local monitoring collector for the Edge Sentinel simulator."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


DEFAULT_INVENTORY_PATH = Path(__file__).with_name("inventory.json")
DEFAULT_LATENCY_THRESHOLD_MS = 2000.0


class InventoryError(Exception):
    """Raised when the collector inventory cannot be used."""


def load_inventory(path: Path = DEFAULT_INVENTORY_PATH) -> list[dict]:
    try:
        inventory = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InventoryError(f"inventory file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise InventoryError(f"inventory contains malformed JSON: {path}") from error

    if not isinstance(inventory, list):
        raise InventoryError("inventory root must be a list")
    if not inventory:
        raise InventoryError("inventory must contain at least one component")

    device_ids = set()
    for entry in inventory:
        if not isinstance(entry, dict):
            raise InventoryError("each inventory entry must be an object")

        device_id = entry.get("deviceId")
        site_id = entry.get("siteId")
        component_type = entry.get("componentType")
        health_url = entry.get("healthUrl")
        if not isinstance(device_id, str) or not device_id:
            raise InventoryError("each inventory entry requires a deviceId")
        if not isinstance(site_id, str) or not site_id:
            raise InventoryError(f"inventory entry '{device_id}' requires a siteId")
        if not isinstance(component_type, str) or not component_type:
            raise InventoryError(f"inventory entry '{device_id}' requires a componentType")
        if not isinstance(health_url, str) or not health_url:
            raise InventoryError(f"inventory entry '{device_id}' requires a healthUrl")
        if device_id in device_ids:
            raise InventoryError(f"duplicate deviceId: {device_id}")

        device_ids.add(device_id)

    return inventory


def base_record(component: dict) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "deviceId": component["deviceId"],
        "siteId": component["siteId"],
        "componentType": component["componentType"],
        "checkType": "httpHealth",
    }


def collect_component(
    component: dict, latency_threshold_ms: float = DEFAULT_LATENCY_THRESHOLD_MS
) -> dict:
    """Poll one simulator health endpoint and normalize the result."""
    started_at = time.perf_counter()

    try:
        response = httpx.get(component["healthUrl"], timeout=5.0)
        response.raise_for_status()
        try:
            health = response.json()
        except ValueError:
            health = None
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)

        status = health.get("status") if isinstance(health, dict) else None
        if not isinstance(status, str) or status not in {"online", "degraded", "offline"}:
            return {
                **base_record(component),
                "status": "unknown",
                "latencyMs": latency_ms,
                "failureReason": "invalidResponse",
            }

        failure_reason = None

        if status == "online" and latency_ms > latency_threshold_ms:
            status = "degraded"
            failure_reason = "highLatency"

        return {
            **base_record(component),
            "status": status,
            "latencyMs": latency_ms,
            "failureReason": failure_reason,
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
    inventory: list,
    collect=collect_component,
    output=print,
    latency_threshold_ms: float = DEFAULT_LATENCY_THRESHOLD_MS,
) -> None:
    """Collect one record for every component and print status changes."""
    for component in inventory:
        record = collect(component, latency_threshold_ms)
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


def positive_latency_threshold(value: str) -> float:
    threshold = float(value)
    if threshold <= 0:
        raise argparse.ArgumentTypeError("latency threshold must be greater than zero")
    return threshold


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Poll Edge Sentinel simulator health endpoints.")
    parser.add_argument("--once", action="store_true", help="Poll each component once and exit.")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=DEFAULT_INVENTORY_PATH,
        help="Path to the component inventory JSON file.",
    )
    parser.add_argument(
        "--interval",
        type=positive_interval,
        default=5.0,
        help="Seconds between polling passes in continuous mode (default: 5).",
    )
    parser.add_argument(
        "--latency-threshold-ms",
        type=positive_latency_threshold,
        default=DEFAULT_LATENCY_THRESHOLD_MS,
        help="Milliseconds before a successful online response is classified as degraded (default: 2000).",
    )
    return parser.parse_args(arguments)


def run_collector(
    once: bool,
    interval: float,
    inventory: list,
    collect=collect_component,
    output=print,
    sleep=time.sleep,
    latency_threshold_ms: float = DEFAULT_LATENCY_THRESHOLD_MS,
) -> None:
    previous_statuses = {}

    try:
        while True:
            run_pass(previous_statuses, inventory, collect, output, latency_threshold_ms)
            if once:
                return
            sleep(interval)
    except KeyboardInterrupt:
        output("Collector stopped.")


def main(arguments: list[str] | None = None) -> int:
    args = parse_arguments(arguments)
    try:
        inventory = load_inventory(args.inventory)
    except InventoryError as error:
        print(f"Collector startup error: {error}", file=sys.stderr)
        return 1

    run_collector(
        args.once,
        args.interval,
        inventory,
        latency_threshold_ms=args.latency_threshold_ms,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
