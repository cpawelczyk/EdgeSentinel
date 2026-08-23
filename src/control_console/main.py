"""Application entry point for the Edge Sentinel Control Console."""

import sys

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from .api import SimulatorApiError, SimulatorClient
from .models import DeviceState, FleetState, SITE_IDS
from .widgets import DeviceNode, InspectorPanel, SiteTopologyWidget, StatusIndicator


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
        self.refresh_in_flight = False
        self.fleet_state: FleetState | None = None
        self.selected_device_id: str | None = None
        self.site_widgets: dict[str, SiteTopologyWidget] = {}
        self.shared_nodes: dict[str, DeviceNode] = {}

        self.setWindowTitle("Edge Sentinel Control Console")
        self.resize(1320, 780)
        self.setMinimumSize(1000, 620)
        self._build_ui()
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_fleet_state)
        self.refresh_timer.start(self.REFRESH_INTERVAL_MS)
        QTimer.singleShot(0, self.refresh_fleet_state)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setStyleSheet(
            "QWidget { background: #0b0f12; color: #d6dde2; font-family: Segoe UI, sans-serif; }"
            "QPushButton { background: #1a2228; border: 1px solid #46535d; padding: 7px 9px; "
            "font-size: 10px; font-weight: 700; }"
            "QPushButton:hover { background: #273139; border-color: #8da1ad; }"
            "QPushButton:disabled { color: #66727b; border-color: #303941; }"
        )
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("EDGE SENTINEL  /  CONTROL CONSOLE")
        title.setStyleSheet("font-size: 14px; font-weight: 800; letter-spacing: 2px;")
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
        reset_button.clicked.connect(lambda: self._run_control(self.client.reset_fleet))
        randomize_button = QPushButton("RANDOMIZE")
        randomize_button.clicked.connect(lambda: self._run_control(self.client.randomize_fleet))
        header.addWidget(reset_button)
        header.addWidget(randomize_button)
        layout.addLayout(header)

        content = QHBoxLayout()
        topology_area = QVBoxLayout()
        sites = QHBoxLayout()
        sites.setSpacing(12)
        for site_id in SITE_IDS:
            widget = SiteTopologyWidget(site_id)
            widget.node_selected.connect(self.select_device)
            self.site_widgets[site_id] = widget
            sites.addWidget(widget, 1)
        topology_area.addLayout(sites, 1)

        shared_title = QLabel("SHARED SERVICES")
        shared_title.setStyleSheet("font-size: 10px; font-weight: 800; letter-spacing: 2px; color: #84909b;")
        topology_area.addWidget(shared_title)
        self.shared_layout = QHBoxLayout()
        self.shared_layout.setSpacing(10)
        self.shared_layout.addStretch()
        topology_area.addLayout(self.shared_layout)
        content.addLayout(topology_area, 1)

        self.inspector = InspectorPanel()
        self.inspector.action_requested.connect(self.set_component_status)
        self.inspector.site_action_requested.connect(self.set_site_status)
        content.addWidget(self.inspector)
        layout.addLayout(content, 1)
        self.feedback = QLabel("Connecting to simulator…")
        self.feedback.setStyleSheet("font-size: 10px; color: #84909b;")
        layout.addWidget(self.feedback)

    def refresh_fleet_state(self) -> None:
        if self.refresh_in_flight:
            return
        self.refresh_in_flight = True
        worker = ApiWorker(self.client.get_fleet_state)
        worker.signals.completed.connect(self._fleet_state_received)
        worker.signals.failed.connect(self._fleet_state_failed)
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
        worker = ApiWorker(action)
        worker.signals.completed.connect(lambda result: self.refresh_fleet_state())
        worker.signals.failed.connect(self._control_failed)
        self.thread_pool.start(worker)

    def _control_failed(self, message: str) -> None:
        self.feedback.setText(message)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
