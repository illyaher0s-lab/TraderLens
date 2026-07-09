# TraderLens Runtime Ports

**Standard local development ports:**

- **Backend:** `localhost:8010`
- **Frontend:** `localhost:3010`

## Why 3010 instead of 3000

Port 3000 is commonly used by other local projects (e.g., Crossroads). To avoid conflicts, TraderLens frontend uses port 3010.

## Starting Services

### Backend
```powershell
cd D:\Codex\TraderLens
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8010
```

### Frontend
```powershell
cd D:\Codex\TraderLens\frontend
npm run dev -- --port 3010
```

## Verification Scripts

All verification scripts in `scripts/` use `runtime_process_helpers.py` to start backend and frontend with correct ports.

**Do not hardcode ports in new scripts.** Use:
```python
from scripts.runtime_process_helpers import start_backend, start_frontend

backend_proc = start_backend(port=8010)
frontend_proc = start_frontend(port=3010)
```

## Port Conflict Handling

If a port is occupied:
1. **Do not automatically kill** processes you didn't start
2. Report PID and CommandLine:
   ```powershell
   Get-NetTCPConnection -LocalPort 8010,3010
   Get-CimInstance Win32_Process -Filter "ProcessId = <PID>" | Select-Object ProcessId,Name,CommandLine
   ```
3. Let the user decide whether to stop the conflicting process

## Frontend API Base URL

Frontend fetches from `http://localhost:8010` (backend port), not its own port 3010.

See `frontend/app/page.tsx`, `frontend/lib/api-client.ts` for examples.
