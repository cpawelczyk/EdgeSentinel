import sys
from pathlib import Path

import pytest


SIMULATOR_PATH = Path(__file__).parents[1] / "src" / "simulator"
sys.path.insert(0, str(SIMULATOR_PATH))

from run_scenario import DEFAULT_STEP_DELAY_SECONDS, parse_arguments, run_scenario  # noqa: E402


def test_scenario_applies_the_expected_fault_sequence():
    fault_calls = []
    sleep_calls = []
    output = []

    run_scenario(
        5.0,
        apply_fault=lambda device_id, status, delay: fault_calls.append(
            (device_id, status, delay)
        ),
        sleep=sleep_calls.append,
        output=output.append,
    )

    assert fault_calls == [
        ("phoenix-gateway-01", "online", 0.0),
        ("phoenix-panel-03", "online", 0.0),
        ("phoenix-panel-03", "online", 3.0),
        ("phoenix-panel-03", "online", 0.0),
        ("phoenix-gateway-01", "offline", 0.0),
        ("phoenix-gateway-01", "online", 0.0),
    ]
    assert sleep_calls == [5.0] * 5
    assert output[-1] == "Scenario complete."


def test_scenario_uses_a_sensible_default_step_delay():
    assert parse_arguments([]).step_delay == DEFAULT_STEP_DELAY_SECONDS


def test_invalid_step_delay_is_rejected():
    with pytest.raises(SystemExit):
        parse_arguments(["--step-delay", "0"])
