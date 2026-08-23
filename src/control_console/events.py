"""Compact in-memory operational events for the control console."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EventEntry:
    timestamp: str
    source: str
    message: str
    severity: str = "normal"

    @property
    def text(self) -> str:
        return f"{self.timestamp}  {self.source:<10} {self.message}"


class EventLog:
    """Format and de-duplicate the small set of operator-meaningful events."""

    def __init__(self, now=None, limit: int = 200):
        self.now = now or datetime.now
        self.limit = limit
        self.entries: list[EventEntry] = []
        self._last_key = None

    def record(self, source: str, message: str, severity: str = "normal") -> EventEntry | None:
        key = (source, message, severity)
        if key == self._last_key:
            return None
        entry = EventEntry(self.now().strftime("%H:%M:%S"), source, message, severity)
        self.entries.append(entry)
        del self.entries[:-self.limit]
        self._last_key = key
        return entry
