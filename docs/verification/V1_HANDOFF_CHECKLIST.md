# V1 Handoff Checklist

## Run App Locally

```bash
# Backend
cd backend
uv sync
uv run uvicorn app.main:app --port 8010

# Frontend
cd frontend
npm install
npm run dev  # opens on 3010
```

Open `http://localhost:3010`

## Run Final Acceptance Checks

```bash
# P7-2: Friend stock full E2E
.venv/Scripts/python.exe scripts/verify_p7_2_browser_demo_a_friend_stock_full_e2e.py

# P7-3: Strategy full E2E
.venv/Scripts/python.exe scripts/verify_p7_3_browser_demo_b_strategy_full_e2e.py

# P7-4: Boundary & UI smoke
.venv/Scripts/python.exe scripts/verify_p7_4_v1_boundary_and_ui_smoke_acceptance.py

# Build check
npm run build
```

Exit code `0` = pass.

## Evidence Location

`docs/verification/`:
- `V1_FINAL_PRODUCT_ACCEPTANCE.md` (main report)
- `V1_RELEASE_NOTES.md`
- `P7_2_DELIVERY.md`, `P7_3_DELIVERY.md`, `P7_4_DELIVERY.md`
- `p7-2-*`, `p7-3-*`, `p7-4-*` (DOM, network, API logs)

## Do Not Change Before Release

- `backend/app/workbench_execution_feedback.py` (buy/sell message parser)
- `backend/app/workbench_strategy_brain.py` (template mapping, rejection logic)
- `backend/database/` schemas
- `frontend/app/workbench/page.tsx` (input placeholder checked in boundary tests)
- Verification scripts `scripts/verify_p7_*`

## Safe Limitations

These are **documented design boundaries**, not bugs:

1. Approved strategy library empty
2. Risk guard not configured
3. Signal may be null when data unavailable
4. No automatic trading
5. Template mapping rejects most user strategies (by design, no fake approvals)

## Post-V1 Candidates (Do Not Add Now)

- Approved template library expansion
- Risk guard configuration
- Market data source integration
- Observation → position merge flow
- Strategy validation job execution

Add these **only after V1 released and stable**.
