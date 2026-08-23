"""Application entry point for the Edge Sentinel Control Console."""

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from .api import SimulatorApiError, SimulatorClient
from .events import EventLog
from .models import DeviceState, FleetState, SITE_IDS
from .orchestration import (
    RuntimeOrchestrator,
    azure_runtime_state,
    collector_runtime_state,
    collector_start_blocker,
)
from .widgets import DeviceNode, EventConsole, InspectorPanel, MetalPanel, SiteTopologyWidget, StatusIndicator
from src.collector.main import AzureConfigurationError, check_azure_readiness


class WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


def emit_worker_signal(signal, value) -> None:
    """Ignore only Qt's expected deleted-signal race during application teardown."""
    try:
        signal.emit(value)
    except RuntimeError as error:
        if "Signal source has been deleted" not in str(error):
            raise


class ApiWorker(QRunnable):
    """Run one short REST call outside Qt's UI thread."""

    def __init__(self, action):
        super().__init__()
        self.action = action
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            result = self.action()
        except SimulatorApiError as error:
            emit_worker_signal(self.signals.failed, str(error))
        except Exception:
            emit_worker_signal(self.signals.failed, "Simulator action failed.")
        else:
            emit_worker_signal(self.signals.completed, result)


class MainWindow(QMainWindow):
    REFRESH_INTERVAL_MS = 1500

    def __init__(self, simulator_client: SimulatorClient | None = None, orchestrator=None):
        super().__init__()
        self.client = simulator_client or SimulatorClient()
        self.orchestrator = orchestrator or RuntimeOrchestrator(Path(__file__).resolve().parents[2])
        self.azure_state = "unknown"
        self.simulator_state = "unknown"
        self.collector_state = "unknown"
        self.azure_batch_seen = False
        self.last_azure_batch_timestamp = None
        self.is_closing = False
        self.event_log = EventLog()
        self.thread_pool = QThreadPool.globalInstance()
        self.active_workers = set()
        self.refresh_in_flight = False
        self.fleet_state: FleetState | None = None
        self.selected_device_id: str | None = None
        self.site_widgets: dict[str, SiteTopologyWidget] = {}
        self.shared_nodes: dict[str, DeviceNode] = {}

        self.setWindowTitle("Edge Sentinel Control Console")
        self.setMinimumSize(1320, 650)
        available = self.screen().availableGeometry()
        self.resize(
            min(1540, max(self.minimumWidth(), int(available.width() * 0.88))),
            min(780, max(self.minimumHeight(), int(available.height() * 0.72))),
        )
        self._build_ui()
        self._log_event("SYSTEM", "Control Console started")
        self._update_composition()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_fleet_state)
        self.refresh_timer.start(self.REFRESH_INTERVAL_MS)
        self.runtime_timer = QTimer(self)
        self.runtime_timer.timeout.connect(self._refresh_runtime_status)
        self.runtime_timer.start(self.REFRESH_INTERVAL_MS)
        QTimer.singleShot(0, self.refresh_fleet_state)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("consoleRoot")
        root.setStyleSheet(
            "QWidget#consoleRoot { background: #0d0e0f; color: #d8d8d8; font-family: Segoe UI, sans-serif; }"
            "QLabel { background: transparent; }"
            "QPushButton { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #323334, stop:0.45 #202122, stop:1 #151617); "
            "border: 1px solid #5c5e60; border-radius: 5px; padding: 7px 10px; font-family: Segoe UI; font-size: 10px; font-weight: 600; }"
            "QPushButton:hover { border-color: #d0d1d2; background: #353637; }"
            "QPushButton:pressed { background: #141516; padding-top: 8px; padding-bottom: 6px; }"
            "QPushButton:disabled { color: #777879; border-color: #3c3d3e; background: #18191a; }"
            "QPushButton[controlStatus='online'] { color: #b5d2bb; }"
            "QPushButton[controlStatus='degraded'] { color: #d8c18a; }"
            "QPushButton[controlStatus='offline'] { color: #dfa0a0; }"
        )
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header_panel = MetalPanel(10, "strip")
        header = QHBoxLayout(header_panel)
        header.setContentsMargins(18, 10, 14, 10)
        header.setSpacing(8)
        title = QLabel("EDGE SENTINEL  /  CONTROL CONSOLE")
        title.setStyleSheet("font-family: Segoe UI; font-size: 16px; font-weight: 700; letter-spacing: 1px; color: #e2e2e2;")
        header.addWidget(title)
        header.addSpacing(20)
        self.simulator_indicator = StatusIndicator("SIMULATOR")
        self.collector_indicator = StatusIndicator("COLLECTOR")
        self.azure_indicator = StatusIndicator("AZURE")
        self.simulator_indicator.clicked.connect(self.toggle_simulator)
        self.collector_indicator.clicked.connect(self.toggle_collector)
        self.azure_indicator.clicked.connect(self.check_azure)
        header.addWidget(self.simulator_indicator)
        header.addWidget(self.collector_indicator)
        header.addWidget(self.azure_indicator)
        header.addStretch()
        reset_button = QPushButton("RESET FLEET")
        reset_button.setFixedHeight(38)
        reset_button.clicked.connect(lambda: self._run_control(self.client.reset_fleet, "Fleet reset"))
        randomize_button = QPushButton("RANDOMIZE")
        randomize_button.setFixedHeight(38)
        randomize_button.clicked.connect(lambda: self._run_control(self.client.randomize_fleet, "Fleet randomized"))
        header.addWidget(reset_button)
        header.addWidget(randomize_button)
        layout.addWidget(header_panel)

        self.composition_spacer = QWidget()
        self.composition_spacer.setFixedHeight(0)
        layout.addWidget(self.composition_spacer)

        content = QHBoxLayout()
        topology_area = QVBoxLayout()
        sites = QHBoxLayout()
        sites.setSpacing(12)
        for site_id in SITE_IDS:
            widget = SiteTopologyWidget(site_id)
            widget.node_selected.connect(self.select_device)
            self.site_widgets[site_id] = widget
            sites.addWidget(widget, 1, Qt.AlignmentFlag.AlignTop)
        topology_area.addLayout(sites)

        shared_panel = MetalPanel(10, "rack")
        shared_box = QVBoxLayout(shared_panel)
        shared_box.setContentsMargins(14, 10, 14, 10)
        shared_box.setSpacing(8)
        shared_title = QLabel("SHARED INFRASTRUCTURE")
        shared_title.setStyleSheet("font-family: Segoe UI; font-size: 10px; font-weight: 700; letter-spacing: 1px; color: #c9c9c9;")
        shared_box.addWidget(shared_title)
        self.shared_layout = QHBoxLayout()
        self.shared_layout.setSpacing(10)
        self.shared_layout.addStretch()
        shared_box.addLayout(self.shared_layout)
        topology_area.addWidget(shared_panel)
        topology_area.addStretch()
        content.addLayout(topology_area, 1)

        self.inspector = InspectorPanel()
        self.inspector.action_requested.connect(self.set_component_status)
        self.inspector.site_action_requested.connect(self.set_site_status)
        content.addWidget(self.inspector)
        layout.addLayout(content)
        layout.addStretch()
        self.event_console = EventConsole()
        layout.addWidget(self.event_console)

    def _log_event(self, source: str, message: str, severity: str = "normal") -> None:
        if self.is_closing:
            return
        entry = self.event_log.record(source, message, severity)
        if entry is not None:
            self.event_console.append(entry)

    def _set_status(self, source: str, attribute: str, indicator, state: str, message: str | None = None) -> None:
        previous = getattr(self, attribute)
        indicator.set_state(state)
        setattr(self, attribute, state)
        if previous != state:
            label = message or state.upper()
            severity = "error" if state == "error" else "normal"
            self._log_event(source, label, severity)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_composition()

    def _update_composition(self) -> None:
        if not self.site_widgets:
            return
        extra_height = max(0, self.height() - 850)
        topology_height = 390 + min(100, int(extra_height * 0.4))
        composition_gap = min(52, int(extra_height * 0.22))
        self.composition_spacer.setFixedHeight(composition_gap)
        for widget in self.site_widgets.values():
            widget.setFixedHeight(topology_height)

    def refresh_fleet_state(self) -> None:
        if self.is_closing or self.refresh_in_flight:
            return
        self.refresh_in_flight = True
        self._start_worker(self.client.get_fleet_state, self._fleet_state_received, self._fleet_state_failed)

    def _start_worker(self, action, completed, failed) -> None:
        """Keep worker signal objects alive until their background request finishes."""
        if self.is_closing:
            return
        worker = ApiWorker(action)
        self.active_workers.add(worker)

        def on_completed(result) -> None:
            self.active_workers.discard(worker)
            if self.is_closing:
                return
            completed(result)

        def on_failed(message: str) -> None:
            self.active_workers.discard(worker)
            if self.is_closing:
                return
            failed(message)

        worker.signals.completed.connect(on_completed)
        worker.signals.failed.connect(on_failed)
        self.thread_pool.start(worker)

    def _fleet_state_received(self, fleet_state: FleetState) -> None:
        if self.is_closing:
            return
        self.refresh_in_flight = False
        self.fleet_state = fleet_state
        self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "online", "Online")
        devices_by_site = {site_id: fleet_state.for_site(site_id) for site_id in SITE_IDS}
        for site_id, devices in devices_by_site.items():
            self.site_widgets[site_id].set_devices(devices)
        self._update_shared_nodes(fleet_state.for_site("shared"))
        self._refresh_selection()
        self._refresh_runtime_status()

    def _fleet_state_failed(self, message: str) -> None:
        if self.is_closing:
            return
        self.refresh_in_flight = False
        self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "offline", message)
        self._refresh_runtime_status()

    def toggle_simulator(self) -> None:
        if self.orchestrator.is_running(self.orchestrator.simulator_process):
            self.orchestrator.stop_simulator()
            self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "offline", "Stopped")
            return
        self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "starting", "Starting")
        self._start_worker(
            self.client.get_fleet_state,
            lambda _: self._external_simulator_detected(),
            lambda _: self._start_simulator(),
        )

    def _external_simulator_detected(self) -> None:
        self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "online", "Online (external)")

    def _start_simulator(self) -> None:
        try:
            self.orchestrator.start_simulator()
        except OSError:
            self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "error", "Unable to start")
            return
        self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "starting", "Starting")

    def check_azure(self) -> None:
        self._set_status("AZURE", "azure_state", self.azure_indicator, "checking", "Checking readiness")
        self._start_worker(self._azure_readiness, self._azure_readiness_received, self._azure_readiness_failed)

    @staticmethod
    def _azure_readiness() -> tuple[bool, str]:
        try:
            check_azure_readiness()
        except AzureConfigurationError as error:
            return False, str(error)
        except Exception:
            return False, "Azure authentication failed."
        return True, "Azure connection validated."

    def _azure_readiness_received(self, result: tuple[bool, str]) -> None:
        success, message = result
        self._set_status("AZURE", "azure_state", self.azure_indicator, "connected" if success else "error", message)

    def _azure_readiness_failed(self, message: str) -> None:
        self._set_status("AZURE", "azure_state", self.azure_indicator, "error", message)

    def toggle_collector(self) -> None:
        if self.orchestrator.is_running(self.orchestrator.collector_process):
            self.orchestrator.stop_collector()
            self._set_status("COLLECTOR", "collector_state", self.collector_indicator, "offline", "Stopped")
            return
        blocker = collector_start_blocker(self.fleet_state is not None, self.azure_state == "connected")
        if blocker is not None:
            self._log_event("CONTROL", blocker, "error")
            return
        self._start_worker(
            self.client.get_fleet_state,
            lambda _: self._collector_simulator_ready(),
            self._collector_simulator_unavailable,
        )

    def _collector_simulator_unavailable(self, _message: str) -> None:
        self._log_event("CONTROL", "Start simulator first.", "error")

    def _collector_simulator_ready(self) -> None:
        self._start_collector()

    def _start_collector(self) -> None:
        try:
            self.orchestrator.start_collector()
        except OSError:
            self._set_status("COLLECTOR", "collector_state", self.collector_indicator, "error", "Unable to start")
            return
        self._set_status("COLLECTOR", "collector_state", self.collector_indicator, "starting", "Starting")

    def _refresh_runtime_status(self) -> None:
        simulator = self.orchestrator.simulator_process
        if simulator is not None and not self.orchestrator.is_running(simulator):
            self._set_status("SIMULATOR", "simulator_state", self.simulator_indicator, "error", "Stopped unexpectedly")

        collector = self.orchestrator.collector_process
        if collector is None:
            return
        if not self.orchestrator.is_running(collector):
            self._set_status("COLLECTOR", "collector_state", self.collector_indicator, "error", "Stopped unexpectedly")
            return
        status = self.orchestrator.collector_status()
        self._set_status("COLLECTOR", "collector_state", self.collector_indicator, collector_runtime_state(status))
        azure_state = azure_runtime_state(status)
        if azure_state is not None:
            previous_azure_state = self.azure_state
            message = "Telemetry batch accepted" if azure_state == "connected" else "Telemetry batch failed" if azure_state == "error" else None
            self._set_status("AZURE", "azure_state", self.azure_indicator, azure_state, message)
            if azure_state == "connected":
                timestamp = status.get("lastAzureIngestion")
                if timestamp != self.last_azure_batch_timestamp:
                    if not self.azure_batch_seen and previous_azure_state == "connected":
                        self._log_event("AZURE", "Telemetry batch accepted")
                    self.azure_batch_seen = True
                    self.last_azure_batch_timestamp = timestamp
            elif azure_state == "error":
                self.azure_batch_seen = False

    def _begin_shutdown(self) -> None:
        if self.is_closing:
            return
        self._log_event("SYSTEM", "Control Console shutting down")
        self.is_closing = True
        self.refresh_timer.stop()
        self.runtime_timer.stop()
        self.thread_pool.clear()
        self.orchestrator.shutdown()

    def closeEvent(self, event) -> None:
        self._begin_shutdown()
        super().closeEvent(event)

    def _update_shared_nodes(self, devices: tuple[DeviceState, ...]) -> None:
        for device in devices:
            node = self.shared_nodes.get(device.device_id)
            if node is None:
                node = DeviceNode(device.device_id)
                node.selected.connect(self.select_device)
                self.shared_nodes[device.device_id] = node
                self.shared_layout.insertWidget(self.shared_layout.count() - 1, node)
            node.set_device_state(device)

    def select_device(self, device_id: str) -> None:
        self.selected_device_id = device_id
        self._refresh_selection()

    def _refresh_selection(self) -> None:
        devices = self.fleet_state.by_id if self.fleet_state else {}
        self.inspector.set_device(devices.get(self.selected_device_id))
        for widget in self.site_widgets.values():
            widget.set_selected_device(self.selected_device_id)
        for node in self.shared_nodes.values():
            node.set_selected(node.device_id == self.selected_device_id)

    def set_component_status(self, device_id: str, status: str) -> None:
        self._run_control(lambda: self.client.set_component_status(device_id, status), f"{device_id} -> {status.upper()}")

    def set_site_status(self, site_id: str, status: str) -> None:
        self._run_control(lambda: self.client.set_site_status(site_id, status), f"{site_id} site -> {status.upper()}")

    def _run_control(self, action, success_message: str) -> None:
        self._start_worker(action, lambda result: self._control_succeeded(success_message), self._control_failed)

    def _control_succeeded(self, message: str) -> None:
        self._log_event("CONTROL", message)
        self.refresh_fleet_state()

    def _control_failed(self, message: str) -> None:
        self._log_event("CONTROL", message, "error")


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
