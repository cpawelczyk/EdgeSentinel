import httpx

from src.collector.main import collect_component


COMPONENT = {
    "deviceId": "detroit-panel-01",
    "siteId": "detroit",
    "componentType": "controller",
    "url": "http://simulator.test/components/detroit-panel-01/health",
}


class FakeResponse:
    def __init__(self, status: str):
        self.status = status

    def raise_for_status(self):
        return None

    def json(self):
        return {"status": self.status}


def test_online_response_is_normalized(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("online"))

    record = collect_component(COMPONENT)

    assert record["deviceId"] == "detroit-panel-01"
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
