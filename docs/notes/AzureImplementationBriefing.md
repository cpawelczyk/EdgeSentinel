# Edge Sentinel: Azure Implementation Briefing

Use this document as technical context before making Azure-related changes. It describes the implemented local platform and the intended next step. It is not a new roadmap or an invitation to expand scope.

## Project Purpose

Edge Sentinel is a portfolio project that demonstrates cloud observability for simulated, distributed access-control infrastructure. The core story is:

```text
Simulator -> independent Monitoring Collector -> Azure observability and automation
```

The simulator represents infrastructure. The collector observes it from outside and produces useful, normalized operational telemetry. Azure is the centralized destination for that already-trusted telemetry.

## Current Local State

The local simulator and collector are complete enough to begin Azure work. The repository currently has 41 passing automated tests.

### Simulator

- FastAPI application at `src/simulator/main.py`.
- Models three sites: Detroit, Atlanta, and Phoenix.
- Each site has one gateway and five controllers.
- Shared services: `access-control-server-01` and `video-management-server-01`.
- State is intentionally in memory and resets when the simulator restarts.
- Supported application states are `online`, `degraded`, and `offline`.
- Every component shares these existing routes:
  - `GET /components/{device_id}/health`
  - `POST /components/{device_id}/fault`
- Fault requests change application status and may set a deterministic response delay.

Gateway behavior is important: when a site gateway is `offline`, controllers at that site return HTTP 503 to the collector. Their own stored application state is not changed. Gateways and components at other sites remain independently observable.

### Collector

- Entry point: `src/collector/main.py`.
- Inventory: `src/collector/inventory.json`.
- The inventory is version-controlled and contains `deviceId`, `siteId`, `componentType`, and `healthUrl` for each monitored component.
- The collector polls each inventory endpoint once per pass. It supports `--once` and continuous polling; the default interval is five seconds.
- It is synchronous and intentionally has no retries, persistence, database, correlation engine, or cloud dependency.
- It maintains previous status in memory and emits a transition record when a status changes.

The collector does not rely on simulator internals. Inventory context is used even when an endpoint is unreachable, so failed checks still identify the affected site and component type.

## Current Contracts

### Simulator Health Response

```json
{
  "deviceId": "detroit-panel-01",
  "siteId": "detroit",
  "componentType": "controller",
  "status": "online"
}
```

### Normalized Check Record

The collector prints one JSON check record for every completed poll. This is the record Azure ingestion should preserve without changing its field meanings.

```json
{
  "timestamp": "2026-08-03T12:00:00+00:00",
  "deviceId": "detroit-panel-01",
  "siteId": "detroit",
  "componentType": "controller",
  "checkType": "httpHealth",
  "status": "online",
  "latencyMs": 4.2,
  "failureReason": null
}
```

Current classification rules:

| Observation | `status` | `failureReason` |
| --- | --- | --- |
| Successful response reporting `online` below the latency threshold | `online` | `null` |
| Successful response reporting `online` above the latency threshold | `degraded` | `highLatency` |
| Successful response reporting `degraded` | `degraded` | `null` |
| Successful response reporting `offline` | `offline` | `null` |
| Request timeout | `unknown` | `timeout` |
| HTTP error, including a controller blocked by an offline gateway | `unknown` | `httpError` |
| Connection failure | `unknown` | `connectionFailure` |

Latency is measured by the collector. The default local degradation threshold is 2000 milliseconds and can be changed with `--latency-threshold-ms`.

### Status Transition Record

When a component's current status differs from the previous in-memory status, the collector emits a second JSON record:

```json
{
  "eventType": "statusTransition",
  "timestamp": "2026-08-03T12:00:05+00:00",
  "deviceId": "detroit-panel-01",
  "previousStatus": "degraded",
  "currentStatus": "online",
  "transition": "statusChanged"
}
```

A transition from `offline` or `unknown` to `online` is labeled `recovered`. Other changes, including `degraded` to `online`, are labeled `statusChanged`.

## Reproducible Local Demonstration

`src/simulator/run_scenario.py` drives the existing fault API in a fixed sequence:

1. Reset the Phoenix gateway and `phoenix-panel-03` to online with no delay.
2. Set a three-second delay on `phoenix-panel-03`.
3. Clear that delay.
4. Set the Phoenix gateway offline.
5. Restore the gateway online.

This demonstrates high-latency degradation, normal recovery, gateway-path HTTP errors for Phoenix controllers, and restoration. It is deterministic. Randomized fleet behavior remains a future local enhancement and is not part of the Azure work.

## Recommended First Azure Milestone

Implement only this:

> Send the existing normalized collector check records to Azure Log Analytics and verify they are queryable with KQL.

The goal is to prove the end-to-end path while keeping the simulator and collector behavior unchanged. A successful first Azure milestone means a locally run collector can send records with the existing fields, and a KQL query can retrieve and filter them by `deviceId`, `siteId`, `status`, `failureReason`, and `latencyMs`.

Do not combine this milestone with a Workbook, alert rules, Logic Apps, Bicep deployment automation, new hosting, or collector redesign. Those are later layers once ingestion is proven.

## Constraints for Azure Work

- Preserve the existing check-record field names and meanings.
- Keep check records and transition records distinguishable; do not silently discard either type.
- Do not alter the simulator to accommodate Azure.
- Do not add retries, persistence, correlation, flapping logic, rolling latency analysis, or randomized behavior as part of ingestion.
- Do not add Docker, a database, a dashboard application, or production authentication infrastructure.
- Prefer the smallest Azure implementation that is easy to explain and delete when no longer needed.
- Keep credentials and connection details out of source control.
- Azure decisions should support AZ-104 learning and Version 1 completion, not production-system complexity.

## Important Documentation Note

`docs/design/Design.md` contains several aspirational concepts, such as correlation, flapping, stale telemetry, severity, and additional telemetry fields, that are not implemented in the current local platform. Treat this briefing and the source code as the current implementation truth for the first Azure milestone. Do not implement those aspirational concepts unless they are deliberately selected later.

## Useful Starting Points

- Simulator implementation: `src/simulator/main.py`
- Deterministic scenario: `src/simulator/run_scenario.py`
- Collector implementation: `src/collector/main.py`
- Collector inventory: `src/collector/inventory.json`
- Collector instructions: `src/collector/README.md`
- Automated tests: `tests/test_simulator.py`, `tests/test_collector.py`, and `tests/test_scenario.py`
