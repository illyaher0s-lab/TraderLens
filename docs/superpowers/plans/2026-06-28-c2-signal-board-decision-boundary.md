# C2 Signal Board Decision Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Signal Board user-facing output safe: admitted signals can be viewed, but the UI/API/agent-facing text must not become buy/sell advice, live-trading readiness, or profit claims.

**Architecture:** C0 controls signal generation admission. C1 controls Signal Board list admission filtering. C2 closes the remaining decision-boundary gaps: detail lookup by signal ID, frontend/API type metadata, visible copy, and agent-readable explanation boundaries. C2 must not rebuild Signal Board list, pagination, review, strategy filters, B-module validation, or live execution.

**Tech Stack:** Python 3.11, FastAPI, SQLite SignalBoardDB, Pydantic contracts, Next.js/TypeScript Signal Board UI, pytest/unittest.

---

## Current Signal Board State

Already implemented:
- M4: `PlannedSignal`, SignalBoardDB, FastAPI Signal Board endpoints, Next.js list/detail pages, manual review states.
- M4.1: strategy selector, pagination, date filters, Load More, quick review, expiration workflow.
- C0: `generate_planned_signals.py` requires B-approved `prototype_passed` strategy revision before generating new signals.
- C1: Signal Board list and strategy endpoints filter to admitted `prototype_passed` signals by default; public API no longer exposes `include_missing_admission`.

Do not repeat:
- Do not rebuild Signal Board UI layout.
- Do not add charts, batch review, notifications, broker API, live trading, or real-time data.
- Do not change B3/B4/B5/B6 semantics.
- Do not add new trading strategy rules.

Known gaps to verify:
- `GET /api/signals/{signal_id}` may still return a non-admitted signal by direct ID lookup.
- `frontend/lib/api-client.ts` may not include C1 admission metadata fields.
- Visible copy and tests contain mojibake in several Signal Board files.
- Existing copy guardrail only checks a small set of prohibited terms.

---

## File Map

- Modify: `backend/api/signal_board.py`
  - Enforce admission filtering for single-signal detail lookup.
- Modify: `backend/db/signal_board.py`
  - Add a focused helper if needed, for example `get_admitted_signal(signal_id)`.
- Modify: `frontend/lib/api-client.ts`
  - Add C1 admission metadata fields to `PlannedSignal`.
- Modify: `frontend/app/signals/page.tsx`
  - Fix visible copy only where it affects decision boundary or mojibake.
- Modify: `frontend/app/signals/[signal_id]/page.tsx`
  - Fix visible copy and show admission context without making trade recommendations.
- Modify: `tests/test_signal_api.py`
  - Add direct-detail admission filtering regression test.
- Modify: `tests/test_signal_board_ux_polish.py`
  - Expand prohibited wording and mojibake checks.
- Create: `tests/test_c2_signal_board_decision_boundary.py`
  - C2-specific boundary tests.
- Create: `docs/verification/C2_VERIFICATION.md`
  - Final acceptance record.

---

### Task C2-1: Prove Direct Detail Lookup Admission Risk

**Files:**
- Modify: `tests/test_signal_api.py`

- [ ] **Step 1: Write failing test for direct ID bypass**

Add this test to `TestSignalBoardAPI`:

```python
def test_get_signal_rejects_unadmitted_signal_by_direct_id(self):
    """Direct signal detail lookup must not bypass C1 list filtering."""
    signal = self._create_test_signal(
        signal_id="legacy-unadmitted",
        strategy_revision_id=None,
        lifecycle_state_at_generation=None,
        admission_source=None,
    )
    self.db.create_signal(signal)

    response = self.client.get("/api/signals/legacy-unadmitted")

    self.assertEqual(response.status_code, 404)
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_signal_api.py::TestSignalBoardAPI::test_get_signal_rejects_unadmitted_signal_by_direct_id -q
```

Expected before implementation: FAIL because `/api/signals/{signal_id}` returns the legacy signal.

- [ ] **Step 3: Commit failing test**

```powershell
git add tests/test_signal_api.py
git commit -m "test: C2 identify Signal Board detail admission bypass"
```

---

### Task C2-2: Enforce Admission on Single-Signal Detail API

**Files:**
- Modify: `backend/db/signal_board.py`
- Modify: `backend/api/signal_board.py`
- Test: `tests/test_signal_api.py`

- [ ] **Step 1: Add admitted-detail DB helper**

In `SignalBoardDB`, add:

```python
def get_admitted_signal(self, signal_id: str) -> PlannedSignal | None:
    """Return signal only if it has valid C admission metadata."""
    signal = self.get_signal(signal_id)
    if signal is None:
        return None
    if signal.lifecycle_state_at_generation != "prototype_passed":
        return None
    return signal
```

- [ ] **Step 2: Use admitted-detail helper in API**

In `backend/api/signal_board.py`, change `get_signal()` to call:

```python
signal = db.get_admitted_signal(signal_id)
```

Keep the 404 behavior:

```python
if signal is None:
    raise HTTPException(status_code=404, detail=f"Signal {signal_id} not found")
```

- [ ] **Step 3: Verify direct bypass test passes**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_signal_api.py::TestSignalBoardAPI::test_get_signal_rejects_unadmitted_signal_by_direct_id -q
```

Expected: PASS.

- [ ] **Step 4: Run Signal API focused tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_signal_api.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/db/signal_board.py backend/api/signal_board.py tests/test_signal_api.py
git commit -m "feat: C2 enforce admission on Signal Board detail lookup"
```

---

### Task C2-3: Align Frontend Signal Type With Admission Metadata

**Files:**
- Modify: `frontend/lib/api-client.ts`
- Test: `tests/test_c2_signal_board_decision_boundary.py`

- [ ] **Step 1: Create boundary test for frontend type metadata**

Create `tests/test_c2_signal_board_decision_boundary.py`:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_CLIENT = ROOT / "frontend" / "lib" / "api-client.ts"
SIGNALS_PAGE = ROOT / "frontend" / "app" / "signals" / "page.tsx"
SIGNAL_DETAIL_PAGE = ROOT / "frontend" / "app" / "signals" / "[signal_id]" / "page.tsx"


def test_frontend_planned_signal_includes_admission_metadata():
    source = API_CLIENT.read_text(encoding="utf-8")

    assert "strategy_revision_id: string | null" in source
    assert "lifecycle_state_at_generation: string | null" in source
    assert "admission_source: string | null" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py::test_frontend_planned_signal_includes_admission_metadata -q
```

Expected before implementation: FAIL because frontend type lacks C1 fields.

- [ ] **Step 3: Add metadata fields to TypeScript type**

In `frontend/lib/api-client.ts`, add to `PlannedSignal`:

```ts
  strategy_revision_id: string | null;
  lifecycle_state_at_generation: string | null;
  admission_source: string | null;
```

- [ ] **Step 4: Verify test passes**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py::test_frontend_planned_signal_includes_admission_metadata -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add frontend/lib/api-client.ts tests/test_c2_signal_board_decision_boundary.py
git commit -m "feat: C2 expose admission metadata to Signal Board frontend type"
```

---

### Task C2-4: Lock User-Facing Copy Boundary

**Files:**
- Modify: `frontend/app/signals/page.tsx`
- Modify: `frontend/app/signals/[signal_id]/page.tsx`
- Modify: `tests/test_signal_board_ux_polish.py`
- Modify: `tests/test_c2_signal_board_decision_boundary.py`

- [ ] **Step 1: Add copy guard tests**

Append to `tests/test_c2_signal_board_decision_boundary.py`:

```python
def test_signal_board_visible_copy_has_decision_boundary_disclaimer():
    list_source = SIGNALS_PAGE.read_text(encoding="utf-8")
    detail_source = SIGNAL_DETAIL_PAGE.read_text(encoding="utf-8")

    required_phrases = [
        "不是买卖建议",
        "不会自动交易",
        "仅显示已通过验证的计划信号",
    ]

    combined = list_source + "\n" + detail_source
    for phrase in required_phrases:
        assert phrase in combined


def test_signal_board_visible_copy_has_no_profit_or_live_trading_claims():
    combined = (
        SIGNALS_PAGE.read_text(encoding="utf-8")
        + "\n"
        + SIGNAL_DETAIL_PAGE.read_text(encoding="utf-8")
    )

    forbidden = [
        "保证盈利",
        "稳定盈利",
        "实盘可用",
        "立即买入",
        "立即卖出",
        "推荐买入",
        "推荐卖出",
        "最佳策略",
        "一键下单",
        "自动交易",
    ]

    for phrase in forbidden:
        assert phrase not in combined
```

- [ ] **Step 2: Run tests to verify current state**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py -q
```

Expected before implementation: at least one test fails if disclaimer is missing or TypeScript metadata is not yet added.

- [ ] **Step 3: Update list page copy**

In `frontend/app/signals/page.tsx`, the page header supporting copy should include:

```tsx
<p className="text-xs text-[#808080] mt-1">
  仅显示已通过验证的计划信号｜不是买卖建议｜不会自动交易
</p>
```

Do not add new UI sections, charts, or cards.

- [ ] **Step 4: Update detail page copy and mojibake**

In `frontend/app/signals/[signal_id]/page.tsx`, replace mojibake-visible strings with readable Chinese. The detail header should include:

```tsx
<p className="text-xs text-slate-500 mt-2">
  仅显示已通过验证的计划信号；不是买卖建议；不会自动交易。
</p>
```

Keep action labels neutral:

```tsx
{signal.planned_action === "enter" ? "入场" : "离场"}
```

Review actions must remain:

```tsx
ignored | watching | expired
```

- [ ] **Step 5: Expand existing UX polish guard**

In `tests/test_signal_board_ux_polish.py`, make prohibited visible-copy terms readable and expanded:

```python
prohibited_terms = [
    "推荐买入",
    "推荐卖出",
    "立即买入",
    "立即卖出",
    "保证盈利",
    "稳定盈利",
    "实盘可用",
    "一键下单",
    "自动交易",
    "最佳策略",
    "策略排名",
]
```

Add a mojibake guard:

```python
def test_signal_board_pages_have_no_mojibake(self):
    for path in [SIGNALS_PAGE, ROOT / "frontend" / "app" / "signals" / "[signal_id]" / "page.tsx"]:
        source = path.read_text(encoding="utf-8")
        for marker in ["鐩", "鍏", "绂", "淇", "瀹", "鈫", "鉁"]:
            self.assertNotIn(marker, source)
```

- [ ] **Step 6: Verify focused UI/copy tests**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add frontend/app/signals/page.tsx frontend/app/signals/[signal_id]/page.tsx tests/test_signal_board_ux_polish.py tests/test_c2_signal_board_decision_boundary.py
git commit -m "feat: C2 lock Signal Board user-facing decision boundary"
```

---

### Task C2-5: Verification Documentation

**Files:**
- Create: `docs/verification/C2_VERIFICATION.md`
- Modify: root status document if one exists. If no root status document exists, do not create one only for C2.

- [ ] **Step 1: Create verification document**

Create `docs/verification/C2_VERIFICATION.md` with this structure:

```markdown
# C2 Signal Board Decision Boundary Verification

**Purpose:** Record C2 acceptance state, guarantees, non-guarantees, tests, and known boundaries.

**Status:** C2 completed and verified. C2 protects Signal Board user-facing decision boundaries. NOT UI redesign, NOT live trading, NOT profit proof.

## Accepted Commits

Before committing this document, run `git log --oneline -10` and paste the real C2 commit hashes here. Do not commit this file with missing or placeholder hashes.

## What C2 Proves

- Direct signal detail lookup cannot show unadmitted signals.
- Frontend signal type includes C1 admission metadata.
- User-facing Signal Board copy says the output is a validated planned signal, not buy/sell advice.
- User-facing Signal Board copy does not claim future profit, live trading readiness, one-click execution, or automatic trading.
- Signal Board detail/list pages have no mojibake markers covered by tests.

## What C2 Does Not Prove

- C2 does not redesign the Signal Board UI.
- C2 does not generate signals.
- C2 does not create action plans.
- C2 does not enable live trading.
- C2 does not guarantee future profit.

## Test Results

Record exact command output for:

- C2 focused tests
- C1 focused tests
- C0 focused tests
- B6 focused tests
- B5 full focused suite
- B4 regression
- full pytest
```

- [ ] **Step 2: Fill real commit hashes**

Use:

```powershell
git log --oneline -10
```

Add a markdown table under `## Accepted Commits` with the real C2 task commit hashes before committing. The table must contain no placeholder values.

- [ ] **Step 3: Run verification commands**

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/test_c2_signal_board_decision_boundary.py tests/test_signal_board_ux_polish.py tests/test_signal_api.py -q
.venv\Scripts\python.exe -m pytest tests/test_c1_signal_board_admission_risk.py tests/test_c1_admission_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_c0_admission_boundary.py tests/test_c0_anti_bypass.py -q
.venv\Scripts\python.exe -m pytest tests/test_b6_validation_flow.py tests/test_b6_c_admission_gate.py tests/test_b6_no_shortcuts.py -q
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_b4*.py" -v
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

- [ ] **Step 4: Commit verification document**

```powershell
git add docs/verification/C2_VERIFICATION.md
git commit -m "docs: C2 Signal Board decision boundary verification"
```

---

## Acceptance Criteria

C2 is accepted only if:
- `GET /api/signals/{signal_id}` does not return unadmitted or legacy signals.
- Public Signal Board API has no user-exposed audit bypass.
- Signal Board frontend type includes C1 admission metadata.
- Signal Board visible copy contains clear non-advice/non-execution disclaimer.
- Signal Board visible copy has no tested mojibake markers.
- No buy/sell recommendation, profit guarantee, live trading, broker, or auto-execution claim is introduced.
- C2, C1, C0, B6, B5, B4, and full pytest verification pass.
- `git status --short` is clean.
