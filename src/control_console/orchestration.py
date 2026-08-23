"""Local child-process and heartbeat helpers for the control console."""

import json
import subprocess
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path


HEARTBEAT_STALE_SECONDS = 8.0


def _creation_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def is_recent(timestamp: str | None, now: datetime | None = None) -> bool:
    """Return whether an ISO timestamp is within the heartbeat window."""
    if not timestamp:
        return False
    try:
        observed_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    current_time = now or datetime.now(timezone.utc)
    return (current_time - observed_at).total_seconds() <= HEARTBEAT_STALE_SECONDS


def collector_start_blocker(simulator_known: bool, azure_connected: bool) -> str | None:
    if not simulator_known:
        return "Start simulator first."
    if not azure_connected:
        return "Validate Azure connection first."
    return None


def collector_runtime_state(status: dict) -> str:
    if is_recent(status.get("lastSuccessfulPass")):
        return "online"
    if status.get("lastSuccessfulPass"):
        return "stale"
    return "starting"


def azure_runtime_state(status: dict) -> str | None:
    if is_recent(status.get("lastAzureFailure")):
        return "error"
    if is_recent(status.get("lastAzureIngestion")):
        return "connected"
    if status.get("lastAzureIngestion"):
        return "stale"
    return None


class RuntimeOrchestrator:
    """Own only the simulator and collector child processes launched by this GUI."""

    def __init__(self, project_root: Path, process_factory=subprocess.Popen):
        self.project_root = project_root
        self.process_factory = process_factory
        self.simulator_process = None
        self.collector_process = None
        self.status_file = Path(tempfile.gettempdir()) / f"edge-sentinel-collector-{id(self)}.json"

    @staticmethod
    def is_running(process) -> bool:
        return process is not None and process.poll() is None

    def start_simulator(self):
        if self.is_running(self.simulator_process):
            return self.simulator_process
        self.simulator_process = self.process_factory(
            [sys.executable, "-m", "uvicorn", "src.simulator.main:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=self.project_root,
            creationflags=_creation_flags(),
        )
        return self.simulator_process

    def start_collector(self):
        if self.is_running(self.collector_process):
            return self.collector_process
        self.status_file.unlink(missing_ok=True)
        self.collector_process = self.process_factory(
            [sys.executable, "-m", "src.collector.main", "--azure", "--interval", "2", "--status-file", str(self.status_file)],
            cwd=self.project_root,
            creationflags=_creation_flags(),
        )
        return self.collector_process

    def collector_status(self) -> dict:
        try:
            status = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return status if isinstance(status, dict) else {}

    def stop_simulator(self) -> None:
        self._stop("simulator_process")

    def stop_collector(self) -> None:
        self._stop("collector_process")
        self.status_file.unlink(missing_ok=True)

    def shutdown(self) -> None:
        self.stop_collector()
        self.stop_simulator()

    def _stop(self, attribute: str) -> None:
        process = getattr(self, attribute)
        if not self.is_running(process):
            setattr(self, attribute, None)
            return
        process.terminate()
        threading.Thread(target=self._reap, args=(process,), daemon=True).start()
        setattr(self, attribute, None)

    @staticmethod
    def _reap(process) -> None:
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
