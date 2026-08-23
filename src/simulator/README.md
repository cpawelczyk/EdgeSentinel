# Edge Sentinel Simulator

This is the smallest local simulator slice for Edge Sentinel. It keeps component state in memory, so restarting the server resets the controller to `online` with no delay.

## Run locally

From the repository root in PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
py -m pip --python .venv install -r src\simulator\requirements.txt
python -m uvicorn main:app --app-dir src\simulator --reload
```

The simulator listens at `http://127.0.0.1:8000`.

## Run tests

From the repository root:

```powershell
python -m pytest
```

## Check controller health

```powershell
Invoke-RestMethod http://127.0.0.1:8000/components/detroit-panel-01/health
```

## Control API

The simulator exposes these localhost-only control endpoints:

```text
POST /components/{device_id}/fault
POST /sites/{site_id}/fault
POST /fleet/reset
POST /fleet/randomize
GET  /fleet/state
```

### Control an individual component

Set the controller offline:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/components/detroit-panel-01/fault `
  -ContentType 'application/json' `
  -Body '{"status":"offline","delaySeconds":0}'
```

Set the controller back online with a one-second response delay:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/components/detroit-panel-01/fault `
  -ContentType 'application/json' `
  -Body '{"status":"online","delaySeconds":1}'
```

Take a gateway offline. Its controllers retain their stored states, but their health endpoint returns HTTP 503 while the gateway remains offline:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/components/detroit-gateway-01/fault `
  -ContentType 'application/json' `
  -Body '{"status":"offline","delaySeconds":0}'
```

### Control a site

Set a site's gateway and controllers offline together:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/sites/detroit/fault `
  -ContentType 'application/json' `
  -Body '{"status":"offline","delaySeconds":0}'
```

The simulated sites are `detroit`, `atlanta`, and `phoenix`. Site control does not affect the shared access-control or video-management servers.

### Restore, randomize, and inspect the fleet

Restore every component to `online` with no delay:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/fleet/reset
```

Generate one bounded, demo-friendly fault state. This is a one-shot update, not a background process:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/fleet/randomize
```

Retrieve the fleet read model, including stored state and `effectiveStatus`. A controller whose gateway is offline retains its stored status and reports `effectiveStatus` as `unreachable`:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/fleet/state
```

## Run the deterministic local scenario

Start the simulator and collector in separate PowerShell windows. Use a shorter collector interval so it observes each scenario step:

```powershell
python src\collector\main.py --interval 2
```

Then run the scenario from a third window:

```powershell
python src\simulator\run_scenario.py
```

It resets the Phoenix gateway and `phoenix-panel-03`, then applies a three-second panel delay, clears it, takes the Phoenix gateway offline, and restores it. The default ten-second pause between steps gives the collector time to emit telemetry and transitions. Use a different pause when needed:

```powershell
python src\simulator\run_scenario.py --step-delay 5
```

This is a reproducible demonstration layer built from existing manual fault behavior.
