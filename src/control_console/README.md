# Edge Sentinel Control Console

The Control Console is a native PySide6 desktop application for viewing and controlling the local EdgeSentinel simulator. It communicates only with the simulator REST API; it does not communicate with the collector, Azure Monitor, or Log Analytics.

## Install and run

From the repository root in PowerShell, install the dedicated GUI dependencies:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r src\control_console\requirements.txt
```

Start the simulator in one PowerShell window:

```powershell
python -m uvicorn main:app --app-dir src\simulator --reload
```

Launch the control console from another window:

```powershell
python -m src.control_console.main
```

## Controls

- Click any gateway, controller, or shared-service node to select it and open its inspector.
- Use the inspector to set a component online, degraded, or offline.
- For a selected site device, use `SITE ONLINE` or `SITE OFFLINE` to control that site’s gateway and controllers.
- Use `RESET FLEET` to restore the complete fleet to a healthy baseline.
- Use `RANDOMIZE` to request one bounded demo fault state.

The console polls `GET /fleet/state` every 1.5 seconds. It uses `effectiveStatus` for topology colors and connection lines while retaining the simulator’s stored `status` in the inspector. For example, a controller behind an offline gateway is shown as `UNREACHABLE` even when its stored status remains `ONLINE`.

The `SIMULATOR` indicator reflects whether fleet-state polling succeeds. `COLLECTOR` and `AZURE` intentionally remain `UNKNOWN` until reliable health signals are added in a future milestone.
