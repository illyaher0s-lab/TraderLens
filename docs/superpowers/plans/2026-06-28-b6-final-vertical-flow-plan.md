# B6 Final Vertical Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the smallest real B-module V1 vertical flow required by the original B-module plan: A/B inputs become a frozen strategy validation record, pass through B3/B4/B5, require human promotion, and only true `prototype_passed` can enter the existing C/Signal Board boundary.

**Architecture:** B6 is a thin orchestration and boundary layer over existing B1-B5 and existing C files. It must not invent new trading rules, search parameters, bypass B3/B4/B5, or replace existing Signal Board code. It records an auditable validation run and proves the original V1 chain works at MVP level.

**Tech Stack:** Python 3.11, unittest/pytest, existing `contracts.strategy`, B3/B4/B5 services, `StrategyDB`, existing Signal Board contracts/API/DB.

---

## Scope From Original B Module Plan

B6 implements only the remaining MVP closure from the original six-phase plan:

```text
A/B frozen hypothesis input
-> StrategyDraft
-> ResearchProtocolSnapshot
-> B4 formal qualification and event backtest result
-> OOS reservation
-> ImmutableBacktestReport
-> deterministic Gate
-> plain-language explanation
-> human confirmation
-> StrategyPromotionReducer
-> prototype_passed
-> C admission check
```

B6 does not implement Serenity, a full UI, broker integration, automatic order placement, real-money trading, parameter optimization, or LLM research automation.

## Files And Responsibilities

- Create `backend/services/b6_validation_flow.py`
  - Thin orchestrator for the MVP vertical flow.
  - Accepts only frozen artifacts or explicit fixture-grade input objects.
  - Calls existing B2/B3/B4/B5 components instead of reimplementing their logic.
  - Returns a structured `B6ValidationRunResult`.

- Modify `backend/services/b5_oos_types.py`
  - Add frozen B6-local run result types if existing contracts cannot express run status and evidence references.
  - No trading recommendations or technical user parameters.

- Create `backend/services/c_admission_gate.py`
  - Minimal C boundary guard.
  - Allows existing Signal Board path to read only strategies whose lifecycle state is exactly `prototype_passed`.
  - Rejects `draft`, `candidate_for_prototype_passed`, `needs_review`, and `rejected`.

- Create `tests/test_b6_validation_flow.py`
  - End-to-end B6 flow tests using real services and in-memory DB.

- Create `tests/test_b6_c_admission_gate.py`
  - Tests that existing C/Signal Board can only admit true `prototype_passed`.

- Create `tests/test_b6_no_shortcuts.py`
  - Boundary tests proving no UI/API/LLM/user parameter shortcut bypasses the original B-module plan.

- Create `docs/verification/B6_VERIFICATION.md`
  - Documents exactly what B6 proves and what remains out of scope.

Do not modify without explicit escalation:

- `backend/services/backtest_time_cursor.py`
- `backend/services/future_data_guard.py`
- `strategy_core/backtest_engine.py`
- Existing Signal Board behavior except for adding an admission guard around it.

---

### Task 1: B6 Run Result Contract

**Files:**
- Modify: `backend/services/b5_oos_types.py`
- Test: `tests/test_b6_validation_flow.py`

- [ ] **Step 1: Write the failing contract test**

Add this test skeleton:

```python
def test_b6_run_result_is_frozen_and_has_no_trade_instruction_fields(self):
    from datetime import datetime
    from backend.services.b5_oos_types import B6ValidationRunResult

    result = B6ValidationRunResult(
        run_id="b6_run_001",
        strategy_revision_id="strat_001",
        protocol_snapshot_id="proto_001",
        report_id="report_001",
        gate_result_id="gate_001",
        explanation_id="expl_001",
        promotion_id=None,
        final_state="candidate_for_prototype_passed",
        status="completed",
        blocking_reason=None,
        created_at=datetime(2026, 6, 28, 10, 0, 0),
    )

    self.assertTrue(result.frozen)
    dumped = result.model_dump()
    self.assertNotIn("buy", dumped)
    self.assertNotIn("sell", dumped)
    self.assertNotIn("target_price", dumped)
    self.assertNotIn("stop_loss", dumped)

    with self.assertRaises(Exception):
        result.status = "changed"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b6_validation_flow.TestB6ValidationFlow.test_b6_run_result_is_frozen_and_has_no_trade_instruction_fields -v
```

Expected: FAIL because `B6ValidationRunResult` does not exist.

- [ ] **Step 3: Add minimal frozen type**

In `backend/services/b5_oos_types.py`, add:

```python
class B6ValidationRunResult(FrozenB5Contract):
    """Auditable B6 vertical validation run result."""
    run_id: str = Field(min_length=1)
    strategy_revision_id: str = Field(min_length=1)
    protocol_snapshot_id: str = Field(min_length=1)
    report_id: str | None = None
    gate_result_id: str | None = None
    explanation_id: str | None = None
    promotion_id: str | None = None
    final_state: Literal[
        "draft",
        "rejected",
        "needs_review",
        "candidate_for_prototype_passed",
        "prototype_passed",
    ]
    status: Literal["completed", "blocked", "failed"]
    blocking_reason: str | None = None
    created_at: datetime
    frozen: Literal[True] = True
```

- [ ] **Step 4: Run test to verify it passes**

Run the same focused test. Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b5_oos_types.py tests/test_b6_validation_flow.py
git commit -m "test: add B6 validation run contract"
```

---

### Task 2: B6 Orchestrator Skeleton Blocks Missing Prerequisites

**Files:**
- Create: `backend/services/b6_validation_flow.py`
- Test: `tests/test_b6_validation_flow.py`

- [ ] **Step 1: Write failing tests**

Add tests:

```python
def test_b6_flow_rejects_missing_strategy_draft(self):
    from backend.services.b6_validation_flow import B6ValidationFlow

    flow = B6ValidationFlow()

    with self.assertRaises(ValueError) as ctx:
        flow.run_minimal_validation(
            strategy_draft=None,
            protocol=None,
            manifest=None,
            universe=None,
            b4_qualification=None,
            b4_event_result=None,
            human_decision=None,
        )

    self.assertIn("StrategyDraft is required", str(ctx.exception))


def test_b6_flow_rejects_missing_b4_formal_qualification(self):
    flow = self._create_b6_flow_with_fixtures()

    with self.assertRaises(ValueError) as ctx:
        flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=None,
            b4_event_result=self.b4_event_result,
            human_decision=None,
        )

    self.assertIn("B4 formal qualification is required", str(ctx.exception))
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b6_validation_flow -v
```

Expected: FAIL because `B6ValidationFlow` does not exist.

- [ ] **Step 3: Implement minimal skeleton**

Create `backend/services/b6_validation_flow.py`:

```python
"""B6 final vertical flow orchestration."""
from __future__ import annotations

from datetime import datetime

from contracts.strategy import StrategyDraft
from backend.services.b5_oos_types import B6ValidationRunResult


class B6ValidationFlow:
    """Thin MVP flow over existing B1-B5 components."""

    def run_minimal_validation(
        self,
        *,
        strategy_draft: StrategyDraft | None,
        protocol,
        manifest,
        universe,
        b4_qualification,
        b4_event_result,
        human_decision: str | None,
    ) -> B6ValidationRunResult:
        if strategy_draft is None:
            raise ValueError("StrategyDraft is required for B6 validation flow")
        if protocol is None:
            raise ValueError("ResearchProtocolSnapshot is required for B6 validation flow")
        if manifest is None:
            raise ValueError("DataSnapshotManifest is required for B6 validation flow")
        if universe is None:
            raise ValueError("PointInTimeMembershipSnapshot is required for B6 validation flow")
        if b4_qualification is None:
            raise ValueError("B4 formal qualification is required for B6 validation flow")
        if b4_event_result is None:
            raise ValueError("B4 event backtest result is required for B6 validation flow")

        return B6ValidationRunResult(
            run_id=f"b6_{strategy_draft.strategy_revision_id}",
            strategy_revision_id=strategy_draft.strategy_revision_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            report_id=None,
            gate_result_id=None,
            explanation_id=None,
            promotion_id=None,
            final_state="draft",
            status="blocked",
            blocking_reason="orchestrator skeleton only",
            created_at=datetime.now(),
        )
```

- [ ] **Step 4: Run tests**

Expected: prerequisite tests pass.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b6_validation_flow.py tests/test_b6_validation_flow.py
git commit -m "feat: add B6 validation flow prerequisite boundary"
```

---

### Task 3: B6 Calls Existing B3/B4/B5 Boundary Validators

**Files:**
- Modify: `backend/services/b6_validation_flow.py`
- Test: `tests/test_b6_validation_flow.py`

- [ ] **Step 1: Write failing tests**

Add:

```python
def test_b6_flow_stops_on_failed_b4_qualification(self):
    flow = self._create_b6_flow_with_fixtures()
    failed_b4 = dict(self.b4_qualification)
    failed_b4["result"] = type("Qualification", (), {"qualification_status": "fail"})()

    with self.assertRaises(ValueError) as ctx:
        flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=failed_b4,
            b4_event_result=self.b4_event_result,
            human_decision=None,
        )

    self.assertIn("qualification failed", str(ctx.exception).lower())


def test_b6_flow_stops_on_b4_metadata_mismatch(self):
    flow = self._create_b6_flow_with_fixtures()
    mismatched = dict(self.b4_qualification)
    mismatched["data_snapshot_hash"] = "wrong_hash"

    with self.assertRaises(ValueError) as ctx:
        flow.run_minimal_validation(
            strategy_draft=self.strategy_draft,
            protocol=self.protocol,
            manifest=self.manifest,
            universe=self.universe,
            b4_qualification=mismatched,
            b4_event_result=self.b4_event_result,
            human_decision=None,
        )

    self.assertIn("mismatch", str(ctx.exception).lower())
```

- [ ] **Step 2: Run tests to verify failure**

Expected: FAIL because flow skeleton does not call `OOSEvaluationController`.

- [ ] **Step 3: Wire existing validator**

In `B6ValidationFlow.__init__`, accept or create:

```python
from backend.services.oos_evaluation_controller import OOSEvaluationController

def __init__(self, oos_controller: OOSEvaluationController | None = None):
    self.oos_controller = oos_controller or OOSEvaluationController()
```

Before returning:

```python
self.oos_controller.validate_b3_b4_prerequisites(
    protocol=protocol,
    manifest=manifest,
    universe=universe,
    b4_result=b4_qualification,
)
```

- [ ] **Step 4: Run B6 tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b6_validation_flow.py tests/test_b6_validation_flow.py
git commit -m "feat: wire B6 to B3-B4 prerequisite validation"
```

---

### Task 4: B6 Produces Report, Gate, And Explanation

**Files:**
- Modify: `backend/services/b6_validation_flow.py`
- Test: `tests/test_b6_validation_flow.py`

- [ ] **Step 1: Write failing test**

Add:

```python
def test_b6_flow_produces_report_gate_and_explanation(self):
    flow = self._create_b6_flow_with_fixtures()

    result = flow.run_minimal_validation(
        strategy_draft=self.strategy_draft,
        protocol=self.protocol,
        manifest=self.manifest,
        universe=self.universe,
        b4_qualification=self.b4_qualification,
        b4_event_result=self.b4_event_result,
        human_decision=None,
    )

    self.assertEqual(result.status, "completed")
    self.assertIsNotNone(result.report_id)
    self.assertIsNotNone(result.gate_result_id)
    self.assertIsNotNone(result.explanation_id)
    self.assertIn(
        result.final_state,
        ["rejected", "needs_review", "candidate_for_prototype_passed"],
    )
    self.assertNotEqual(result.final_state, "prototype_passed")
```

- [ ] **Step 2: Run to verify failure**

Expected: FAIL because flow still returns skeleton blocked result.

- [ ] **Step 3: Wire existing report/gate/explanation builders**

Use existing components:

```python
from backend.services.backtest_report_builder import BacktestReportBuilder
from backend.services.prototype_gate_v2 import PrototypeGateV2
from backend.services.gate_explanation_builder import GateExplanationBuilder
```

In `run_minimal_validation`, after prerequisite validation:

```python
report = self.report_builder.build_report(
    report_id=f"report_{strategy_draft.strategy_revision_id}",
    strategy_revision_id=strategy_draft.strategy_revision_id,
    protocol_snapshot_id=protocol.protocol_snapshot_id,
    strategy_config_hash=protocol.strategy_config_hash,
    data_snapshot_hash=protocol.data_snapshot_hash,
    gate_criteria_hash=protocol.gate_criteria_hash,
    oos_draw_index=1,
    shared_oos_window_id=protocol.shared_oos_window_id,
    b4_result=b4_event_result,
    adjustment_mode="qfq",
    adjustment_snapshot_fingerprint=manifest.adjustment_factor_fingerprint,
)
gate_result = self.gate.evaluate(report, protocol.gate_criteria_hash)
explanation = self.explanation_builder.build_explanation(report.report_id, gate_result)
```

Return `B6ValidationRunResult` with IDs and `final_state=gate_result.verdict`.

- [ ] **Step 4: Run B6 tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b6_validation_flow.py tests/test_b6_validation_flow.py
git commit -m "feat: produce B6 report gate and explanation"
```

---

### Task 5: B6 Requires Human Approval For Promotion

**Files:**
- Modify: `backend/services/b6_validation_flow.py`
- Test: `tests/test_b6_validation_flow.py`

- [ ] **Step 1: Write failing tests**

Add:

```python
def test_b6_flow_candidate_without_human_approval_is_not_prototype_passed(self):
    flow = self._create_b6_flow_with_fixtures()

    result = flow.run_minimal_validation(
        strategy_draft=self.strategy_draft,
        protocol=self.protocol,
        manifest=self.manifest,
        universe=self.universe,
        b4_qualification=self.b4_qualification,
        b4_event_result=self.b4_event_result,
        human_decision=None,
    )

    self.assertNotEqual(result.final_state, "prototype_passed")
    self.assertIsNone(result.promotion_id)


def test_b6_flow_human_reject_never_promotes(self):
    flow = self._create_b6_flow_with_fixtures()

    result = flow.run_minimal_validation(
        strategy_draft=self.strategy_draft,
        protocol=self.protocol,
        manifest=self.manifest,
        universe=self.universe,
        b4_qualification=self.b4_qualification,
        b4_event_result=self.b4_event_result,
        human_decision="reject",
    )

    self.assertNotEqual(result.final_state, "prototype_passed")
    self.assertIsNone(result.promotion_id)
```

- [ ] **Step 2: Run tests**

Expected: Current candidate/no-human behavior may pass, but human reject must be explicitly locked.

- [ ] **Step 3: Add explicit human decision boundary**

In `run_minimal_validation`:

```python
if human_decision not in (None, "approve", "reject"):
    raise ValueError("human_decision must be None, 'approve', or 'reject'")

promotion_id = None
final_state = gate_result.verdict
if gate_result.verdict == "candidate_for_prototype_passed" and human_decision == "approve":
    final_state = "prototype_passed"
    promotion_id = f"promotion_pending_reducer_{strategy_draft.strategy_revision_id}"
```

Do not write lifecycle state in this task unless using `StrategyPromotionReducer` with a real DB fixture. If not using reducer, label promotion as pending and add Task 6 for reducer-backed promotion.

- [ ] **Step 4: Run tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b6_validation_flow.py tests/test_b6_validation_flow.py
git commit -m "feat: enforce B6 human approval boundary"
```

---

### Task 6: Reducer-Backed Promotion Path

**Files:**
- Modify: `backend/services/b6_validation_flow.py`
- Test: `tests/test_b6_validation_flow.py`

- [ ] **Step 1: Write failing test**

Add an in-memory DB fixture and test:

```python
def test_b6_flow_uses_strategy_promotion_reducer_for_prototype_passed(self):
    flow = self._create_b6_flow_with_db_fixtures()

    result = flow.run_minimal_validation(
        strategy_draft=self.strategy_draft,
        protocol=self.protocol,
        manifest=self.manifest,
        universe=self.universe,
        b4_qualification=self.b4_qualification,
        b4_event_result=self.b4_event_result,
        human_decision="approve",
    )

    if result.final_state == "prototype_passed":
        self.assertIsNotNone(result.promotion_id)
        state = self.strategy_db.get_latest_lifecycle_state(self.strategy_draft.strategy_revision_id)
        self.assertEqual(state.state, "prototype_passed")
```

- [ ] **Step 2: Run to verify failure**

Expected: FAIL if flow does not store report/gate/confirmation and call reducer.

- [ ] **Step 3: Wire optional DB-backed promotion**

Add optional dependencies:

```python
from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer
from contracts.strategy import HumanPromotionConfirmation
```

When `strategy_db` is provided:

```python
self.strategy_db.store_backtest_report(report)
self.strategy_db.store_gate_result(gate_result)
if gate_result.verdict == "candidate_for_prototype_passed" and human_decision == "approve":
    confirmation = HumanPromotionConfirmation(...)
    self.strategy_db.store_human_confirmation(confirmation)
    promotion = self.promotion_reducer.promote_to_prototype_passed(...)
    promotion_id = promotion.promotion_id
    final_state = "prototype_passed"
```

Do not bypass reducer. If reducer rejects, let the exception fail loud.

- [ ] **Step 4: Run B6 tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b6_validation_flow.py tests/test_b6_validation_flow.py
git commit -m "feat: connect B6 promotion through reducer"
```

---

### Task 7: C Admission Gate For Existing Signal Board

**Files:**
- Create: `backend/services/c_admission_gate.py`
- Test: `tests/test_b6_c_admission_gate.py`

- [ ] **Step 1: Write failing tests**

Add:

```python
def test_c_admission_rejects_non_prototype_passed_states(self):
    from backend.services.c_admission_gate import CAdmissionGate

    gate = CAdmissionGate()

    for state in ["draft", "rejected", "needs_review", "candidate_for_prototype_passed"]:
        with self.subTest(state=state):
            with self.assertRaises(ValueError):
                gate.require_prototype_passed(
                    strategy_revision_id="strat_001",
                    lifecycle_state=state,
                )


def test_c_admission_accepts_only_prototype_passed(self):
    from backend.services.c_admission_gate import CAdmissionGate

    gate = CAdmissionGate()
    result = gate.require_prototype_passed(
        strategy_revision_id="strat_001",
        lifecycle_state="prototype_passed",
    )

    self.assertEqual(result["strategy_revision_id"], "strat_001")
    self.assertEqual(result["admission_status"], "accepted")
```

- [ ] **Step 2: Run tests to verify failure**

Expected: FAIL because `CAdmissionGate` does not exist.

- [ ] **Step 3: Implement minimal guard**

Create:

```python
"""C module admission guard for B-validated strategies."""
from __future__ import annotations


class CAdmissionGate:
    """Allow Signal Board admission only for true prototype_passed strategies."""

    def require_prototype_passed(self, *, strategy_revision_id: str, lifecycle_state: str) -> dict:
        if lifecycle_state != "prototype_passed":
            raise ValueError(
                f"Strategy '{strategy_revision_id}' is not prototype_passed; "
                f"C module admission rejected for state '{lifecycle_state}'"
            )
        return {
            "strategy_revision_id": strategy_revision_id,
            "admission_status": "accepted",
        }
```

- [ ] **Step 4: Run tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/c_admission_gate.py tests/test_b6_c_admission_gate.py
git commit -m "feat: add C admission gate for prototype strategies"
```

---

### Task 8: B6 Shortcut And No-UI/API Boundary Tests

**Files:**
- Create: `tests/test_b6_no_shortcuts.py`
- Modify only if tests reveal real violations.

- [ ] **Step 1: Write boundary tests**

Add tests:

```python
def test_b6_has_no_ui_dependency(self):
    import inspect
    import backend.services.b6_validation_flow as flow_module

    source = inspect.getsource(flow_module).lower()
    self.assertNotIn("frontend", source)
    self.assertNotIn("react", source)
    self.assertNotIn("page.tsx", source)


def test_b6_has_no_external_broker_or_live_api_dependency(self):
    import inspect
    import backend.services.b6_validation_flow as flow_module

    source = inspect.getsource(flow_module).lower()
    forbidden = ["broker", "live_trading", "order_submission", "real_time_feed"]
    for term in forbidden:
        self.assertNotIn(term, source)


def test_b6_rejects_user_supplied_technical_parameters(self):
    from backend.services.b6_validation_flow import B6ValidationFlow

    flow = B6ValidationFlow()
    with self.assertRaises(ValueError):
        flow.run_minimal_validation(
            strategy_draft=None,
            protocol=None,
            manifest=None,
            universe=None,
            b4_qualification=None,
            b4_event_result=None,
            human_decision="approve",
            user_gate_thresholds={"min_sharpe": 0.1},
        )
```

- [ ] **Step 2: Run tests**

Expected: the third test should fail until the flow signature explicitly rejects unexpected kwargs.

- [ ] **Step 3: Add explicit kwargs rejection**

Change the signature to include:

```python
**unexpected_user_parameters,
```

At the top:

```python
if unexpected_user_parameters:
    raise ValueError(
        "B6 validation flow does not accept user-supplied technical parameters"
    )
```

- [ ] **Step 4: Run B6 tests**

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add backend/services/b6_validation_flow.py tests/test_b6_no_shortcuts.py
git commit -m "test: lock B6 shortcut boundaries"
```

---

### Task 9: B6 Verification Documentation

**Files:**
- Create: `docs/verification/B6_VERIFICATION.md`

- [ ] **Step 1: Create verification document**

Document must include:

```markdown
# B6 Final Vertical Flow Verification

Status: MVP vertical flow verified. This is not a full Serenity workflow, not UI completion, not live trading, not a future profit guarantee, and not automatic promotion.

Accepted commits:
- Task 1:
- Task 2:
- Task 3:
- Task 4:
- Task 5:
- Task 6:
- Task 7:
- Task 8:

What B6 proves:
- B1-B5 can be called as one minimal validation flow.
- B3/B4 prerequisites are enforced.
- B5 report/Gate/explanation are produced.
- Human approval is required before reducer-backed promotion.
- C admission accepts only true prototype_passed.

What B6 does not prove:
- No full UI.
- No external live API.
- No broker execution.
- No complete Serenity autonomous research flow.
- No future profit guarantee.

Test record:
- B6 focused:
- B5 focused:
- B4 regression:
- full pytest:
```

- [ ] **Step 2: Run danger wording scan**

Run:

```powershell
Select-String -Path docs\verification\B6_VERIFICATION.md -Pattern "profit proven|ready for live trading|production ready|promotion approved|Gate passed" -CaseSensitive:$false
```

Expected: no matches.

- [ ] **Step 3: Commit**

```powershell
git add docs/verification/B6_VERIFICATION.md
git commit -m "docs: verify B6 final vertical flow"
```

---

## Final Verification Required

After all tasks:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b6_validation_flow tests.test_b6_c_admission_gate tests.test_b6_no_shortcuts -v
.venv\Scripts\python.exe -m unittest tests.test_b5_oos_budget tests.test_b5_oos_controller tests.test_b5_report_builder tests.test_b5_cost_stress tests.test_b5_control_comparison tests.test_b5_gate_v2 tests.test_b5_gate_explanation tests.test_b5_promotion_boundary tests.test_b5_vertical_flow tests.test_b5_compatibility -v
.venv\Scripts\python.exe -m unittest tests.test_b4_adjustment_snapshot tests.test_b4_ashare_fill_constraints tests.test_b4_b3_integration tests.test_b4_canary_qualification tests.test_b4_compatibility tests.test_b4_delisting_liquidation tests.test_b4_event_backtest_loop tests.test_b4_future_data_guard tests.test_b4_normalization_guard tests.test_b4_time_cursor
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
```

Acceptance requires:

- B6 focused tests pass.
- Existing B5 focused tests pass.
- B4 131-test regression passes.
- Full pytest passes.
- `git status --short` is clean.
- No B6 code imports frontend, broker, Signal Board action generation, or LLM Gate logic.

## Stop Conditions

Stop and escalate if implementation appears to require:

- asking the user to choose technical parameters;
- adding UI before the backend flow has stable artifacts;
- using external live API data outside B3 snapshots;
- allowing C to read anything other than `prototype_passed`;
- making Gate write lifecycle state;
- weakening B3/B4/B5 boundaries;
- generating buy/sell advice in B6.
