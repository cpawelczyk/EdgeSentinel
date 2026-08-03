# Edge Sentinel Design

## How Edge Sentinel Works

Edge Sentinel observes simulated access-control infrastructure from outside the simulated environment. A simulator exposes the health of sites, gateways, controllers, and shared services. A monitoring collector polls those endpoints, evaluates their health over time, correlates related failures, and sends normalized records to Azure Log Analytics. Azure Monitor queries those records for dashboards, alerts, and notification automation.

```text
Simulator --> Monitoring Collector --> Azure Log Analytics / Azure Monitor
                                              |          |
                                              |          +--> Alert rules --> Action group --> Logic App
                                              +--> KQL queries and Workbook
```

The collector is intentionally independent of the simulator. It must be able to distinguish a component reporting a bad state from the collector being unable to reach that component.

## Design Principles

- **External observation:** Health is assessed by an independent collector, not trusted solely to the simulated application.
- **Explainable incidents:** Every state change includes enough context to support triage.
- **Correlate before notifying:** Prefer one gateway or site incident over many duplicate controller incidents when the evidence shows a shared cause.
- **Configuration over discovery:** V1 reads a version-controlled inventory instead of performing network discovery.
- **Safe automation:** Automation notifies or creates a simulated incident; it does not change real infrastructure.
- **Small and maintainable:** V1 uses simple polling, deterministic fault injection, and structured logs rather than unnecessary distributed services.

## Components and Responsibilities

### Enterprise Infrastructure Simulator

The simulator models three sites: Detroit, Atlanta, and Phoenix. Each site has one gateway and five controllers. Two shared dependencies represent an access-control application service and a video-management service.

It exposes HTTP health/status endpoints, reports application-level state, and supports deterministic fault scenarios such as offline, slow response, intermittent failure, flapping, dependency failure, and site outage. It does not implement physical-access workflows, vendor APIs, or proprietary protocols.

### Monitoring Collector

The collector reads the component inventory and polls each configured endpoint. It measures response time, interprets the response, records connectivity failures, and keeps enough recent state to identify meaningful health changes.

The collector:

- performs HTTP health checks in V1;
- distinguishes connectivity failures from application-reported unhealthy states;
- classifies online, offline, degraded, flapping, recovery, and stale-telemetry states;
- correlates controller failures with gateway or site failures; and
- sends normalized telemetry to Azure.

### Azure Observability and Automation

Azure stores and presents the collector's telemetry. Log Analytics is the central telemetry store; Azure Monitor runs analysis and alerting on that data.

- Azure Workbooks show fleet availability, site health, active incidents, affected components, and latency trends.
- KQL queries support investigation and scheduled-query alert rules.
- Action groups invoke a Logic App for a notification or simulated incident workflow.
- Bicep provisions the Azure resources; GitHub Actions validates and deploys the infrastructure definition.

## Inventory and Polling

The V1 inventory is a version-controlled configuration file that identifies each component, its site, type, and endpoint. The collector polls this inventory on a configurable interval and records the result of each check. This keeps the monitored topology visible and reproducible without adding network discovery.

## Health Classification and Correlation

Health rules describe how the collector interprets patterns over time. Their thresholds are configuration, not fixed architecture:

| Condition | Intended behavior |
| --- | --- |
| Offline | Treat sustained failed checks as an offline state. |
| Recovery | Report when an offline component has returned to a healthy state. |
| Degraded | Identify slow or intermittently failing components before they are considered offline. |
| Flapping | Identify components whose health changes repeatedly in a short period. |
| Site outage | Recognize when failures across a site indicate a wider issue. |
| Shared cause | Prefer a gateway or site incident when multiple impacted controllers share that dependency. |

Network observation and application observation remain separate. For example, an HTTP response that says `offline` is different from a timeout where the collector cannot contact the endpoint. The telemetry preserves this distinction through `status` and `failureReason`.

## Telemetry Schema

The collector emits one structured record per completed check. The initial contract is:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC time the check completed. |
| `deviceId` | Stable identifier for the component. |
| `siteId` | Identifier for its site or facility. |
| `componentType` | Type of component being monitored. |
| `checkType` | Kind of health check performed. |
| `status` | `online`, `offline`, `degraded`, `unknown`, or `recovered`. |
| `latencyMs` | Response duration, if a response was received. |
| `failureReason` | Normalized reason for a failed or unhealthy check. |
| `consecutiveFailures` | Current sequence of failed checks, when applicable. |
| `severity` | Informational, warning, error, or critical. |
| `correlationId` | Identifier shared by related component, gateway, or site events. |
| `collectorId` | Identifier for the collector instance. |

Telemetry must not include credentials, controller configuration, badgeholder data, or other sensitive physical-security information.

## API Contract

Each simulated component exposes an HTTP health endpoint. The exact route is implementation-specific, but its response provides a stable component identity and an application-level status.

Example response:

```json
{
  "deviceId": "detroit-panel-01",
  "siteId": "detroit",
  "componentType": "controller",
  "status": "online"
}
```

HTTP success alone does not mean that a component is healthy. The collector considers the returned `status` and its observation of the request; failed requests become a normalized `failureReason`.

## Azure Implementation Decisions

Azure provides the centralized observability layer. The collector sends structured telemetry to Log Analytics, where Azure Monitor supports queries, dashboards, and alerts. Alert workflows notify operators or create a simulated incident through the existing automation path.

Azure resources are defined with Bicep and deployed through GitHub Actions. Access to Azure follows least-privilege principles, and secrets are kept outside source control. The simulator and collector can run wherever is most practical during development; their responsibilities and telemetry contract do not depend on a particular hosting model.

## Future Enhancements

These are not Version 1 requirements:

- Ping and TCP port checks in addition to HTTP health checks.
- Azure Arc integration.
- Containerized simulator and collector deployments.
- Azure Container Apps or Azure Functions runtimes.
- Event Grid-driven processing.
- ServiceNow Developer Instance integration.
- Simulated camera infrastructure.
- AI-assisted anomaly detection after baseline telemetry exists.
