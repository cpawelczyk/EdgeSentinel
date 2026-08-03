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

## Change controller state

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

This is a reproducible demonstration layer built from existing manual fault behavior. Randomized fleet behavior remains a separate future local enhancement.
