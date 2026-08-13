# Edge Sentinel: Azure Architecture Plan

## Purpose

This document defines the planned Microsoft Azure architecture for Edge
Sentinel before cloud implementation begins.

Edge Sentinel is a portfolio proof-of-concept for centralized
observability of simulated, distributed physical-security
infrastructure. The local simulator and monitoring collector are already
implemented and tested. Azure provides the centralized telemetry,
visualization, alerting, automation, and eventually
infrastructure-as-code layer.

The core architecture remains:

``` text
Enterprise Infrastructure Simulator
            |
            v
    Monitoring Collector
            |
      HTTPS / Azure API
            |
            v
      Microsoft Azure
            |
     Azure Monitor / Logs
```

This document intentionally separates the architecture we need for
Version 1 from possible future enhancements.

------------------------------------------------------------------------

## 1. Azure Subscription Boundary

Edge Sentinel will be deployed inside the existing Azure subscription
used for development and learning.

The subscription is the top-level Azure management and billing boundary
for the project. Edge Sentinel does not require a separate subscription.

Conceptually:

``` text
Azure Subscription
|
+-- Edge Sentinel Resource Group
    |
    +-- Log Analytics Workspace
    +-- Data Collection Rule / ingestion configuration
    +-- Azure Monitor resources
    +-- Azure Workbook
    +-- Alert rules
    +-- Action Group
    +-- Logic App
    +-- Future deployment resources
```

All Edge Sentinel Azure resources should be grouped together so they are
easy to identify, manage, secure, estimate costs for, and eventually
delete.

------------------------------------------------------------------------

## 2. Dedicated Resource Group

A new resource group should be created specifically for Edge Sentinel.

Example naming:

``` text
rg-edgesentinel-dev
```

The exact name can be selected during implementation.

### Why a dedicated resource group?

The resource group creates a clean lifecycle boundary around the
project.

It allows us to:

-   keep portfolio resources separate from unrelated Azure labs;
-   apply tags consistently;
-   view project-specific costs;
-   manage permissions at a logical scope;
-   deploy the environment through Bicep later;
-   delete the entire Edge Sentinel Azure environment cleanly when it is
    no longer needed.

For Version 1, nearly all Azure resources should live in this resource
group unless Azure requires a resource to exist at another scope.

------------------------------------------------------------------------

## 3. Local Infrastructure Boundary

The existing simulator and collector remain local during the initial
Azure implementation.

``` text
Local workstation

+----------------------------+
| Edge Sentinel Simulator    |
| FastAPI / localhost:8000   |
+-------------+--------------+
              |
              | HTTP health checks
              v
+----------------------------+
| Monitoring Collector       |
| Python                     |
+-------------+--------------+
              |
              | outbound HTTPS
              v
        Microsoft Azure
```

The simulator does not need to run in Azure.

The collector does not need to run in Azure.

This is intentional. The first cloud milestone is about centralized
observability, not application hosting.

The collector remains the trust boundary between the simulated
infrastructure and Azure. Azure receives normalized telemetry produced
by the collector rather than directly interrogating the simulator.

------------------------------------------------------------------------

## 4. Azure Networking

### Version 1 decision: No Azure VNet required

Edge Sentinel does **not** require an Azure Virtual Network for the
first implementation.

The local collector will initiate outbound HTTPS connections to Azure's
public ingestion endpoint. Azure does not need to initiate connections
back into the local workstation or simulator.

Conceptually:

``` text
Simulator
   |
   | localhost HTTP
   v
Collector
   |
   | outbound HTTPS / TCP 443
   v
Internet
   |
   v
Azure Monitor Logs ingestion
   |
   v
Log Analytics Workspace
```

This means Version 1 does not require:

-   an Azure VNet;
-   subnets;
-   Network Security Groups;
-   a VPN;
-   ExpressRoute;
-   public IP addresses for Edge Sentinel;
-   inbound firewall rules to the workstation;
-   Azure Bastion;
-   Private Endpoints.

### Why this is preferable for V1

Adding a VNet would not currently protect a workload hosted inside Azure
because there is no Edge Sentinel workload hosted there.

It would add complexity without improving the first telemetry-ingestion
milestone.

The important network-security property is that communication is
**outbound from the collector to Azure over HTTPS**. The simulator
remains bound to the local development environment and is not
intentionally exposed to the Internet.

### Future private networking

Private networking can be evaluated later if the architecture changes.

Examples include:

-   hosting the collector in Azure;
-   hosting the simulator in Azure;
-   requiring Azure Monitor ingestion over private connectivity;
-   using Azure Monitor Private Link Scope;
-   introducing private endpoints;
-   connecting a simulated or real remote network to Azure.

Those are future architecture decisions, not Version 1 requirements.

------------------------------------------------------------------------

## 5. First Azure Data Path

The first Azure milestone should prove one simple end-to-end path:

``` text
Simulator
    |
    v
Collector
    |
    | normalized JSON telemetry
    v
Azure Monitor Logs Ingestion
    |
    v
Log Analytics Workspace
    |
    v
KQL Query
```

The existing collector record contract should remain intact.

Example:

``` json
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

The initial success criterion is simple:

> Run the collector locally, send a normalized check record to Azure,
> and retrieve that record from Log Analytics using KQL.

No dashboard or alert is required to prove this first milestone.

------------------------------------------------------------------------

## 6. Log Analytics Workspace

A dedicated Log Analytics Workspace should be created for Edge Sentinel.

Conceptually:

``` text
rg-edgesentinel-dev
|
+-- Log Analytics Workspace
    |
    +-- Edge Sentinel telemetry
```

The workspace becomes the centralized telemetry store for the project.

It will support:

-   KQL investigation;
-   Azure Monitor queries;
-   Azure Workbooks;
-   scheduled-query alerts;
-   latency analysis;
-   component and site health analysis;
-   future operational reporting.

A dedicated workspace is preferable for this portfolio project because
it keeps the dataset isolated and makes the architecture easier to
explain, demonstrate, and remove.

------------------------------------------------------------------------

## 7. Telemetry Ingestion

The collector needs a supported mechanism for sending its normalized
records into Azure Monitor Logs.

The implementation should use the current Azure Monitor Logs ingestion
architecture, with the required Azure resources/configuration such as a
Data Collection Rule and the appropriate ingestion endpoint.

Conceptually:

``` text
Collector
   |
   | authenticate
   | send normalized records
   v
Azure Monitor Logs ingestion
   |
   +-- Data Collection Rule
   |
   v
Log Analytics custom table
```

The exact resource names and schema configuration will be selected
during implementation.

The collector's existing field meanings should not be changed merely to
accommodate Azure.

Check records and status-transition records must remain distinguishable.

------------------------------------------------------------------------

## 8. Identity and Authentication

Azure credentials must never be committed to Git.

The Azure integration should use Microsoft Entra ID authentication and
the smallest practical permission scope for the project.

During local development, authentication may use an appropriate
developer identity or application identity depending on the ingestion
implementation selected.

The design principles are:

-   no secrets in source control;
-   no credentials in `inventory.json`;
-   no credentials embedded in Python source;
-   least privilege;
-   environment-specific values supplied outside committed source;
-   future CI/CD identities separated from local developer
    authentication.

The repository `.gitignore` has already been hardened to reduce the risk
of committing local environment and Azure-specific
credential/configuration artifacts.

------------------------------------------------------------------------

## 9. Azure Monitor and KQL

Once telemetry reaches Log Analytics, KQL becomes the primary
investigation and analytics layer.

Example questions the project should eventually answer include:

-   Which components are currently unhealthy?
-   Which sites have generated failures?
-   Which controllers have exceeded the latency threshold?
-   What failure reasons occur most frequently?
-   When did a component transition from healthy to unhealthy?
-   When did it recover?
-   How has component latency changed over time?

KQL should be developed incrementally after ingestion is proven.

Reusable portfolio-quality queries can eventually be stored in the
repository.

Example future location:

``` text
docs/
└── queries/
    ├── fleet-health.kql
    ├── unhealthy-components.kql
    ├── latency-trends.kql
    └── status-transitions.kql
```

------------------------------------------------------------------------

## 10. Azure Workbook

After ingestion and KQL are stable, an Azure Workbook will provide the
primary visual demonstration layer.

Conceptually:

``` text
Log Analytics
      |
      | KQL
      v
Azure Workbook
      |
      +-- Fleet overview
      +-- Site health
      +-- Component health
      +-- Active failures
      +-- Latency trends
      +-- Recovery / transition information
```

This is where Edge Sentinel becomes visually demonstrable as an
observability platform.

The Workbook should be built from actual telemetry and queries rather
than designed before the data path exists.

------------------------------------------------------------------------

## 11. Alerting

After visualization is functioning, Azure Monitor scheduled-query alerts
can evaluate telemetry stored in Log Analytics.

Conceptually:

``` text
Log Analytics
      |
      | KQL condition
      v
Azure Monitor Alert Rule
      |
      v
Action Group
```

Possible conditions include:

-   controller becomes unreachable;
-   gateway becomes unreachable;
-   component remains degraded;
-   latency exceeds an operational threshold;
-   shared service becomes unhealthy.

Alert logic should be implemented only after the telemetry behavior is
understood through KQL.

------------------------------------------------------------------------

## 12. Automation

An Action Group can later invoke a Logic App.

``` text
Azure Monitor Alert
        |
        v
   Action Group
        |
        v
     Logic App
        |
        v
Simulated notification / incident workflow
```

The Version 1 automation should remain safe and demonstrative.

It should not modify real physical-security infrastructure.

Potential outputs include:

-   formatted notification;
-   Teams/email-style simulated notification;
-   simulated incident record;
-   webhook to a controlled demonstration endpoint.

Actual ServiceNow integration is a future enhancement.

------------------------------------------------------------------------

## 13. Infrastructure as Code

Once the Azure architecture is working manually and understood, its
resources should be represented using Bicep.

Potential repository structure:

``` text
infrastructure/
└── bicep/
    ├── main.bicep
    ├── parameters/
    └── modules/
```

Bicep should eventually define appropriate project resources such as:

-   resource group-scoped resources;
-   Log Analytics Workspace;
-   ingestion configuration;
-   Azure Monitor resources;
-   alerting resources;
-   automation resources.

The goal is repeatability, not unnecessary abstraction.

Infrastructure as Code comes **after** the first working Azure
implementation so that the project automates an architecture that has
already been validated.

------------------------------------------------------------------------

## 14. GitHub Actions

GitHub Actions is a later deployment layer.

Conceptually:

``` text
GitHub Repository
       |
       | workflow
       v
GitHub Actions
       |
       | authenticated Azure deployment
       v
Azure Resource Group
       |
       v
Bicep Resources
```

CI/CD should use an appropriate secure identity mechanism and should not
store reusable Azure credentials directly in the repository.

Dependency pinning and automated dependency/security checks should also
be addressed before or during this phase.

------------------------------------------------------------------------

## 15. Resource Model

The expected Version 1 Azure resource hierarchy is approximately:

``` text
Azure Subscription
|
└── rg-edgesentinel-dev
    |
    ├── Log Analytics Workspace
    |
    ├── Azure Monitor Logs ingestion configuration
    |   └── Data Collection Rule
    |
    ├── Azure Workbook
    |
    ├── Azure Monitor scheduled-query alert rule(s)
    |
    ├── Action Group
    |
    └── Logic App
```

Resources may be added or adjusted when Azure implementation
requirements are validated, but additions should have a clear purpose.

------------------------------------------------------------------------

## 16. Resources Deliberately Not Required for V1

The following are not currently required:

-   Azure Virtual Network
-   Subnets
-   Network Security Groups
-   VPN Gateway
-   ExpressRoute
-   Azure Bastion
-   Azure Firewall
-   Azure Arc
-   Azure Kubernetes Service
-   Azure Container Apps
-   Azure Functions
-   Azure SQL Database
-   Cosmos DB
-   Storage Account for primary telemetry
-   Event Grid
-   Service Bus
-   production API gateway
-   production authentication for the simulator
-   production-grade high availability

Their absence is intentional rather than an architectural oversight.

------------------------------------------------------------------------

## 17. Security Boundary

The Version 1 security model is intentionally simple.

### Local boundary

The simulator and fault-injection API are development/demo components
and should remain local.

They are not intended to be Internet-facing production APIs.

### Collector boundary

The collector is the trusted monitoring component.

It reads trusted inventory configuration, observes simulator endpoints,
normalizes results, and sends approved telemetry to Azure.

### Azure boundary

Azure stores operational telemetry only.

Edge Sentinel telemetry must not contain:

-   credentials;
-   badgeholder information;
-   access-control configuration;
-   personal information;
-   real customer infrastructure details;
-   proprietary physical-security data.

The current simulator inventory is fictional and uses loopback
endpoints.

------------------------------------------------------------------------

## 18. Cost and Lifecycle

Edge Sentinel should remain inexpensive and disposable.

Architecture decisions should favor:

-   low ingestion volume;
-   minimal always-on compute;
-   development-tier usage where appropriate;
-   no unnecessary network appliances;
-   no unnecessary databases;
-   resources that can be recreated through Bicep;
-   a dedicated resource group that can eventually be deleted as one
    lifecycle unit.

Azure cost should be reviewed as resources are introduced.

------------------------------------------------------------------------

## 19. Implementation Sequence

The Azure implementation should proceed incrementally.

### Milestone 1 - Azure foundation

-   Confirm subscription.
-   Create the dedicated Edge Sentinel resource group.
-   Create the Log Analytics Workspace.
-   Configure the minimum required ingestion resources.

### Milestone 2 - Telemetry ingestion

-   Authenticate the local collector to Azure.
-   Send existing normalized collector telemetry.
-   Confirm records arrive in Log Analytics.

### Milestone 3 - KQL

-   Query telemetry.
-   Filter by device, site, component type, status, failure reason, and
    latency.
-   Save useful operational queries.

### Milestone 4 - Visualization

-   Build the Azure Workbook.
-   Create fleet/site/component health views.
-   Add latency and failure visualizations.

### Milestone 5 - Alerting

-   Create Azure Monitor scheduled-query alert rules.
-   Create an Action Group.
-   Validate alerts using deterministic simulator faults.

### Milestone 6 - Automation

-   Add the Logic App.
-   Demonstrate a simulated operational notification or incident
    workflow.

### Milestone 7 - Infrastructure as Code

-   Reproduce the validated Azure architecture using Bicep.

### Milestone 8 - CI/CD

-   Add GitHub Actions for validation/deployment.
-   Add dependency/security checks as appropriate.

### Milestone 9 - Public portfolio cleanup

-   Finalize root README.
-   Finalize license.
-   Update architecture documentation and diagram to represent
    implemented functionality.
-   Pin/review dependencies.
-   Perform final security/public-readiness review.
-   Capture Azure Workbook screenshots and demonstration material.
-   Make the repository public when ready.

------------------------------------------------------------------------

## 20. Final Version 1 Architecture

The intended end-state is:

``` text
                   LOCAL DEVELOPMENT ENVIRONMENT

     +-----------------------------------------------+
     | Enterprise Infrastructure Simulator           |
     |                                               |
     | Detroit       Atlanta       Phoenix           |
     | Gateway       Gateway       Gateway           |
     | Controllers   Controllers   Controllers       |
     |                                               |
     | Shared Access-Control / Video Services        |
     +----------------------+------------------------+
                            |
                            | HTTP health checks
                            v
                  +---------------------+
                  | Monitoring Collector|
                  +----------+----------+
                             |
                             | outbound HTTPS
                             | authenticated ingestion
                             v

                         MICROSOFT AZURE

                  +----------------------+
                  | Log Analytics        |
                  | Workspace            |
                  +----------+-----------+
                             |
                +------------+-------------+
                |                          |
                v                          v
         +-------------+            +-------------+
         | KQL Queries |            | Workbook    |
         +-------------+            +-------------+
                |
                v
         +-------------------+
         | Azure Monitor     |
         | Alert Rules       |
         +---------+---------+
                   |
                   v
            +-------------+
            | Action Group|
            +------+------+
                   |
                   v
             +-----------+
             | Logic App |
             +-----------+

                    DEPLOYMENT LAYER

         GitHub -> GitHub Actions -> Bicep -> Azure
```

No Azure VNet is required for this Version 1 architecture because the
collector initiates outbound HTTPS communication to Azure and no
Azure-hosted Edge Sentinel workload requires private network
segmentation.

------------------------------------------------------------------------

## Architecture Principle

Edge Sentinel should remain easy to explain:

> A simulated distributed physical-security environment is independently
> monitored by a local collector. The collector converts observations
> into normalized operational telemetry and securely sends that
> telemetry to Azure, where Azure Monitor provides centralized querying,
> visualization, alerting, and automation.

Every Azure resource added to the project should strengthen that story.
