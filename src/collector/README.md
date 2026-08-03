# Edge Sentinel Collector

This collector reads the simulator's health endpoints and prints normalized telemetry to the terminal. The simulator must already be running on `http://127.0.0.1:8000`.

## Inventory

The collector loads monitored components from [inventory.json](inventory.json). Each entry contains only a stable device ID and its health endpoint:

```json
{
  "deviceId": "detroit-panel-01",
  "healthUrl": "http://127.0.0.1:8000/components/detroit-panel-01/health"
}
```

Components can later be added through this configuration file rather than by changing collector code.

The default path is resolved beside the collector code. Use `--inventory <path>` only when testing a different inventory file.

## Run locally

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r src\collector\requirements.txt
python src\collector\main.py --once
```

`--once` preserves the original behavior: the collector checks each component once, prints one JSON record per check, then exits.

## Continuous polling

Without `--once`, the collector polls continuously every five seconds:

```powershell
python src\collector\main.py
```

Use `--interval` to change the interval in seconds:

```powershell
python src\collector\main.py --interval 2
```

Each pass prints telemetry for every component. When a component's status changes, the collector also prints one transition record. A change from `offline` or `unknown` to `online` is labeled `recovered`.

```json
{"eventType": "statusTransition", "timestamp": "2026-08-03T12:00:05+00:00", "deviceId": "detroit-panel-01", "previousStatus": "offline", "currentStatus": "online", "transition": "recovered"}
```

Press `Ctrl+C` to stop continuous polling cleanly.

Example output:

```json
{"timestamp": "2026-08-03T12:00:00+00:00", "deviceId": "detroit-panel-01", "siteId": "detroit", "componentType": "controller", "checkType": "httpHealth", "status": "online", "latencyMs": 4.2, "failureReason": null}
```
