"""Local monitoring collector for the Edge Sentinel simulator."""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential


DEFAULT_INVENTORY_PATH = Path(__file__).with_name("inventory.json")
DEFAULT_ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_LATENCY_THRESHOLD_MS = 2000.0
AZURE_STREAM_NAME = "Custom-EdgeSentinel"
AZURE_MONITOR_SCOPE = "https://monitor.azure.com/.default"
AZURE_INGESTION_API_VERSION = "2023-01-01"
AZURE_REQUIRED_ENVIRONMENT_VARIABLES = (
    "EDGESENTINEL_DCR_ENDPOINT",
    "EDGESENTINEL_DCR_IMMUTABLE_ID",
)


class InventoryError(Exception):
    """Raised when the collector inventory cannot be used."""


class AzureConfigurationError(Exception):
    """Raised when Azure export configuration is incomplete."""


def load_local_environment(path: Path = DEFAULT_ENV_FILE_PATH) -> dict[str, str]:
    """Read simple key/value configuration from the project-local .env file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}

    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip().strip('"').strip("'")
        if name in AZURE_REQUIRED_ENVIRONMENT_VARIABLES:
            values[name] = value
    return values


def resolve_azure_environment(
    environ: dict | None = None, dotenv_path: Path = DEFAULT_ENV_FILE_PATH
) -> dict:
    """Resolve Azure settings without overwriting explicit process environment values."""
    environment = dict(os.environ if environ is None else environ)
    for name, value in load_local_environment(dotenv_path).items():
        if not environment.get(name):
            environment[name] = value
    return environment


def load_azure_configuration(
    environ: dict | None = None, dotenv_path: Path = DEFAULT_ENV_FILE_PATH
) -> dict:
    """Load the Azure export settings required by the Logs Ingestion API."""
    environment = resolve_azure_environment(environ, dotenv_path)
    missing = [name for name in AZURE_REQUIRED_ENVIRONMENT_VARIABLES if not environment.get(name)]
    if missing:
        raise AzureConfigurationError(
            "missing required Azure environment variables: " + ", ".join(missing)
        )

    return {
        "endpoint": environment["EDGESENTINEL_DCR_ENDPOINT"].rstrip("/"),
        "dcr_immutable_id": environment["EDGESENTINEL_DCR_IMMUTABLE_ID"],
    }


class AzureLogExporter:
    """Send normalized check records to Azure Monitor Logs."""

    def __init__(self, configuration: dict, credential_factory=None):
        self.endpoint = configuration["endpoint"].rstrip("/")
        self.dcr_immutable_id = configuration["dcr_immutable_id"]
        self.credential = (credential_factory or DefaultAzureCredential)()

    @property
    def ingestion_url(self) -> str:
        return (
            f"{self.endpoint}/dataCollectionRules/{self.dcr_immutable_id}/streams/"
            f"{AZURE_STREAM_NAME}?api-version={AZURE_INGESTION_API_VERSION}"
        )

    def send(self, records: list[dict], output=print) -> bool:
        """Send one completed collection batch, keeping Azure failures non-fatal."""
        if not records:
            return True

        try:
            token = self.credential.get_token(AZURE_MONITOR_SCOPE)
        except Exception:
            output("Azure export warning: failed to acquire Azure access token.")
            return False

        try:
            response = httpx.post(
                self.ingestion_url,
                headers={
                    "Authorization": f"Bearer {token.token}",
                    "Content-Type": "application/json",
                },
                json=records,
                timeout=10.0,
            )
            response.raise_for_status()
            return True
        except Exception:
            output("Azure export warning: failed to send telemetry batch to Azure.")
            return False


def check_azure_readiness(
    environ: dict | None = None,
    credential_factory=None,
    dotenv_path: Path = DEFAULT_ENV_FILE_PATH,
) -> None:
    """Verify the configured credential can access the Azure Monitor scope."""
    load_azure_configuration(environ, dotenv_path)
    credential = (credential_factory or DefaultAzureCredential)()
    credential.get_token(AZURE_MONITOR_SCOPE)


def write_status_file(path: Path, status: dict) -> None:
    """Atomically publish collector activity for a local process supervisor."""
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(json.dumps(status), encoding="utf-8")
    temporary_path.replace(path)


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
    azure_exporter: AzureLogExporter | None = None,
    status_file: Path | None = None,
) -> None:
    """Collect one record for every component and print status changes."""
    records = []
    for component in inventory:
        record = collect(component, latency_threshold_ms)
        records.append(record)
        output(json.dumps(record))

        previous_status = previous_statuses.get(record["deviceId"])
        if previous_status is not None:
            transition = transition_record(previous_status, record)
            if transition is not None:
                output(json.dumps(transition))

        previous_statuses[record["deviceId"]] = record["status"]

    azure_success = None
    if azure_exporter is not None:
        azure_success = azure_exporter.send(records, output)

    if status_file is not None:
        completed_at = datetime.now(timezone.utc).isoformat()
        status = {"lastSuccessfulPass": completed_at}
        if azure_success:
            status["lastAzureIngestion"] = completed_at
        elif azure_success is False:
            status["lastAzureFailure"] = completed_at
        try:
            write_status_file(status_file, status)
        except OSError:
            output("Collector warning: failed to write runtime status.")


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
        "--azure",
        action="store_true",
        help="Also send normalized check records to Azure Monitor Logs.",
    )
    parser.add_argument(
        "--status-file",
        type=Path,
        help=argparse.SUPPRESS,
    )
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
    azure_exporter: AzureLogExporter | None = None,
    status_file: Path | None = None,
) -> None:
    previous_statuses = {}

    try:
        while True:
            run_pass(
                previous_statuses,
                inventory,
                collect,
                output,
                latency_threshold_ms,
                azure_exporter,
                status_file,
            )
            if once:
                return
            sleep(interval)
    except KeyboardInterrupt:
        output("Collector stopped.")


def main(arguments: list[str] | None = None) -> int:
    args = parse_arguments(arguments)
    azure_exporter = None
    if args.azure:
        try:
            azure_exporter = AzureLogExporter(load_azure_configuration())
        except AzureConfigurationError as error:
            print(f"Collector startup error: {error}", file=sys.stderr)
            return 1

    try:
        inventory = load_inventory(args.inventory)
    except InventoryError as error:
        print(f"Collector startup error: {error}", file=sys.stderr)
        return 1

    collector_arguments = {
        "latency_threshold_ms": args.latency_threshold_ms,
    }
    if args.status_file is not None:
        collector_arguments["status_file"] = args.status_file
    if azure_exporter is not None:
        collector_arguments["azure_exporter"] = azure_exporter
    run_collector(args.once, args.interval, inventory, **collector_arguments)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
