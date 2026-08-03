"""Run a repeatable local fault scenario through the simulator API."""

import argparse
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SIMULATOR_URL = "http://127.0.0.1:8000"
DEFAULT_STEP_DELAY_SECONDS = 10.0


class ScenarioError(Exception):
    """Raised when the scenario cannot communicate with the simulator."""


def post_fault(device_id: str, status: str, delay_seconds: float) -> None:
    """Apply one existing simulator fault request."""
    payload = json.dumps({"status": status, "delaySeconds": delay_seconds}).encode("utf-8")
    request = Request(
        f"{SIMULATOR_URL}/components/{device_id}/fault",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=5.0) as response:
            response.read()
    except (HTTPError, URLError) as error:
        raise ScenarioError(f"could not update {device_id}: {error.reason}") from error


def run_scenario(
    step_delay_seconds: float,
    apply_fault=post_fault,
    sleep=time.sleep,
    output=print,
) -> None:
    """Run one deterministic scenario using only existing simulator behaviors."""
    apply_fault("phoenix-gateway-01", "online", 0.0)
    apply_fault("phoenix-panel-03", "online", 0.0)
    output("Scenario initialized: Phoenix gateway and panel are online.")
    sleep(step_delay_seconds)

    apply_fault("phoenix-panel-03", "online", 3.0)
    output("Scenario step: Phoenix panel response delay set to 3 seconds.")
    sleep(step_delay_seconds)

    apply_fault("phoenix-panel-03", "online", 0.0)
    output("Scenario step: Phoenix panel response delay cleared.")
    sleep(step_delay_seconds)

    apply_fault("phoenix-gateway-01", "offline", 0.0)
    output("Scenario step: Phoenix gateway set offline.")
    sleep(step_delay_seconds)

    apply_fault("phoenix-gateway-01", "online", 0.0)
    output("Scenario step: Phoenix gateway restored online.")
    sleep(step_delay_seconds)

    output("Scenario complete.")


def positive_step_delay(value: str) -> float:
    delay = float(value)
    if delay <= 0:
        raise argparse.ArgumentTypeError("step delay must be greater than zero")
    return delay


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Edge Sentinel local fault scenario.")
    parser.add_argument(
        "--step-delay",
        type=positive_step_delay,
        default=DEFAULT_STEP_DELAY_SECONDS,
        help="Seconds to wait after each scenario step (default: 10).",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    args = parse_arguments(arguments)
    try:
        run_scenario(args.step_delay)
    except ScenarioError as error:
        print(f"Scenario startup error: {error}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
