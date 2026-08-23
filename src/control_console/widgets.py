"""Reusable Qt widgets for the EdgeSentinel control console."""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .models import DeviceState


COLORS = {
    "online": "#48e88b",
    "degraded": "#f6bd45",
    "offline": "#ff5f5f",
    "unreachable": "#ff754b",
    "unknown": "#84909b",
}


def status_color(status: str) -> str:
    return COLORS.get(status, COLORS["unknown"])


class StatusIndicator(QFrame):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        self.light = QLabel()
        self.light.setFixedSize(8, 8)
        self.label = QLabel()
        self.label.setStyleSheet("font-size: 10px; font-weight: 700;")
        layout.addWidget(self.light)
        layout.addWidget(self.label)
        self.set_state("unknown")

    def set_state(self, state: str) -> None:
        color = status_color(state)
        text = "ONLINE" if state == "online" else "OFFLINE" if state == "offline" else "UNKNOWN"
        self.light.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.label.setText(f"{self.name}  {text}")


class DeviceNode(QFrame):
    selected = Signal(str)

    def __init__(self, device_id: str):
        super().__init__()
        self.device_id = device_id
        self.state: DeviceState | None = None
        self.is_selected = False
        self.setFixedSize(104, 58)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(1)
        self.name = QLabel(device_id.replace("-", " ").upper())
        self.name.setWordWrap(True)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setStyleSheet("font-size: 8px; font-weight: 700;")
        self.status = QLabel("UNKNOWN")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("font-size: 9px; font-weight: 700;")
        layout.addWidget(self.name)
        layout.addWidget(self.status)
        self._update_style()

    def set_device_state(self, state: DeviceState) -> None:
        self.state = state
        self.status.setText(state.display_status.upper())
        self._update_style()

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self._update_style()

    def _update_style(self) -> None:
        current = self.state.display_status if self.state else "unknown"
        color = status_color(current)
        selected = "background: #263039;" if self.is_selected else "background: #171c20;"
        self.setStyleSheet(
            f"DeviceNode {{ {selected} border: 1px solid {color}; border-radius: 2px; }}"
            "DeviceNode:hover { background: #222a30; }"
        )
        self.status.setStyleSheet(f"font-size: 9px; font-weight: 700; color: {color};")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.device_id)
        super().mousePressEvent(event)


class SiteTopologyWidget(QFrame):
    node_selected = Signal(str)

    def __init__(self, site_id: str):
        super().__init__()
        self.site_id = site_id
        self.nodes: dict[str, DeviceNode] = {}
        self.gateway_node: DeviceNode | None = None
        self.setMinimumWidth(350)
        self.setStyleSheet("SiteTopologyWidget { background: #11161a; border: 1px solid #303941; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(12)
        title = QLabel(site_id.upper())
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 2px; color: #c8d2d9;")
        layout.addWidget(title)

        self.gateway_container = QHBoxLayout()
        self.gateway_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self.gateway_container)
        self.controllers = QHBoxLayout()
        self.controllers.setSpacing(7)
        self.controllers.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(self.controllers)

    def set_devices(self, devices: tuple[DeviceState, ...]) -> None:
        for device in devices:
            node = self.nodes.get(device.device_id)
            if node is None:
                node = DeviceNode(device.device_id)
                node.selected.connect(self.node_selected)
                self.nodes[device.device_id] = node
                if device.component_type == "gateway":
                    self.gateway_node = node
                    self.gateway_container.addWidget(node)
                else:
                    self.controllers.addWidget(node)
            node.set_device_state(device)
        self.update()

    def set_selected_device(self, device_id: str | None) -> None:
        for node in self.nodes.values():
            node.set_selected(node.device_id == device_id)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.gateway_node is None or self.gateway_node.state is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        start = self.gateway_node.geometry().bottomLeft() + QPoint(self.gateway_node.width() // 2, 0)
        for node in self.nodes.values():
            if node is self.gateway_node or node.state is None:
                continue
            end = node.geometry().topLeft() + QPoint(node.width() // 2, 0)
            pen = QPen(QColor(status_color(node.state.display_status)), 1.2)
            painter.setPen(pen)
            painter.drawLine(start, end)


class InspectorPanel(QFrame):
    action_requested = Signal(str, str)
    site_action_requested = Signal(str, str)

    def __init__(self):
        super().__init__()
        self.device: DeviceState | None = None
        self.setMinimumWidth(235)
        self.setStyleSheet("InspectorPanel { background: #11161a; border: 1px solid #303941; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        title = QLabel("INSPECTOR")
        title.setStyleSheet("font-size: 11px; font-weight: 800; letter-spacing: 2px;")
        layout.addWidget(title)
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout()
        for row, label in enumerate(("DEVICE", "SITE", "TYPE", "STORED", "EFFECTIVE", "DELAY")):
            key = label.lower()
            name = QLabel(label)
            name.setStyleSheet("font-size: 9px; color: #84909b; font-weight: 700;")
            value = QLabel("—")
            value.setWordWrap(True)
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self.values[key] = value
        layout.addLayout(grid)
        layout.addWidget(QLabel("COMPONENT CONTROL"))
        self.component_buttons = []
        for status in ("online", "degraded", "offline"):
            button = QPushButton(f"SET {status.upper()}")
            button.clicked.connect(lambda checked=False, value=status: self._request_component(value))
            layout.addWidget(button)
            self.component_buttons.append(button)
        self.site_label = QLabel("SITE CONTROL")
        layout.addWidget(self.site_label)
        self.site_buttons = []
        for status in ("online", "offline"):
            button = QPushButton(f"SITE {status.upper()}")
            button.clicked.connect(lambda checked=False, value=status: self._request_site(value))
            layout.addWidget(button)
            self.site_buttons.append(button)
        layout.addStretch()
        self.set_device(None)

    def set_device(self, device: DeviceState | None) -> None:
        self.device = device
        values = {
            "device": device.device_id if device else "—",
            "site": device.site_id if device else "—",
            "type": device.component_type if device else "—",
            "stored": device.status.upper() if device else "—",
            "effective": device.effective_status.upper() if device else "—",
            "delay": f"{device.delay_seconds:g}s" if device else "—",
        }
        for key, value in values.items():
            self.values[key].setText(value)
        is_site_device = device is not None and device.site_id != "shared"
        for button in self.component_buttons:
            button.setEnabled(device is not None)
        for button in self.site_buttons:
            button.setEnabled(is_site_device)
        self.site_label.setEnabled(is_site_device)

    def _request_component(self, status: str) -> None:
        if self.device is not None:
            self.action_requested.emit(self.device.device_id, status)

    def _request_site(self, status: str) -> None:
        if self.device is not None and self.device.site_id != "shared":
            self.site_action_requested.emit(self.device.site_id, status)
