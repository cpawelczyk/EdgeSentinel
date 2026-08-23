import json
from pathlib import Path

import httpx
import pytest

from src.collector.main import (
    AZURE_MONITOR_SCOPE,
    AZURE_STREAM_NAME,
    AzureConfigurationError,
    AzureLogExporter,
    InventoryError,
    check_azure_readiness,
    collect_component,
    load_azure_configuration,
    load_inventory,
    main as collector_main,
    parse_arguments,
    resolve_azure_environment,
    run_collector,
    run_pass,
)
from src.simulator.main import components as simulator_components


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


class InvalidJsonResponse:
    def raise_for_status(self):
        return None

    def json(self):
        raise json.JSONDecodeError("Expecting value", "not json", 0)


class PayloadResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeToken:
    token = "test-access-token"


class FakeCredential:
    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes):
        self.scopes.append(scopes)
        return FakeToken()


def azure_configuration():
    return {
        "endpoint": "https://example.ingest.monitor.azure.com/",
        "dcr_immutable_id": "dcr-immutable-id",
    }


def azure_environment():
    return {
        "EDGESENTINEL_DCR_ENDPOINT": azure_configuration()["endpoint"],
        "EDGESENTINEL_DCR_IMMUTABLE_ID": azure_configuration()["dcr_immutable_id"],
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

    assert len(inventory) == 20
    assert {component["deviceId"] for component in inventory} == set(simulator_components)


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

    def capture_run(once, interval, inventory, **kwargs):
        observed["once"] = once
        observed["inventory"] = inventory
        observed["latency_threshold_ms"] = kwargs["latency_threshold_ms"]

    monkeypatch.setattr("src.collector.main.load_inventory", lambda path: loaded_inventory)
    monkeypatch.setattr("src.collector.main.run_collector", capture_run)

    assert collector_main(["--once"]) == 0
    assert observed == {
        "once": True,
        "inventory": loaded_inventory,
        "latency_threshold_ms": 2000.0,
    }


def test_local_only_mode_does_not_require_or_create_azure_export(monkeypatch):
    loaded_inventory = [COMPONENT]
    observed = {}

    monkeypatch.setattr("src.collector.main.load_inventory", lambda path: loaded_inventory)
    monkeypatch.setattr(
        "src.collector.main.run_collector",
        lambda *args, **kwargs: observed.update(kwargs),
    )
    monkeypatch.setattr(
        "src.collector.main.AzureLogExporter",
        lambda configuration: pytest.fail("Azure exporter should not be created"),
    )

    assert collector_main(["--once"]) == 0
    assert observed == {"latency_threshold_ms": 2000.0}


def test_azure_mode_requires_dcr_configuration_values(monkeypatch, capsys):
    for variable in (
        "EDGESENTINEL_DCR_ENDPOINT",
        "EDGESENTINEL_DCR_IMMUTABLE_ID",
    ):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr("src.collector.main.load_local_environment", lambda path: {})

    assert collector_main(["--azure", "--once"]) == 1

    error = capsys.readouterr().err
    assert "EDGESENTINEL_DCR_ENDPOINT" in error
    assert "EDGESENTINEL_DCR_IMMUTABLE_ID" in error


def test_azure_configuration_strips_endpoint_trailing_slash():
    configuration = azure_configuration()

    loaded = load_azure_configuration(
        {
            "EDGESENTINEL_DCR_ENDPOINT": configuration["endpoint"],
            "EDGESENTINEL_DCR_IMMUTABLE_ID": configuration["dcr_immutable_id"],
        }
    )

    assert loaded["endpoint"] == "https://example.ingest.monitor.azure.com"


def test_dotenv_azure_values_are_used_when_process_environment_is_missing(tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "EDGESENTINEL_DCR_ENDPOINT=https://dotenv.ingest.monitor.azure.com\n"
        "EDGESENTINEL_DCR_IMMUTABLE_ID=dcr-dotenv-id\n",
        encoding="utf-8",
    )

    configuration = load_azure_configuration({}, dotenv_path)

    assert configuration == {
        "endpoint": "https://dotenv.ingest.monitor.azure.com",
        "dcr_immutable_id": "dcr-dotenv-id",
    }


def test_process_environment_overrides_dotenv_azure_values(tmp_path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "EDGESENTINEL_DCR_ENDPOINT=https://dotenv.ingest.monitor.azure.com\n"
        "EDGESENTINEL_DCR_IMMUTABLE_ID=dcr-dotenv-id\n",
        encoding="utf-8",
    )
    environment = {
        "EDGESENTINEL_DCR_ENDPOINT": "https://process.ingest.monitor.azure.com",
        "EDGESENTINEL_DCR_IMMUTABLE_ID": "dcr-process-id",
    }

    resolved = resolve_azure_environment(environment, dotenv_path)

    assert resolved["EDGESENTINEL_DCR_ENDPOINT"] == environment["EDGESENTINEL_DCR_ENDPOINT"]
    assert resolved["EDGESENTINEL_DCR_IMMUTABLE_ID"] == environment["EDGESENTINEL_DCR_IMMUTABLE_ID"]


def test_missing_azure_configuration_keeps_the_existing_clear_error(tmp_path):
    with pytest.raises(AzureConfigurationError, match="missing required Azure environment variables"):
        load_azure_configuration({}, tmp_path / ".env")


def test_azure_readiness_reports_missing_configuration(tmp_path):
    with pytest.raises(AzureConfigurationError, match="EDGESENTINEL_DCR_ENDPOINT"):
        check_azure_readiness({}, dotenv_path=tmp_path / ".env")


def test_azure_readiness_reports_token_failure():
    class FailingCredential:
        def get_token(self, *scopes):
            raise RuntimeError("token failure")

    with pytest.raises(RuntimeError, match="token failure"):
        check_azure_readiness(azure_environment(), credential_factory=lambda: FailingCredential())


def test_azure_readiness_acquires_azure_monitor_token():
    credential = FakeCredential()

    check_azure_readiness(azure_environment(), credential_factory=lambda: credential)

    assert credential.scopes == [(AZURE_MONITOR_SCOPE,)]


def test_azure_exporter_uses_default_azure_credential(monkeypatch):
    credential = FakeCredential()
    created = []

    def default_credential_factory():
        created.append(True)
        return credential

    monkeypatch.setattr(
        "src.collector.main.DefaultAzureCredential", default_credential_factory
    )

    exporter = AzureLogExporter(azure_configuration())

    assert exporter.credential is credential
    assert created == [True]


def test_azure_export_uses_default_credential_and_expected_ingestion_request(monkeypatch):
    credential = FakeCredential()
    created_with = {}
    sent = {}

    def credential_factory(**kwargs):
        created_with.update(kwargs)
        return credential

    class SuccessfulPostResponse:
        def raise_for_status(self):
            return None

    def post(url, **kwargs):
        sent["url"] = url
        sent.update(kwargs)
        return SuccessfulPostResponse()

    monkeypatch.setattr("src.collector.main.httpx.post", post)
    exporter = AzureLogExporter(azure_configuration(), credential_factory=credential_factory)
    record = {
        "timestamp": "2026-08-03T12:00:00+00:00",
        "deviceId": "detroit-panel-01",
        "siteId": "detroit",
        "componentType": "controller",
        "checkType": "httpHealth",
        "status": "online",
        "latencyMs": 4.2,
        "failureReason": None,
    }

    exporter.send([record])

    assert created_with == {}
    assert credential.scopes == [(AZURE_MONITOR_SCOPE,)]
    assert sent["url"] == (
        "https://example.ingest.monitor.azure.com/dataCollectionRules/dcr-immutable-id/"
        "streams/Custom-EdgeSentinel?api-version=2023-01-01"
    )
    assert sent["headers"]["Authorization"] == "Bearer test-access-token"
    assert sent["headers"]["Content-Type"] == "application/json"
    assert sent["json"] == [record]
    assert AZURE_STREAM_NAME == "Custom-EdgeSentinel"


@pytest.mark.parametrize("failure", ["authentication", "ingestion"])
def test_azure_export_failures_are_non_fatal_and_do_not_expose_secrets(monkeypatch, failure):
    credential = FakeCredential()
    output = []

    if failure == "authentication":
        def get_token(*scopes):
            raise RuntimeError("credential failure")

        credential.get_token = get_token
    else:
        def post(*args, **kwargs):
            raise httpx.ConnectError("connection failure")

        monkeypatch.setattr("src.collector.main.httpx.post", post)

    exporter = AzureLogExporter(azure_configuration(), credential_factory=lambda **kwargs: credential)
    exporter.send([{"deviceId": "detroit-panel-01", "status": "online"}], output.append)

    assert len(output) == 1
    assert "warning" in output[0].lower()
    assert "credential failure" not in output[0]
    assert "connection failure" not in output[0]


def test_successful_response_below_latency_threshold_remains_online(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("online"))
    elapsed = iter([0.0, 0.5])
    monkeypatch.setattr("src.collector.main.time.perf_counter", lambda: next(elapsed))

    record = collect_component(COMPONENT, latency_threshold_ms=1000.0)

    assert record["deviceId"] == "detroit-panel-01"
    assert record["siteId"] == "detroit"
    assert record["componentType"] == "controller"
    assert record["status"] == "online"
    assert record["failureReason"] is None
    assert isinstance(record["latencyMs"], float)


def test_successful_response_above_latency_threshold_becomes_degraded(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("online"))
    elapsed = iter([0.0, 3.0])
    monkeypatch.setattr("src.collector.main.time.perf_counter", lambda: next(elapsed))

    record = collect_component(COMPONENT, latency_threshold_ms=2000.0)

    assert record["status"] == "degraded"
    assert record["latencyMs"] == 3000.0
    assert record["failureReason"] == "highLatency"


def test_application_reported_offline_is_preserved(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("offline"))
    elapsed = iter([0.0, 3.0])
    monkeypatch.setattr("src.collector.main.time.perf_counter", lambda: next(elapsed))

    record = collect_component(COMPONENT, latency_threshold_ms=2000.0)

    assert record["status"] == "offline"
    assert record["failureReason"] is None


def test_application_reported_degraded_is_preserved(monkeypatch):
    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: FakeResponse("degraded"))
    elapsed = iter([0.0, 3.0])
    monkeypatch.setattr("src.collector.main.time.perf_counter", lambda: next(elapsed))

    record = collect_component(COMPONENT, latency_threshold_ms=2000.0)

    assert record["status"] == "degraded"
    assert record["failureReason"] is None


def test_malformed_json_response_is_normalized(monkeypatch):
    monkeypatch.setattr(
        "src.collector.main.httpx.get", lambda *args, **kwargs: InvalidJsonResponse()
    )

    record = collect_component(COMPONENT)

    assert record["status"] == "unknown"
    assert record["failureReason"] == "invalidResponse"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": "unsupported"},
        {"status": 1},
    ],
    ids=["missing-status", "unsupported-status", "non-string-status"],
)
def test_invalid_status_response_is_normalized(monkeypatch, payload):
    monkeypatch.setattr(
        "src.collector.main.httpx.get", lambda *args, **kwargs: PayloadResponse(payload)
    )

    record = collect_component(COMPONENT)

    assert record["status"] == "unknown"
    assert record["failureReason"] == "invalidResponse"


def test_timeout_behavior_is_unchanged(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Timed out")

    monkeypatch.setattr("src.collector.main.httpx.get", raise_timeout)

    record = collect_component(COMPONENT)

    assert record["status"] == "unknown"
    assert record["failureReason"] == "timeout"


def test_connection_failure_is_normalized(monkeypatch):
    def raise_connection_error(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("src.collector.main.httpx.get", raise_connection_error)

    record = collect_component(COMPONENT)

    assert record["status"] == "unknown"
    assert record["failureReason"] == "connectionFailure"
    assert record["siteId"] == "detroit"
    assert record["componentType"] == "controller"


def test_http_error_is_normalized(monkeypatch):
    def raise_http_error(*args, **kwargs):
        request = httpx.Request("GET", COMPONENT["healthUrl"])
        response = httpx.Response(503, request=request)
        raise httpx.HTTPStatusError("Service unavailable", request=request, response=response)

    monkeypatch.setattr("src.collector.main.httpx.get", raise_http_error)

    record = collect_component(COMPONENT)

    assert record["status"] == "unknown"
    assert record["failureReason"] == "httpError"


def test_once_mode_polls_once_and_exits():
    output = []
    calls = []

    def collect(component, latency_threshold_ms):
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
        lambda component, threshold: {"deviceId": component["deviceId"], "status": "online"},
        output.append,
    )

    assert len(output) == 1
    assert json.loads(output[0])["status"] == "online"


def test_azure_export_sends_check_records_but_not_transitions():
    output = []
    exported_records = []

    class Exporter:
        def send(self, records, output):
            exported_records.extend(records)

    run_pass(
        {"detroit-panel-01": "offline"},
        [COMPONENT],
        lambda component, threshold: {"deviceId": component["deviceId"], "status": "online"},
        output.append,
        azure_exporter=Exporter(),
    )

    assert exported_records == [{"deviceId": "detroit-panel-01", "status": "online"}]
    assert json.loads(output[1])["eventType"] == "statusTransition"


def test_collector_heartbeat_records_pass_and_azure_batch_result(tmp_path):
    class Exporter:
        def send(self, records, output):
            assert len(records) == 1
            return True

    status_file = tmp_path / "collector-status.json"
    run_pass(
        {},
        [COMPONENT],
        lambda component, threshold: {"deviceId": component["deviceId"], "status": "online"},
        azure_exporter=Exporter(),
        status_file=status_file,
    )

    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["lastSuccessfulPass"] == status["lastAzureIngestion"]
    assert "lastAzureFailure" not in status


def test_collector_heartbeat_records_azure_batch_failure(tmp_path):
    class Exporter:
        def send(self, records, output):
            return False

    status_file = tmp_path / "collector-status.json"
    run_pass(
        {},
        [COMPONENT],
        lambda component, threshold: {"deviceId": component["deviceId"], "status": "online"},
        azure_exporter=Exporter(),
        status_file=status_file,
    )

    status = json.loads(status_file.read_text(encoding="utf-8"))
    assert status["lastSuccessfulPass"] == status["lastAzureFailure"]
    assert "lastAzureIngestion" not in status


def test_azure_export_batches_a_complete_20_component_pass(monkeypatch):
    credential = FakeCredential()
    requests = []
    inventory = [{**COMPONENT, "deviceId": f"component-{index}"} for index in range(20)]

    class SuccessfulPostResponse:
        def raise_for_status(self):
            return None

    def post(url, **kwargs):
        requests.append((url, kwargs))
        return SuccessfulPostResponse()

    monkeypatch.setattr("src.collector.main.httpx.post", post)
    exporter = AzureLogExporter(
        azure_configuration(), credential_factory=lambda: credential
    )

    run_pass(
        {},
        inventory,
        lambda component, threshold: {
            "deviceId": component["deviceId"],
            "status": "online",
        },
        azure_exporter=exporter,
    )

    assert credential.scopes == [(AZURE_MONITOR_SCOPE,)]
    assert len(requests) == 1
    _, request = requests[0]
    assert request["json"] == [
        {"deviceId": component["deviceId"], "status": "online"}
        for component in inventory
    ]
    assert request["headers"] == {
        "Authorization": "Bearer test-access-token",
        "Content-Type": "application/json",
    }


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
        lambda component, threshold: {"deviceId": component["deviceId"], "status": current_status},
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


def test_latency_threshold_can_be_configured():
    args = parse_arguments(["--latency-threshold-ms", "1500"])

    assert args.latency_threshold_ms == 1500.0


def test_latency_recovery_emits_a_status_transition(monkeypatch):
    responses = iter([FakeResponse("online"), FakeResponse("online")])
    elapsed = iter([0.0, 3.0, 10.0, 10.2])
    output = []
    previous_statuses = {}

    monkeypatch.setattr("src.collector.main.httpx.get", lambda *args, **kwargs: next(responses))
    monkeypatch.setattr("src.collector.main.time.perf_counter", lambda: next(elapsed))

    run_pass(previous_statuses, [COMPONENT], output=output.append, latency_threshold_ms=2000.0)
    run_pass(previous_statuses, [COMPONENT], output=output.append, latency_threshold_ms=2000.0)

    first_record = json.loads(output[0])
    second_record = json.loads(output[1])
    transition = json.loads(output[2])
    assert first_record["status"] == "degraded"
    assert second_record["status"] == "online"
    assert transition["previousStatus"] == "degraded"
    assert transition["currentStatus"] == "online"
    assert transition["transition"] == "statusChanged"


def test_continuous_mode_stops_cleanly_on_keyboard_interrupt():
    output = []

    def interrupt_sleep(interval):
        raise KeyboardInterrupt

    run_collector(
        False,
        5.0,
        [COMPONENT],
        lambda component, threshold: {"deviceId": component["deviceId"], "status": "online"},
        output.append,
        interrupt_sleep,
    )

    assert output[-1] == "Collector stopped."
