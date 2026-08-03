import json
from pathlib import Path

import httpx
import pytest

from src.collector.main import (
    InventoryError,
    collect_component,
    load_inventory,
    main as collector_main,
    parse_arguments,
    run_collector,
    run_pass,
)


COMPONENT = {
    "deviceId": "detroit-panel-01",
    "siteId": "detroit",
    "componentType": "controller",
    "healthUrl": "http://simulator.test/components/detroit-panel-01/health",
}


class FakeResponse:
    def __init__(self, status: str):
        self.status = status

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "deviceId": "detroit-panel-01",
            "siteId": "detroit",
            "componentType": "controller",
            "status": self.status,
        }


def test_valid_inventory_loads(monkeypatch):
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *args, **kwargs: (
            '[{"deviceId": "detroit-panel-01", "siteId": "detroit", '
            '"componentType": "controller", "healthUrl": "http://simulator.test/health"}]'
        ),
    )

    assert load_inventory(Path("inventory.json")) == [
        {
            "deviceId": "detroit-panel-01",
            "siteId": "detroit",
            "componentType": "controller",
            "healthUrl": "http://simulator.test/health",
        }
    ]


def test_default_inventory_path_is_independent_of_working_directory(monkeypatch):
    monkeypatch.chdir(Path(__file__).parent)

    inventory = load_inventory()

    assert [component["deviceId"] for component in inventory] == [
        "detroit-panel-01",
        "detroit-gateway-01",
        "access-control-server-01",
    ]


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        (None, "inventory file not found"),
        ("not json", "inventory contains malformed JSON"),
        ("{}", "inventory root must be a list"),
        ("[]", "inventory must contain at least one component"),
        ('[{"healthUrl": "http://one"}]', "requires a deviceId"),
        ('[{"deviceId": "panel", "healthUrl": "http://one"}]', "requires a siteId"),
        (
            '[{"deviceId": "panel", "siteId": "detroit", "healthUrl": "http://one"}]',
            "requires a componentType",
        ),
        (
            '[{"deviceId": "panel", "siteId": "detroit", '
            '"componentType": "controller"}]',
            "requires a healthUrl",
        ),
        (
            '[{"deviceId": "panel", "siteId": "detroit", "componentType": "controller", '
            '"healthUrl": "http://one"}, {"deviceId": "panel", "siteId": "detroit", '
            '"componentType": "controller", "healthUrl": "http://two"}]',
            "duplicate deviceId: panel",
        ),
    ],
)
def test_invalid_inventory_is_rejected(monkeypatch, contents, message):
    if contents is None:
        def read_text(*args, **kwargs):
            raise FileNotFoundError
    else:
        def read_text(*args, **kwargs):
            return contents

    monkeypatch.setattr(Path, "read_text", read_text)

    with pytest.raises(InventoryError, match=message):
        load_inventory(Path("inventory.json"))


def test_main_uses_the_loaded_inventory(monkeypatch):
    loaded_inventory = [
        {
            "deviceId": "detroit-panel-01",
            "siteId": "detroit",
            "componentType": "controller",
            "healthUrl": "http://simulator.test/health",
        }
    ]
    observed = {}

    def capture_run(once, interval, inventory):
        observed["once"] = once
        observed["inventory"] = inventory

    monkeypatch.setattr("src.collector.main.load_inventory", lambda path: loaded_inventory)
    monkeypatch.setattr("src.collector.main.run_collector", capture_run)

    assert collector_main(["--once"]) == 0
    assert observed == {
        "once": True,
        "inventory": loaded_inventory,
    }


def test_online_response_is_normalized(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("online"))

    record = collect_component(COMPONENT)

    assert record["deviceId"] == "detroit-panel-01"
    assert record["siteId"] == "detroit"
    assert record["componentType"] == "controller"
    assert record["status"] == "online"
    assert record["failureReason"] is None
    assert isinstance(record["latencyMs"], float)


def test_application_reported_offline_is_preserved(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("offline"))

    record = collect_component(COMPONENT)

    assert record["status"] == "offline"
    assert record["failureReason"] is None


def test_connection_failure_is_normalized(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("src.collector.main.httpx.get", raise_connection_error)

    record = collect_component(COMPONENT)

    assert record["status"] == "unknown"
    assert record["failureReason"] == "connectionFailure"
    assert record["siteId"] == "detroit"
    assert record["componentType"] == "controller"


def test_once_mode_polls_once_and_exits():
    output = []
    calls = []

    def collect(component):
        calls.append(component)
        return {"deviceId": component["deviceId"], "status": "online"}

    run_collector(True, 5.0, [COMPONENT], collect, output.append)

    assert calls == [COMPONENT]
    assert len(output) == 1


def test_unchanged_status_does_not_emit_a_transition():
    output = []
    previous_statuses = {"detroit-panel-01": "online"}

    run_pass(
        previous_statuses,
        [COMPONENT],
        lambda component: {"deviceId": component["deviceId"], "status": "online"},
        output.append,
    )

    assert len(output) == 1
    assert json.loads(output[0])["status"] == "online"


@pytest.mark.parametrize(
    ("previous_status", "current_status", "expected_transition"),
    [
        ("online", "offline", "statusChanged"),
        ("offline", "online", "recovered"),
        ("online", "degraded", "statusChanged"),
    ],
)
def test_status_changes_emit_transition_records(
    previous_status, current_status, expected_transition
):
    output = []
    previous_statuses = {"detroit-panel-01": previous_status}

    run_pass(
        previous_statuses,
        [COMPONENT],
        lambda component: {"deviceId": component["deviceId"], "status": current_status},
        output.append,
    )

    transition = json.loads(output[1])
    assert transition["previousStatus"] == previous_status
    assert transition["currentStatus"] == current_status
    assert transition["transition"] == expected_transition
    assert previous_statuses["detroit-panel-01"] == current_status


def test_invalid_interval_is_rejected():
    with pytest.raises(SystemExit):
        parse_arguments(["--interval", "0"])


def test_continuous_mode_stops_cleanly_on_keyboard_interrupt():
    output = []

    def interrupt_sleep(interval):
        raise KeyboardInterrupt

    run_collector(
        False,
        5.0,
        [COMPONENT],
        lambda component: {"deviceId": component["deviceId"], "status": "online"},
        output.append,
        interrupt_sleep,
    )

    assert output[-1] == "Collector stopped."
