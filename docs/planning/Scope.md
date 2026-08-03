# Edge Sentinel Scope

## Project Goal

Edge Sentinel is a portfolio project demonstrating cloud-based observability for simulated enterprise access control infrastructure using Microsoft Azure.

The objective is to build a realistic, understandable, end-to-end monitoring platform; not a production monitoring product.

---

# In Scope (Version 1)

## Enterprise Infrastructure Simulator

- Three simulated sites
- Site gateways
- Access control controllers
- Generic Access Control Server
- Generic Video Management Server
- HTTP health endpoints
- Configurable fault injection

## Monitoring Collector

- Inventory-driven monitoring
- HTTP polling
- Health classification
- State tracking
- Telemetry normalization
- Azure telemetry export

## Microsoft Azure

- Log Analytics
- Azure Monitor
- KQL
- Azure Workbooks
- Alert Rules
- Logic Apps
- Bicep
- GitHub Actions

---

# Out of Scope (Version 1)

The following items are intentionally excluded from Version 1:

- Real access control software
- Badgeholders
- Credentials
- Door logic
- Readers
- Camera simulation
- Production ServiceNow integration
- Production SIEM integration
- Automatic remediation of real infrastructure
- AI anomaly detection
- Kubernetes
- Multi-region deployment
- High availability
- Horizontal scaling
- Enterprise authentication beyond development needs

---

# Guiding Principles

When evaluating new ideas, ask:

1. Does this strengthen the project's core story?
2. Does this improve Azure learning?
3. Would this reasonably be expected in a Version 1 portfolio project?

If the answer is "no" to any of these questions, move the idea to the Future Enhancements section instead of expanding the project.

---

# Definition of Version 1 Complete

Version 1 is complete when:

- The simulator models enterprise infrastructure.
- The collector independently detects infrastructure health.
- Azure visualizes telemetry.
- Azure generates alerts.
- Logic Apps trigger a simulated incident workflow.
- The Azure environment is reproducible using Bicep.
