# Edge Sentinel Collector

This one-shot collector reads the simulator's health endpoints and prints normalized telemetry to the terminal. The simulator must already be running on `http://127.0.0.1:8000`.

## Run locally

From the repository root in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r src\collector\requirements.txt
python src\collector\main.py
```

The collector checks each component once, prints one JSON record per check, then exits.

Example output:

```json
{"timestamp": "2026-08-03T12:00:00+00:00", "deviceId": "detroit-panel-01", "siteId": "detroit", "componentType": "controller", "checkType": "httpHealth", "status": "online", "latencyMs": 4.2, "failureReason": null}
```
