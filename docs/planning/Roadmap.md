# Edge Sentinel Roadmap

This roadmap outlines the planned evolution of Edge Sentinel from an initial proof of concept into a portfolio-ready cloud observability platform.

The roadmap is intentionally iterative. Each phase produces a working system before introducing additional capabilities.

---

# Phase 1 - Project Foundation

## Objective

Establish the project structure, architecture, and design documentation.

## Deliverables

- Repository structure
- Project documentation
- High-level architecture
- Development environment
- Initial project planning

## Exit Criteria

The project is fully planned and ready for implementation.

---

# Phase 2 - Enterprise Infrastructure Simulator

## Objective

Build a simulated enterprise environment that represents distributed access control infrastructure.

## Deliverables

- Multiple simulated sites
- Simulated controllers
- Simulated gateways
- Generic Access Control Server
- Generic Video Management Server
- HTTP health endpoints
- Manual fault injection

## Exit Criteria

The simulator can represent healthy and unhealthy infrastructure through documented health endpoints.

---

# Phase 3 - Monitoring Collector

## Objective

Develop an independent monitoring engine that observes the simulated infrastructure.

## Deliverables

- Inventory-based monitoring
- HTTP polling
- Health evaluation
- State tracking
- Failure classification
- Telemetry generation

## Exit Criteria

The collector independently detects and classifies infrastructure health without relying on internal simulator knowledge.

---

# Phase 4 - Azure Observability

## Objective

Send monitoring telemetry into Microsoft Azure and build centralized observability.

## Deliverables

- Azure Log Analytics
- KQL queries
- Azure Workbook dashboard
- Fleet visibility

## Exit Criteria

Infrastructure health is visible through Azure dashboards and queryable using KQL.

---

# Phase 5 - Alerting and Automation

## Objective

Transform telemetry into actionable operational events.

## Deliverables

- Azure Monitor alerts
- Action Groups
- Logic Apps
- Simulated incident workflow

## Exit Criteria

Infrastructure faults generate meaningful alerts and automated notifications.

---

# Phase 6 - Infrastructure as Code

## Objective

Automate Azure deployment and project infrastructure.

## Deliverables

- Bicep templates
- GitHub Actions
- Repeatable deployments

## Exit Criteria

The Azure environment can be recreated from source control.

---

# Version 1.0

Edge Sentinel Version 1.0 demonstrates an end-to-end enterprise monitoring workflow:

1. A simulated infrastructure component experiences a fault.
2. The Monitoring Collector detects and classifies the issue.
3. Telemetry is ingested into Azure.
4. Azure visualizes the infrastructure state.
5. Azure Monitor generates an alert.
6. Logic Apps trigger a simulated incident workflow.

---

# Future Enhancements

Potential future enhancements include:

- Azure Arc
- Containerized deployment
- Azure Container Apps
- Azure Functions
- ServiceNow Developer Instance integration
- Event Grid
- AI-assisted anomaly detection
- Additional simulated infrastructure components