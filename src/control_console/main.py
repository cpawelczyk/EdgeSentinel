"""Application entry point for the Edge Sentinel Control Console."""

import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from .api import SimulatorApiError, SimulatorClient
from .models import DeviceState, FleetState, SITE_IDS
from .widgets import DeviceNode, InspectorPanel, MetalPanel, SiteTopologyWidget, StatusIndicator


class WorkerSignals(QObject):
    completed = Signal(object)
    failed = Signal(str)


class ApiWorker(QRunnable):
    """Run one short REST call outside Qt's UI thread."""

    def __init__(self, action):
        super().__init__()
        self.action = action
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            self.signals.completed.emit(self.action())
        except SimulatorApiError as error:
            self.signals.failed.emit(str(error))
        except Exception:
            self.signals.failed.emit("Simulator action failed.")


class MainWindow(QMainWindow):
    REFRESH_INTERVAL_MS = 1500

    def __init__(self, simulator_client: SimulatorClient | None = None):
        super().__init__()
        self.client = simulator_client or SimulatorClient()
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
        self._update_composition()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_fleet_state)
        self.refresh_timer.start(self.REFRESH_INTERVAL_MS)
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
        header.addWidget(self.simulator_indicator)
        header.addWidget(self.collector_indicator)
        header.addWidget(self.azure_indicator)
        header.addStretch()
        reset_button = QPushButton("RESET FLEET")
        reset_button.setFixedHeight(38)
        reset_button.clicked.connect(lambda: self._run_control(self.client.reset_fleet))
        randomize_button = QPushButton("RANDOMIZE")
        randomize_button.setFixedHeight(38)
        randomize_button.clicked.connect(lambda: self._run_control(self.client.randomize_fleet))
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
        self.feedback = QLabel("Connecting to simulator…")
        self.feedback.setStyleSheet("font-family: Consolas; font-size: 10px; color: #a6a7a8;")
        layout.addWidget(self.feedback)

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
        if self.refresh_in_flight:
            return
        self.refresh_in_flight = True
        self._start_worker(self.client.get_fleet_state, self._fleet_state_received, self._fleet_state_failed)

    def _start_worker(self, action, completed, failed) -> None:
        """Keep worker signal objects alive until their background request finishes."""
        worker = ApiWorker(action)
        self.active_workers.add(worker)

        def on_completed(result) -> None:
            self.active_workers.discard(worker)
            completed(result)

        def on_failed(message: str) -> None:
            self.active_workers.discard(worker)
            failed(message)

        worker.signals.completed.connect(on_completed)
        worker.signals.failed.connect(on_failed)
        self.thread_pool.start(worker)

    def _fleet_state_received(self, fleet_state: FleetState) -> None:
        self.refresh_in_flight = False
        self.fleet_state = fleet_state
        self.simulator_indicator.set_state("online")
        self.feedback.setText("Simulator state refreshed.")
        devices_by_site = {site_id: fleet_state.for_site(site_id) for site_id in SITE_IDS}
        for site_id, devices in devices_by_site.items():
            self.site_widgets[site_id].set_devices(devices)
        self._update_shared_nodes(fleet_state.for_site("shared"))
        self._refresh_selection()

    def _fleet_state_failed(self, message: str) -> None:
        self.refresh_in_flight = False
        self.simulator_indicator.set_state("offline")
        self.feedback.setText(message)

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
        self._run_control(lambda: self.client.set_component_status(device_id, status))

    def set_site_status(self, site_id: str, status: str) -> None:
        self._run_control(lambda: self.client.set_site_status(site_id, status))

    def _run_control(self, action) -> None:
        self.feedback.setText("Sending simulator control action…")
        self._start_worker(action, lambda result: self.refresh_fleet_state(), self._control_failed)

    def _control_failed(self, message: str) -> None:
        self.feedback.setText(message)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
