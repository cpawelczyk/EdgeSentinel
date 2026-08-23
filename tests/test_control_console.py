from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from src.control_console.api import SimulatorApiError, SimulatorClient
from src.control_console.models import DeviceState, FleetState, visual_status
from src.control_console.widgets import node_style, site_health, status_color
from src.control_console.orchestration import (
    RuntimeOrchestrator,
    azure_runtime_state,
    collector_runtime_state,
    collector_start_blocker,
    is_recent,
)
from src.control_console.main import ApiWorker, MainWindow, emit_worker_signal
from src.control_console.events import EventLog


def component_payload(device_id="detroit-panel-01", status="online", effective_status="online"):
    return {
        "deviceId": device_id,
        "siteId": "detroit",
        "componentType": "controller",
        "status": status,
        "delaySeconds": 0,
        "effectiveStatus": effective_status,
    }


def test_fleet_state_mapping_preserves_stored_and_effective_status():
    fleet = FleetState.from_payload(
        {"components": [component_payload(status="online", effective_status="unreachable")]}
    )

    device = fleet.by_id["detroit-panel-01"]
    assert device.status == "online"
    assert device.effective_status == "unreachable"
    assert device.display_status == "unreachable"


@pytest.mark.parametrize(
    ("status", "effective_status", "expected"),
    [
        ("online", "online", "online"),
        ("degraded", "degraded", "degraded"),
        ("offline", "offline", "offline"),
        ("online", "unreachable", "unreachable"),
    ],
)
def test_status_to_visual_state(status, effective_status, expected):
    assert visual_status(status, effective_status) == expected


def test_selected_node_has_a_separate_treatment_without_losing_health_color():
    selected = node_style("offline", True)
    unselected = node_style("offline", False)

    assert selected["health_color"] == status_color("offline")
    assert unselected["health_color"] == status_color("offline")
    assert selected["selection_color"] == "#e6edf2"
    assert selected["selection_width"] > 0
    assert unselected["selection_width"] == 0


def test_individual_controller_failure_makes_the_site_degraded_not_offline():
    devices = (
        DeviceState("detroit-gateway-01", "detroit", "gateway", "online", 0, "online"),
        DeviceState("detroit-panel-01", "detroit", "controller", "offline", 0, "offline"),
    )

    assert site_health(devices) == ("degraded", "DEGRADED")


def test_gateway_failure_makes_the_site_offline_and_preserves_unreachable_controller_state():
    devices = (
        DeviceState("detroit-gateway-01", "detroit", "gateway", "offline", 0, "offline"),
        DeviceState("detroit-panel-01", "detroit", "controller", "online", 0, "unreachable"),
    )

    assert site_health(devices) == ("offline", "OFFLINE")


def test_invalid_fleet_state_is_rejected():
    with pytest.raises(ValueError, match="invalid fleet state"):
        FleetState.from_payload({"components": "not-a-list"})


def test_simulator_unavailable_is_a_concise_client_error(monkeypatch):
    def request(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("src.control_console.api.httpx.request", request)

    with pytest.raises(SimulatorApiError, match="Simulator request failed"):
        SimulatorClient().get_fleet_state()


def test_component_control_request_is_constructed_correctly(monkeypatch):
    observed = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "offline"}

    def request(method, url, **kwargs):
        observed.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr("src.control_console.api.httpx.request", request)
    SimulatorClient().set_component_status("detroit-panel-01", "offline")

    assert observed == {
        "method": "POST",
        "url": "http://127.0.0.1:8000/components/detroit-panel-01/fault",
        "json": {"status": "offline"},
        "timeout": 3.0,
    }


@pytest.mark.parametrize(
    ("method_name", "expected_path"),
    [
        ("reset_fleet", "/fleet/reset"),
        ("randomize_fleet", "/fleet/randomize"),
    ],
)
def test_global_control_requests_use_correct_endpoints(monkeypatch, method_name, expected_path):
    observed = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {}

    def request(method, url, **kwargs):
        observed.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr("src.control_console.api.httpx.request", request)
    getattr(SimulatorClient(), method_name)()

    assert observed["method"] == "POST"
    assert observed["url"] == f"http://127.0.0.1:8000{expected_path}"
    assert observed["json"] is None


class FakeProcess:
    def __init__(self):
        self.running = True
        self.terminated = False
        self.killed = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout):
        return 0

    def kill(self):
        self.killed = True
        self.running = False


def test_runtime_orchestrator_stops_only_gui_owned_processes(tmp_path):
    created = []

    def create(*args, **kwargs):
        process = FakeProcess()
        created.append(process)
        return process

    orchestrator = RuntimeOrchestrator(tmp_path, process_factory=create)
    external_simulator = FakeProcess()

    orchestrator.stop_simulator()
    assert not external_simulator.terminated

    owned_simulator = orchestrator.start_simulator()
    owned_collector = orchestrator.start_collector()
    orchestrator.shutdown()

    assert owned_simulator.terminated
    assert owned_collector.terminated
    assert len(created) == 2


def test_runtime_orchestrator_uses_collector_heartbeat_for_recent_status(tmp_path):
    orchestrator = RuntimeOrchestrator(tmp_path, process_factory=lambda *args, **kwargs: FakeProcess())
    recent = datetime.now(timezone.utc).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(seconds=9)).isoformat()
    orchestrator.status_file.write_text(
        '{"lastSuccessfulPass": "%s", "lastAzureIngestion": "%s"}' % (recent, stale),
        encoding="utf-8",
    )

    status = orchestrator.collector_status()
    assert is_recent(status["lastSuccessfulPass"])
    assert not is_recent(status["lastAzureIngestion"])


def test_collector_start_requires_simulator_then_azure_readiness():
    assert collector_start_blocker(False, False) == "Start simulator first."
    assert collector_start_blocker(True, False) == "Validate Azure connection first."
    assert collector_start_blocker(True, True) is None


def test_runtime_states_follow_recent_collector_and_azure_heartbeat():
    recent = datetime.now(timezone.utc).isoformat()
    stale = (datetime.now(timezone.utc) - timedelta(seconds=9)).isoformat()

    assert collector_runtime_state({}) == "starting"
    assert collector_runtime_state({"lastSuccessfulPass": stale}) == "stale"
    assert collector_runtime_state({"lastSuccessfulPass": recent}) == "online"
    assert azure_runtime_state({"lastAzureIngestion": recent}) == "connected"
    assert azure_runtime_state({"lastAzureIngestion": stale}) == "stale"
    assert azure_runtime_state({"lastAzureIngestion": recent, "lastAzureFailure": recent}) == "error"


class DeletedSignal:
    def emit(self, value):
        raise RuntimeError("Signal source has been deleted")


def test_in_flight_worker_ignores_deleted_signal_source_during_shutdown():
    worker = ApiWorker(lambda: (_ for _ in ()).throw(SimulatorApiError("offline")))
    worker.signals = SimpleNamespace(completed=DeletedSignal(), failed=DeletedSignal())

    worker.run()


def test_successful_in_flight_worker_also_ignores_deleted_signal_source():
    worker = ApiWorker(lambda: {"components": []})
    worker.signals = SimpleNamespace(completed=DeletedSignal(), failed=DeletedSignal())

    worker.run()


def test_worker_signal_does_not_hide_unrelated_runtime_errors():
    class BrokenSignal:
        def emit(self, value):
            raise RuntimeError("unexpected Qt failure")

    with pytest.raises(RuntimeError, match="unexpected Qt failure"):
        emit_worker_signal(BrokenSignal(), "value")


def test_callbacks_and_worker_start_are_ignored_after_close():
    closing_window = SimpleNamespace(is_closing=True)

    MainWindow._fleet_state_received(closing_window, object())
    MainWindow._fleet_state_failed(closing_window, "Simulator request failed.")
    MainWindow._start_worker(closing_window, lambda: None, lambda _: None, lambda _: None)


def test_shutdown_stops_timers_and_cleans_up_owned_processes_once():
    class Timer:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class Pool:
        def __init__(self):
            self.cleared = False

        def clear(self):
            self.cleared = True

    class Orchestrator:
        def __init__(self):
            self.shutdown_calls = 0

        def shutdown(self):
            self.shutdown_calls += 1

    window = SimpleNamespace(
        is_closing=False,
        refresh_timer=Timer(),
        runtime_timer=Timer(),
        thread_pool=Pool(),
        orchestrator=Orchestrator(),
        event_log=EventLog(),
        event_console=CapturingEventConsole(),
    )
    window._log_event = lambda source, message, severity="normal": MainWindow._log_event(window, source, message, severity)

    MainWindow._begin_shutdown(window)
    MainWindow._begin_shutdown(window)

    assert window.is_closing
    assert window.refresh_timer.stopped and window.runtime_timer.stopped
    assert window.thread_pool.cleared
    assert window.orchestrator.shutdown_calls == 1


class CapturingEventConsole:
    def __init__(self):
        self.entries = []

    def append(self, entry):
        self.entries.append(entry)


class CapturingIndicator:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


def test_event_log_records_startup_and_deduplicates_identical_messages():
    log = EventLog(now=lambda: datetime(2026, 8, 23, 11, 42, 3))

    startup = log.record("SYSTEM", "Control Console started")
    duplicate = log.record("SYSTEM", "Control Console started")

    assert startup.text == "11:42:03  SYSTEM     Control Console started"
    assert duplicate is None
    assert len(log.entries) == 1


def test_status_transition_is_logged_once_without_refresh_spam():
    console = CapturingEventConsole()
    window = SimpleNamespace(
        is_closing=False,
        event_log=EventLog(now=lambda: datetime(2026, 8, 23, 11, 42, 3)),
        event_console=console,
        simulator_state="unknown",
    )
    indicator = CapturingIndicator()
    window._log_event = lambda source, message, severity="normal": MainWindow._log_event(window, source, message, severity)

    MainWindow._set_status(window, "SIMULATOR", "simulator_state", indicator, "online", "Online")
    MainWindow._set_status(window, "SIMULATOR", "simulator_state", indicator, "online", "Online")

    assert indicator.states == ["online", "online"]
    assert [entry.text for entry in console.entries] == ["11:42:03  SIMULATOR  Online"]


def test_successful_and_failed_control_actions_are_logged_accurately():
    console = CapturingEventConsole()
    refreshed = []
    window = SimpleNamespace(
        is_closing=False,
        event_log=EventLog(now=lambda: datetime(2026, 8, 23, 11, 42, 3)),
        event_console=console,
        refresh_fleet_state=lambda: refreshed.append(True),
    )
    window._log_event = lambda source, message, severity="normal": MainWindow._log_event(window, source, message, severity)

    MainWindow._control_succeeded(window, "detroit-panel-03 -> OFFLINE")
    MainWindow._control_failed(window, "Simulator request failed.")

    assert refreshed == [True]
    assert [entry.text for entry in console.entries] == [
        "11:42:03  CONTROL    detroit-panel-03 -> OFFLINE",
        "11:42:03  CONTROL    Simulator request failed.",
    ]
    assert console.entries[-1].severity == "error"


def test_event_log_does_not_touch_the_widget_after_shutdown_begins():
    console = CapturingEventConsole()
    window = SimpleNamespace(is_closing=True, event_log=EventLog(), event_console=console)

    MainWindow._log_event(window, "SIMULATOR", "Offline", "error")

    assert console.entries == []


def test_fresh_console_state_does_not_start_fleet_polling_until_simulator_engagement():
    window = SimpleNamespace(is_closing=False, simulator_engaged=False, refresh_in_flight=False)

    MainWindow.refresh_fleet_state(window)

    assert not hasattr(window, "_start_worker")


def test_simulator_startup_failures_remain_starting_until_owned_process_is_ready():
    state_changes = []
    owned_process = object()
    orchestrator = SimpleNamespace(
        simulator_process=owned_process,
        is_running=lambda process: process is owned_process,
    )
    window = SimpleNamespace(
        is_closing=False,
        refresh_in_flight=True,
        simulator_state="starting",
        simulator_indicator=object(),
        orchestrator=orchestrator,
        _set_status=lambda *args: state_changes.append(args),
        _refresh_runtime_status=lambda: None,
    )

    MainWindow._fleet_state_failed(window, "Simulator request failed.")
    assert state_changes == []

    orchestrator.is_running = lambda process: False
    MainWindow._fleet_state_failed(window, "Simulator request failed.")
    assert state_changes[0][-2:] == ("offline", "Simulator request failed.")


def test_azure_connected_click_transitions_to_logical_disconnected():
    transitions = []
    window = SimpleNamespace(
        azure_state="connected",
        azure_indicator=object(),
        orchestrator=SimpleNamespace(collector_process=None, is_running=lambda process: False),
        _set_status=lambda *args: transitions.append(args),
    )

    MainWindow.check_azure(window)

    assert transitions[0][-2:] == ("disconnected", "Disconnected")


def test_azure_disconnected_click_rechecks_readiness():
    transitions = []
    workers = []
    window = SimpleNamespace(
        azure_state="disconnected",
        azure_indicator=object(),
        _set_status=lambda *args: transitions.append(args),
        _start_worker=lambda *args: workers.append(args),
        _azure_readiness=lambda: None,
        _azure_readiness_received=lambda result: None,
        _azure_readiness_failed=lambda message: None,
    )

    MainWindow.check_azure(window)

    assert transitions[0][-2:] == ("checking", "Checking readiness")
    assert len(workers) == 1


def test_azure_disconnect_is_refused_while_collector_is_running():
    events = []
    window = SimpleNamespace(
        azure_state="connected",
        azure_indicator=object(),
        orchestrator=SimpleNamespace(collector_process=object(), is_running=lambda process: True),
        _log_event=lambda *args: events.append(args),
    )

    MainWindow.check_azure(window)

    assert events == [("AZURE", "Cannot disconnect while collector is running", "error")]


def test_startup_event_has_no_initial_simulator_failure_noise():
    log = EventLog(now=lambda: datetime(2026, 8, 23, 11, 42, 3))
    log.record("SYSTEM", "Control Console started")

    assert [entry.message for entry in log.entries] == ["Control Console started"]
