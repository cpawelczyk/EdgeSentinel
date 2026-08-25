# Edge Sentinel Technical Design

Edge Sentinel is a local proof of concept for observing simulated physical-security infrastructure. It keeps the monitoring boundary separate from the simulated fleet: the collector polls HTTP health endpoints, normalizes the observations, and optionally exports them to Azure.

![Current Edge Sentinel architecture](../images/architecture-diagram.png)

## Simulator

The FastAPI simulator models a fictional fleet across Detroit, Atlanta, and Phoenix: each site has a gateway and five controllers, with shared access-control and video-management services. State is held in memory, so restarting the simulator restores the fleet baseline.

The local control API supports component and site fault injection, fleet reset, and bounded randomization. A component can be `online`, `degraded`, or `offline`, and can be assigned a response delay. The collector classifies an otherwise healthy response that exceeds its configured latency threshold as `degraded`.

Gateway state is dependency-aware: when a site gateway is offline, its controllers retain their stored state but return HTTP 503 through their health endpoints. Site control changes the gateway and controllers at that site; shared services are independent. The control console starts the simulator bound to `127.0.0.1` for local demonstration use.

## Collector and telemetry

The Python collector reads the version-controlled inventory and polls each configured health endpoint on a configurable interval. It records application-reported health, response latency, malformed responses, timeouts, HTTP errors, and connection failures without relying on simulator internals.

Each normalized check record uses one of four health states: `online`, `degraded`, `offline`, or `unknown`. `unknown` represents an observation failure such as a timeout, HTTP error, or connection failure. Recovery is not a check-record health state: when a component changes state, the collector emits a separate transition record; a transition from `offline` or `unknown` to `online` is labeled `recovered`.

## Azure observability path

Azure export is opt-in. The collector resolves the DCR endpoint and immutable ID from process environment variables or a local ignored `.env` file, then uses `DefaultAzureCredential` to obtain an Azure Monitor token. It sends normalized check records to the Azure Monitor Logs Ingestion API, through a Direct Data Collection Rule (DCR), into the `EdgeSentinel_CL` custom table in Azure Log Analytics.

Workspace local/shared-key authentication is disabled; the implemented Azure integrations use Microsoft Entra ID and Azure RBAC authentication.

Collector identity selection and DCR-scoped `Monitoring Metrics Publisher` authorization are intentionally external to the reusable Bicep deployment, allowing each operator to authorize its own least-privilege credential.

KQL queries in `docs/queries/` produce current fleet and site views, availability trends, active failures, and alert inputs. The tracked Azure Workbook definition and Grafana dashboard both consume this telemetry model; Azure Monitor alerting detects unhealthy devices from the Log Analytics data.

## Infrastructure as code

The Bicep deployment is resource-group scoped and provisions the core ingestion foundation: a Log Analytics workspace, the `EdgeSentinel_CL` custom table, and a Direct DCR with its stream declaration, transformation, and Log Analytics destination. It does not deploy the simulator, collector, Grafana, alert rules, or workflow automation.

## Scope

This project is intentionally a proof of concept, not a production access-control integration. A production implementation could replace the simulator with supported platform APIs while preserving the collection, normalization, and observability pattern.
