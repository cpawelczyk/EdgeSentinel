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
