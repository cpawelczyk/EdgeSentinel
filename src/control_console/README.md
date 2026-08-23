# Edge Sentinel Control Console

The Control Console is a native PySide6 desktop application for viewing and controlling the local EdgeSentinel simulator. It communicates only with the simulator REST API; it does not communicate with the collector, Azure Monitor, or Log Analytics.

## Install and run

From the repository root in PowerShell, install the dedicated GUI dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r src\control_console\requirements.txt
```

For the Azure-enabled demo, copy the safe template and populate your Azure Data
Collection Rule settings. These are non-secret configuration values; authentication
continues to use your normal `DefaultAzureCredential` sign-in.

```powershell
Copy-Item .env.example .env
# Edit .env and set EDGESENTINEL_DCR_ENDPOINT and EDGESENTINEL_DCR_IMMUTABLE_ID.
az login
```

Launch the control console:

```powershell
python -m src.control_console.main
```

Then use `SIMULATOR` → `AZURE` → `COLLECTOR`. The console starts and stops only
the simulator and collector processes that it launched.

## Controls

- Click any gateway, controller, or shared-service node to select it and open its inspector.
- Use the inspector to set a component online, degraded, or offline.
- For a selected site device, use `SITE ONLINE` or `SITE OFFLINE` to control that site’s gateway and controllers.
- Use `RESET FLEET` to restore the complete fleet to a healthy baseline.
- Use `RANDOMIZE` to request one bounded demo fault state.

The console polls `GET /fleet/state` every 1.5 seconds. It uses `effectiveStatus` for topology colors and connection lines while retaining the simulator’s stored `status` in the inspector. For example, a controller behind an offline gateway is shown as `UNREACHABLE` even when its stored status remains `ONLINE`.

The indicators report simulator reachability, collector heartbeat health, and Azure
credential/recent ingestion health.
