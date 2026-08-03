# Edge Sentinel

## Vision

Edge Sentinel is a proof-of-concept infrastructure observability platform designed to demonstrate how modern cloud technologies can improve the monitoring of distributed access control infrastructure. The project simulates geographically distributed access control systems and uses Microsoft Azure to provide centralized telemetry, dashboards, alerting, and automated incident workflows. Inspired by real-world enterprise operational challenges, Edge Sentinel serves as both an Azure learning project and a portfolio demonstration of cloud engineering, infrastructure monitoring, and automation.

---

# Problem Statement

Modern enterprise access control environments often consist of hundreds of distributed IP-based controllers spread across multiple facilities. While these controllers are critical to daily operations, native monitoring capabilities are frequently limited, proprietary, or difficult to integrate into broader enterprise monitoring platforms.

A controller may continue making local access decisions even after losing communication with the central application server, leaving operators unaware that visibility, event reporting, and centralized management have been degraded. This lack of observability often results in delayed detection, reactive troubleshooting, and increased operational overhead.

Edge Sentinel explores how cloud-native monitoring and automation can improve visibility into distributed infrastructure while remaining vendor-neutral.

---

# Goals

- Simulate realistic enterprise physical security infrastructure.
- Model common operational failures such as offline devices, latency, packet loss, flapping connections, and site-wide outages.
- Demonstrate Microsoft Azure observability using Azure Monitor, Log Analytics, Workbooks, and KQL.
- Automate incident detection and response through Azure alerting and Logic Apps.
- Deploy Azure resources using Infrastructure as Code (Bicep) and GitHub Actions.

---

# Non-Goals

Edge Sentinel is **not** intended to:

- Replace a commercial monitoring platform.
- Implement a real access control system.
- Simulate badgeholders, credentials, readers, or door logic.
- Integrate directly with proprietary vendor APIs or protocols.
- Function as a production SIEM or enterprise monitoring platform.

The focus is demonstrating cloud observability, automation, and infrastructure monitoring principles.

---

# High Level Architecture

```
Enterprise Infrastructure Simulator
            │
            ▼
    Monitoring Collector
            │
            ▼
 Microsoft Azure Observability
```

The Enterprise Infrastructure Simulator models geographically distributed access control infrastructure including sites, controllers, gateways, and supporting application servers.

The Monitoring Collector independently discovers, polls, evaluates, and correlates infrastructure health before forwarding normalized telemetry into Microsoft Azure.

Microsoft Azure provides centralized observability through dashboards, KQL queries, alerting, automation, and Infrastructure as Code deployment.

*(See `ArchitectureDiagram.png` for the complete architecture.)*

---

# Technology Stack

## Languages

- Python

## Azure Services

- Azure Monitor
- Log Analytics
- Azure Workbooks
- Logic Apps
- Azure Resource Manager (Bicep)

## DevOps

- GitHub
- GitHub Actions

---

# Success Criteria

Version 1.0 is considered successful when the following workflow is fully operational:

1. A simulated infrastructure component experiences a fault.
2. The Monitoring Collector detects and classifies the issue.
3. Structured telemetry is ingested into Azure Log Analytics.
4. Azure Monitor generates an alert based on KQL queries.
5. A Logic App triggers an automated notification or simulated incident.
6. The infrastructure state is visible through an Azure Workbook dashboard.

---

# Stretch Goals

Potential future enhancements include:

- Azure Arc integration
- Containerized simulator deployment
- Azure Container Apps
- Azure Functions
- Managed Identity
- Key Vault
- Event Grid
- AI-assisted anomaly detection
- Simulated camera infrastructure
- ServiceNow Developer Instance integration