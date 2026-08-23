"""Reusable gunmetal Qt widgets for the EdgeSentinel control console."""

from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .models import DeviceState


COLORS = {
    "online": "#54f08b", "degraded": "#ffc44d", "offline": "#ff6262",
    "unreachable": "#ff8352", "unknown": "#84909b",
}
TECH_FONT = "Consolas"
UI_FONT = "Segoe UI"
PANEL_TONES = {
    "panel": ("#242526", "#191a1b", "#101112"),
    "strip": ("#2a2b2c", "#1c1d1e", "#121314"),
    "bay": ("#28292a", "#1a1b1c", "#111213"),
    "inspector": ("#232425", "#171819", "#0f1011"),
    "rack": ("#252627", "#18191a", "#101112"),
}


def status_color(status: str) -> str:
    return COLORS.get(status, COLORS["unknown"])


def status_text_color(status: str) -> str:
    """Keep status text legible without competing with perimeter illumination."""
    return {
        "online": "#a9c7af",
        "degraded": "#d8c18a",
        "offline": "#dfa0a0",
        "unreachable": "#d9aa8e",
    }.get(status, "#aeb6b9")


def device_label(device_id: str, component_type: str | None = None) -> str:
    """Return compact topology text while retaining the full ID in the model."""
    parts = device_id.split("-")
    if component_type == "controller" or "panel" in parts:
        return f"PANEL\n{parts[-1]}"
    if component_type == "gateway" or "gateway" in parts:
        return f"{parts[0].upper()}\nGATEWAY {parts[-1]}"
    if device_id == "access-control-server-01":
        return "ACCESS CONTROL\nSERVER 01"
    if device_id == "video-management-server-01":
        return "VIDEO MANAGEMENT\nSERVER 01"
    return device_id.replace("-", " ").upper()


def node_style(status: str, selected: bool) -> dict[str, str | float]:
    """Expose separate health and selection treatments for testing and painting."""
    return {
        "health_color": status_color(status),
        "selection_color": "#e6edf2" if selected else "",
        "selection_width": 1.3 if selected else 0.0,
    }


def site_health(devices: tuple[DeviceState, ...]) -> tuple[str, str]:
    """Derive site availability without treating one failed panel as a site outage."""
    gateway = next((device for device in devices if device.component_type == "gateway"), None)
    if gateway is None or gateway.display_status in {"offline", "unreachable"}:
        return "offline", "OFFLINE"
    if gateway.display_status != "online":
        return "degraded", "DEGRADED"
    if any(
        device.component_type == "controller" and device.display_status != "online"
        for device in devices
    ):
        return "degraded", "DEGRADED"
    return "online", "HEALTHY"


class MetalPanel(QFrame):
    """A restrained, programmatically-painted gunmetal equipment panel."""

    def __init__(self, radius: float = 9.0, tone: str = "panel"):
        super().__init__()
        self.radius = radius
        self.tone = tone
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self.radius, self.radius)
        top, middle, bottom = PANEL_TONES[self.tone]
        surface = QLinearGradient(0, rect.top(), 0, rect.bottom())
        surface.setColorAt(0, QColor(top))
        surface.setColorAt(0.12, QColor(middle))
        surface.setColorAt(1, QColor(bottom))
        painter.fillPath(path, surface)
        painter.setPen(QPen(QColor("#5b5e60"), 1.0))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(222, 224, 225, 58), 0.7))
        painter.drawLine(rect.left() + self.radius, rect.top() + 1, rect.right() - self.radius, rect.top() + 1)


class StatusIndicator(MetalPanel):
    def __init__(self, name: str):
        super().__init__(6, "strip")
        self.name = name
        self.setFixedHeight(48)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(7)
        self.light = QLabel()
        self.light.setFixedSize(9, 9)
        self.label = QLabel()
        self.label.setStyleSheet(f"font-family: {UI_FONT}; font-size: 10px; font-weight: 600; color: #d8d9da;")
        layout.addWidget(self.light)
        layout.addWidget(self.label)
        self.set_state("unknown")

    def set_state(self, state: str) -> None:
        color = status_color(state)
        text = "ONLINE" if state == "online" else "OFFLINE" if state == "offline" else "UNKNOWN"
        self.light.setStyleSheet(f"background: {color}; border-radius: 4px;")
        self.label.setText(f"{self.name}\n{text}")


class DeviceNode(QFrame):
    selected = Signal(str)

    def __init__(self, device_id: str):
        super().__init__()
        self.device_id = device_id
        self.state: DeviceState | None = None
        self.is_selected = False
        self.is_gateway = "gateway" in device_id
        self.is_shared = device_id in {"access-control-server-01", "video-management-server-01"}
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._set_geometry_for_type()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(1)
        self.name = QLabel(device_label(device_id))
        self.name.setWordWrap(True)
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name.setStyleSheet(f"font-family: {UI_FONT}; font-size: 9px; font-weight: 600; color: #d7d8d9;")
        self.status = QLabel("UNKNOWN")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.name)
        layout.addWidget(self.status)

    def _set_geometry_for_type(self) -> None:
        if self.is_shared:
            self.setFixedSize(178, 74)
        elif self.is_gateway:
            self.setFixedSize(146, 98)
        else:
            self.setFixedSize(76, 84)

    def set_device_state(self, state: DeviceState) -> None:
        self.state = state
        self.is_gateway = state.component_type == "gateway"
        self.is_shared = state.site_id == "shared"
        self._set_geometry_for_type()
        self.name.setText(device_label(self.device_id, state.component_type))
        self.status.setText(state.display_status.upper())
        self.name.setStyleSheet(
            f"font-family: {UI_FONT}; font-size: {'10px' if self.is_gateway else '9px'}; "
            "font-weight: 600; color: #d7d8d9;"
        )
        self.status.setStyleSheet(
            f"font-family: {TECH_FONT}; font-size: 10px; font-weight: 700; "
            f"color: {status_text_color(state.display_status)};"
        )
        self.update()

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        style = node_style(self.state.display_status if self.state else "unknown", self.is_selected)
        rect = self.rect().adjusted(3, 3, -3, -3)
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        shadow = QPainterPath()
        shadow.addRoundedRect(rect.translated(0, 2), 8, 8)
        painter.fillPath(shadow, QColor(0, 0, 0, 105))
        face = QLinearGradient(0, rect.top(), 0, rect.bottom())
        face.setColorAt(0, QColor("#353637"))
        face.setColorAt(0.18, QColor("#242526"))
        face.setColorAt(1, QColor("#151617"))
        painter.fillPath(path, face)
        painter.setPen(QPen(QColor(style["health_color"]), 1.35))
        painter.drawPath(path)
        painter.setPen(QPen(QColor(232, 233, 234, 78), 0.7))
        painter.drawLine(rect.left() + 9, rect.top() + 1, rect.right() - 9, rect.top() + 1)
        if self.is_selected:
            selected_path = QPainterPath()
            selected_path.addRoundedRect(rect.adjusted(-2, -2, 2, 2), 10, 10)
            painter.setPen(QPen(QColor(style["selection_color"]), float(style["selection_width"])))
            painter.drawPath(selected_path)
        for point in ((rect.left() + 7, rect.top() + 7), (rect.right() - 7, rect.bottom() - 7)):
            painter.setPen(QPen(QColor("#77797a"), 1))
            painter.setBrush(QColor("#0c0d0e"))
            painter.drawEllipse(QPointF(*point), 1.8, 1.8)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.device_id)
        super().mousePressEvent(event)


class SiteTopologyWidget(MetalPanel):
    node_selected = Signal(str)

    def __init__(self, site_id: str):
        super().__init__(10, "bay")
        self.site_id = site_id
        self.nodes: dict[str, DeviceNode] = {}
        self.gateway_node: DeviceNode | None = None
        self.pulse_phase = 0.0
        self.setMinimumSize(370, 390)
        self.setMaximumHeight(500)
        self.title = QLabel(site_id.upper(), self)
        self.title.setStyleSheet(
            "background: transparent; font-family: Segoe UI; font-size: 19px; "
            "font-weight: 700; color: #d7e0e5;"
        )
        self.health = QLabel("●  UNKNOWN", self)
        self.health.setStyleSheet(
            f"background: transparent; font-family: {TECH_FONT}; font-size: 10px; "
            f"font-weight: 700; color: {COLORS['unknown']};"
        )
        self.pulse_timer = QTimer(self)
        self.pulse_timer.setInterval(70)
        self.pulse_timer.timeout.connect(self._advance_pulse)
        self.pulse_timer.start()

    def _advance_pulse(self) -> None:
        self.pulse_phase = (self.pulse_phase + 0.022) % 1.0
        self.update()

    def set_devices(self, devices: tuple[DeviceState, ...]) -> None:
        for device in devices:
            node = self.nodes.get(device.device_id)
            if node is None:
                node = DeviceNode(device.device_id)
                node.setParent(self)
                node.selected.connect(self.node_selected)
                self.nodes[device.device_id] = node
                if device.component_type == "gateway":
                    self.gateway_node = node
                # setParent() hides a widget created after this topology is visible.
                # These nodes are positioned manually rather than managed by a layout.
                node.show()
                node.raise_()
            node.set_device_state(device)
        summary, summary_label = site_health(devices)
        self.health.setText(f"●  {summary_label}")
        self.health.setStyleSheet(
            f"background: transparent; font-family: {TECH_FONT}; font-size: 10px; "
            f"font-weight: 700; color: {status_color(summary)};"
        )
        self._position_nodes()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_nodes()

    def _position_nodes(self) -> None:
        self.title.setGeometry(18, 17, 170, 28)
        self.health.setGeometry(self.width() - 116, 24, 98, 18)
        if self.gateway_node is None:
            return
        self.gateway_node.move((self.width() - self.gateway_node.width()) // 2, 75)
        controllers = sorted((node for node in self.nodes.values() if node is not self.gateway_node), key=lambda node: node.device_id)
        if not controllers:
            return
        total = sum(node.width() for node in controllers)
        available = self.width() - 20
        gap = max(3, (available - total) // max(1, len(controllers) - 1))
        total_with_gaps = total + gap * (len(controllers) - 1)
        x = max(10, (self.width() - total_with_gaps) // 2)
        for node in controllers:
            node.move(x, min(275, max(235, self.height() - node.height() - 64)))
            x += node.width() + gap

    def set_selected_device(self, device_id: str | None) -> None:
        for node in self.nodes.values():
            node.set_selected(node.device_id == device_id)

    def _connection_points(self, node: DeviceNode) -> tuple[QPointF, QPointF]:
        assert self.gateway_node is not None
        return (
            QPointF(self.gateway_node.x() + self.gateway_node.width() / 2, self.gateway_node.y() + self.gateway_node.height() - 4),
            QPointF(node.x() + node.width() / 2, node.y() + 4),
        )

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rim = self.rect().adjusted(5, 5, -5, -5)
        painter.setPen(QPen(QColor(212, 214, 215, 34), 0.6))
        painter.drawRoundedRect(rim, 7, 7)
        painter.setPen(QPen(QColor(187, 189, 190, 42), 0.6))
        painter.drawLine(18, 55, self.width() - 18, 55)
        if self.gateway_node is None or self.gateway_node.state is None:
            return
        for node in self.nodes.values():
            if node is self.gateway_node or node.state is None:
                continue
            color = QColor(status_color(node.state.display_status))
            start, end = self._connection_points(node)
            glow = QColor(color)
            glow.setAlpha(42 if node.state.display_status in {"offline", "unreachable"} else 60)
            painter.setPen(QPen(glow, 5.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            painter.setPen(QPen(color, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)
            bloom_center = 0.12 + self.pulse_phase * 0.76
            bloom_radius = 0.10
            bloom = QLinearGradient(start, end)
            transparent = QColor(color)
            transparent.setAlpha(0)
            bright = QColor(color)
            bright.setAlpha(105 if node.state.display_status in {"offline", "unreachable"} else 175)
            bloom.setColorAt(0.0, transparent)
            bloom.setColorAt(max(0.0, bloom_center - bloom_radius), transparent)
            bloom.setColorAt(bloom_center, bright)
            bloom.setColorAt(min(1.0, bloom_center + bloom_radius), transparent)
            bloom.setColorAt(1.0, transparent)
            painter.setPen(QPen(QBrush(bloom), 4.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(start, end)


class InspectorPanel(MetalPanel):
    action_requested = Signal(str, str)
    site_action_requested = Signal(str, str)

    def __init__(self):
        super().__init__(10, "inspector")
        self.device: DeviceState | None = None
        self.setMinimumWidth(256)
        self.setMaximumWidth(282)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 15, 16, 15)
        layout.setSpacing(8)
        self.title = QLabel("INSPECTOR  /  NO SELECTION")
        self.title.setStyleSheet(f"font-family: {UI_FONT}; font-size: 12px; font-weight: 700; color: #e0e0e0;")
        layout.addWidget(self.title)
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        for row, label in enumerate(("DEVICE", "SITE", "TYPE", "STORED", "EFFECTIVE", "DELAY")):
            key = label.lower()
            name = QLabel(label)
            name.setStyleSheet(f"font-family: '{TECH_FONT}'; font-size: 9px; color: #91a0aa; font-weight: 700;")
            value = QLabel("—")
            value.setWordWrap(True)
            value.setStyleSheet(f"font-family: '{TECH_FONT}'; font-size: 10px; color: #e1e8ec;")
            grid.addWidget(name, row, 0)
            grid.addWidget(value, row, 1)
            self.values[key] = value
        layout.addLayout(grid)
        layout.addSpacing(8)
        component_title = QLabel("COMPONENT CONTROL")
        component_title.setStyleSheet(f"font-family: {UI_FONT}; font-size: 10px; font-weight: 700; color: #c7c8c9;")
        layout.addWidget(component_title)
        self.component_buttons = []
        for status in ("online", "degraded", "offline"):
            button = QPushButton(f"SET {status.upper()}")
            button.setProperty("controlStatus", status)
            button.clicked.connect(lambda checked=False, value=status: self._request_component(value))
            layout.addWidget(button)
            self.component_buttons.append(button)
        self.site_label = QLabel("SITE CONTROL")
        self.site_label.setStyleSheet(f"font-family: {UI_FONT}; font-size: 10px; font-weight: 700; color: #c7c8c9;")
        layout.addWidget(self.site_label)
        self.site_buttons = []
        for status in ("online", "offline"):
            button = QPushButton(f"SITE {status.upper()}")
            button.setProperty("controlStatus", status)
            button.clicked.connect(lambda checked=False, value=status: self._request_site(value))
            layout.addWidget(button)
            self.site_buttons.append(button)
        layout.addStretch()
        self.set_device(None)

    def set_device(self, device: DeviceState | None) -> None:
        self.device = device
        self.title.setText(f"INSPECTOR  /  {device.device_id.upper()}" if device else "INSPECTOR  /  NO SELECTION")
        values = {"device": device.device_id if device else "—", "site": device.site_id if device else "—", "type": device.component_type if device else "—", "stored": device.status.upper() if device else "—", "effective": device.effective_status.upper() if device else "—", "delay": f"{device.delay_seconds:g}s" if device else "—"}
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
