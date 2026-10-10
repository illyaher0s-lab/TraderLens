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

---

## Active addendum: B6 validation task v2 / B5 evidence admission (2026-08-18)

This addendum is the active implementation plan for the new B5-bound task contract. It is additive to the historical V1 plan above. It does not authorize a production one-shot, worker, OOS, Gate, Promotion, Signal, Git operation, or rewrite of prior artifacts. Where the historical V1 text describes automatic or human Promotion as part of the old vertical-flow scope, the current B6 runtime contract controls: B6 validation writes no Promotion; Promotion is a separate later human-confirmation transaction.

**Goal:** Add the smallest durable v2 B6 task path that binds a verified B5 bundle by exactly `b5_bundle_id` and `b5_bundle_manifest_sha256`, while retaining v1 read compatibility and keeping task creation at zero OOS side effects.

**Architecture:** Reuse `B6ValidationTask`, `StrategyDB`, the existing B5 verifier, the existing one-shot admission caller, and the current B6 worker/flow unchanged. Add only the v2 fields, one additive SQLite migration, one exact `StrategyDB` create-or-get method, and the caller admission branch. Do not duplicate four B5 result references in the task, add a new runner/framework/dependency, change data/strategy parameters, or precompute anything.

**Tech Stack:** Python 3.11, Pydantic, SQLite, existing `StrategyDB`, `unittest`; focused commands only. No full pytest/build is authorized by this plan.

### Acceptance matrix and fixed boundaries

| Case | Required result | Allowed writes | Forbidden effects |
|---|---|---|---|
| v1 historical row | Loads with version `v1` and null/absent B5 fields | None | No in-place upgrade or B5 claim |
| v2 missing/paired-field error | Pydantic or admission fail-loud | None | No task, protocol, ledger, OOS, report, Gate |
| B5 missing/tampered/lineage mismatch | Existing typed unavailable/hard block before task insert | Existing provenance/audit behavior only where already authorized | No task/protocol/OOS write |
| v2 exact first admission | One queued task, `b6_task_created=true` | One StrategyDB task row | No ledger read/reserve/start/consume, worker, report, Gate, Promotion, Signal |
| v2 exact retry/concurrent winner | Same durable winner and its current legal status, `b6_task_reused=true` or concurrent equivalent | No second row | No overwrite or silent conflict |
| same key with any immutable mismatch | Identity conflict fail-loud | No mutation of winner | No `INSERT OR IGNORE` suppression |
| valid queued task after admission | Stop at queued task | Task row only | Do not call B6 worker/flow or OOS |

The v2 `task_key` canonical object is exactly the seven fields specified in the amended B6 spec. Serialization is sorted-key compact JSON with `ensure_ascii=False`, UTF-8 encoding, and lowercase SHA-256. The two B5 fields are the only new frozen B5 values. The B5 manifest must retain `authorization_scope="v3_b5_contract_fixture_only"` and `not_authorized_for_b6_oos_gate_promotion_signal=true`.

### Phase 1 — v2 contract and task-key RED → GREEN

**Files:**

- Modify `contracts/b6_task.py`.
- Modify the focused existing contract/SQLite test file `tests/test_b6_task_atomic_claim.py`.

**RED:** Add and run these tests separately before changing the model:

1. `TestB6TaskV2Contract.test_v2_requires_paired_b5_fields_and_lowercase_sha` — reject missing pair, one-sided pair, uppercase/short/non-hex SHA, empty/path-like bundle ID, and extra payload fields. Expected failure reason before implementation: the current model has no B5 fields/validators.
2. `TestB6TaskV2Contract.test_v2_task_key_includes_b5_identity_and_version` — build the exact seven-field canonical object and assert the expected compact JSON bytes, lowercase digest, and inequality with the v1 key. Expected failure reason: current task contract has only v1 identity.
3. `TestB6TaskV2Contract.test_v1_task_remains_readable_without_b5_fields` — validate a legacy task with absent B5 fields and assert version `v1` plus null B5 values. This is a characterization test and must remain green.

Run separately with:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_atomic_claim.TestB6TaskV2Contract.test_v2_requires_paired_b5_fields_and_lowercase_sha -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_atomic_claim.TestB6TaskV2Contract.test_v2_task_key_includes_b5_identity_and_version -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_atomic_claim.TestB6TaskV2Contract.test_v1_task_remains_readable_without_b5_fields -v
```

The first two must RED for the stated missing-v2-contract reason; the v1 characterization must not be weakened. If a RED is caused by a different root, stop.

**GREEN:** Add only the two Pydantic fields, the paired-field/version validation, the exact SHA validation, and the local canonical v2 key helper needed by the existing contract convention. Keep `extra="forbid"` and frozen behavior. Re-run the same three commands. Do not alter the B5 manifest or production data.

### Phase 2 — additive schema and exact create-or-get RED → GREEN

**Files:**

- Create `backend/db/migrations/migration_003_add_b5_binding_to_b6_tasks.py`.
- Modify `backend/db/strategy.py` (`_run_migrations`, the B6 task CRUD area, and the existing row loader only as required for v2 columns).
- Modify `tests/test_b6_task_atomic_claim.py` and `tests/test_b6_runtime_persistence_kernel.py`.

**RED:** Use temporary file-backed SQLite databases and separate connections where concurrency is tested. Add and run each case separately:

1. `TestB6TaskV2Persistence.test_fresh_schema_has_b5_binding_columns` — current schema has no additive columns.
2. `TestB6TaskV2Persistence.test_legacy_v1_row_loads_with_null_b5_binding` — create a v1 row, apply migration, and assert no rewrite.
3. `TestB6TaskV2Persistence.test_v2_create_or_get_returns_created_then_exact_reuse` — first call returns one queued winner/created; a retry with a different `created_at` returns the same winner/reused.
4. `TestB6TaskV2Persistence.test_existing_lifecycle_state_does_not_change_identity` — after the winner is claimed or otherwise moved to a legal lifecycle state, the same immutable v2 admission identity returns that winner without conflict.
5. `TestB6TaskV2Persistence.test_immutable_identity_mismatch_fails_loud` — same key with a changed `task_id`, strategy/protocol identity, B5 bundle ID, or B5 manifest SHA raises the contract conflict and leaves the winner unchanged.
6. `TestB6TaskV2Persistence.test_create_failure_rolls_back_task_row` — inject failure before commit and assert no partial row.
7. `TestB6TaskV2Persistence.test_concurrent_v2_create_returns_one_winner` — two real SQLite connections converge to one exact queued row; the second writer waits, then reads the committed winner.

Each RED command must be its own command, using the exact node name. The expected pre-GREEN reason is missing migration/create-or-get exactness, not an OOS or worker failure. If a test touches an OOS table or ledger API, stop and correct the test design before implementation.

**GREEN:**

1. Add the migration as additive, idempotent `ALTER TABLE ... ADD COLUMN` guarded by `PRAGMA table_info`, preserving v1 rows and rolling back the migration transaction on error. Register it after migration 002; do not edit migration 002.
2. Add `StrategyDB.create_or_get_b6_task(task: B6ValidationTask) -> tuple[B6ValidationTask, bool]` for v2 only. Validate the requested new-admission shape first (`queued`, no blocking/claim/completion fields), then use one short `BEGIN IMMEDIATE`: select by task key; insert with ordinary `INSERT` when absent; re-read and validate columns/payload plus the exact immutable identity before commit; and commit only after all checks pass. The second SQLite writer waits for the first and then selects the committed winner. A unique conflict that is not the already-read same-key winner, or any immutable mismatch, raises a clear identity conflict; no silent `INSERT OR IGNORE` path is allowed. Do not compare retry `created_at`, lifecycle status, blocking fields, claim time, completion time, or full payload bytes.
3. Preserve the old `create_b6_task` and v1 row loading for compatibility; do not rewrite historical payloads.

Re-run the six focused tests, then run these regressions separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_atomic_claim -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_runtime_persistence_kernel -v
```

Required evidence is exact pass/fail/error count, duration, and any warning. A migration, rollback, or concurrent-winner failure is a hard stop; do not add a second correction in this phase.

### Phase 3 — one-shot B5 admission and queued task RED → GREEN

**Files:**

- Modify `scripts/run_v3_task4_once.py` only at the existing verified B4/B5/protocol materialization boundary.
- Modify `tests/test_run_v3_task4_once.py` using the real caller path and isolated file-backed databases/fixtures.
- Do not modify `backend/services/b6_validation_flow.py`; its reserve/start/terminal boundaries remain downstream and unchanged.

**RED:** Add and run separately:

1. `TestTask7B5Admission.test_b5_admission_creates_queued_v2_task_without_oos` — with exact verified B4/B5/criteria/protocol evidence, the current caller stops at missing task and does not create the v2 row.
2. `TestTask7B5Admission.test_exact_b5_task_retry_reuses_queued_task` — two real caller invocations return one task ID/key and one database row; current caller has no create-or-get branch.
3. `TestTask7B5Admission.test_b5_admission_precedes_protocol_freezer_for_missing_or_invalid_bundle` — missing or tampered B5 returns the existing unavailable/hard-block result before protocol/task creation, with no B6 or OOS rows.
4. `TestTask7B5Admission.test_b4_b5_lineage_mismatch_blocks_before_protocol_freezer` — B4/B5 lineage mismatch returns the existing unavailable/hard-block result, leaves task count zero, and does not reach protocol/task creation.
5. `TestTask7B5Admission.test_task_admission_does_not_instantiate_or_read_oos_ledger` — assert all seven protected/OOS tables remain at zero in the isolated database and the caller never invokes worker/flow boundaries. This must use a real caller and transparent observations, not a mock of the unit under test.

The valid fixture must use the exact verified B5 bundle identity and retain the two fixture-only/not-authorized disclosure fields. The test must not copy four result hashes into a task payload or change the bundle manifest. Expected RED is the current `b6_validation_task_missing` response/no task row.

**GREEN:** After the already verified criteria, B4, B5, and exact `b6_coverage_bound` protocol evidence is available, call the existing B5 verifier result and the v2 `StrategyDB.create_or_get_b6_task` method before any worker/OOS path. If protocol is absent, preserve the current `b6_protocol_missing` stop and create no task. If protocol and all evidence are valid, create or reuse only a queued v2 task and return deterministic admission evidence: `b6_task_created`/`b6_task_reused`, task ID/key, `task_contract_version="v2"`, both B5 refs, `status="queued"`, and no OOS authorization. Do not call `B6ValidationFlow.run_minimal_validation`, `reserve_oos_draw`, `start_execution`, or any report/Gate/Promotion/Signal path.

Run separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_b5_admission_creates_queued_v2_task_without_oos -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_exact_b5_task_retry_reuses_queued_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_b5_admission_precedes_protocol_freezer_for_missing_or_invalid_bundle -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_b4_b5_lineage_mismatch_blocks_before_protocol_freezer -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_task_admission_does_not_instantiate_or_read_oos_ledger -v
```

Then run the focused caller regression, not the full suite:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile scripts/run_v3_task4_once.py contracts/b6_task.py backend/db/strategy.py backend/db/migrations/migration_003_add_b5_binding_to_b6_tasks.py
```

Any B5 verifier bypass, protocol rewrite, task duplication, OOS read/reserve/start/consume, or unexpected worker/report/Gate call is an immediate stop.

### Phase 4 — focused review and separately authorized production task-creation preflight

**Files:** no additional production files are authorized. Tests may only be adjusted for an evidenced same-root mechanical error in the files above; a new independent root stops the phase.

Before any production invocation, review the exact diff against this addendum and run only the focused Phase 1–3 commands. Confirm the B5 bundle manifest/sidecars and B4 artifact are unchanged, the B5 authorization disclosure remains fixture-only/not-authorized, and v1 rows are unchanged. Confirm the task admission response contains no four-result duplication and no OOS credential.

A future production task-creation preflight requires separate authorization. If authorized later, it may use the existing one-shot caller once against the verified B4/B5/protocol inputs, may create/reuse one queued v2 task, and must stop before worker claim and before all OOS read/reserve/start/consume/report/Gate/Promotion/Signal operations. It must post-check the seven-table counts, task identity/lineage, process count, artifact hashes, and `_tmp_coverage_scan_result.json`. It is not a B6 validation run and is not an OOS or Gate authorization.

### Implementation hard stops and handoff

Stop on any RED with a reason other than the stated missing behavior, any GREEN failure, any second independent root, any schema rewrite, any historical v1 mutation, any B5 manifest security-field change, any task-key field drift, any OOS access, or any production artifact change. No Git/worktree/commit/reset/checkout/restore/cleanup operation is part of this plan. The plan is review-ready only after the focused evidence above; it does not claim implementation complete.

The later Gate/decision-card work must explicitly display **market movement vs strategy excess (Alpha)**. That is a downstream acceptance item only and is not implemented here.

## Active addendum: Phase5E criteria evaluator source boundary and controlled lineage rebuild (2026-08-23)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` to execute this addendum task-by-task. Do not use Git, worktrees, commits, reset, checkout, restore, cleanup, or any production OOS action.

**Goal:** Replace the over-broad criteria source binding with a stable production-only effective-criteria surface, publish a new immutable criteria v2 chain, and prepare an auditable explicit-task worker without touching the old queued task or consuming OOS.

**Architecture:** `backend/services/prototype_gate_criteria_surface.py` owns only the six frozen effective blocking categories and maximum verdict aggregation. `PrototypeGateV2` retains same-draw/read-audit/Alpha/report identity validation. A versioned criteria publisher/verifier creates v2 identities that include criteria content, evaluator source/algorithm identity, and contract version; the resulting supplement, protocol, B4, B5 results/bundle, and B6 task are rebuilt in dependency order. A prepared supplement token is verified after claim but before the single ledger-state read and is consumed exactly once after start.

**Tech Stack:** Python 3.11, Pydantic, canonical UTF-8 JSON, SHA-256, existing SQLite/StrategyDB, existing immutable publishers/verifiers, existing B4 engine and B6 worker. Focused `pytest`/`unittest` only; no full build.

### Phase5E acceptance matrix and global stop rules

| Boundary | Required evidence | Forbidden effect |
|---|---|---|
| Stable evaluator | Six-condition equivalence, deterministic issue order, maximum verdict, no Promotion | Same-draw parser/read-audit logic in the surface |
| Criteria v2 | Source/algorithm/version-covered ID, v2 envelope, v1 history untouched, write-once conflict | Overwrite or sidecar repair of v1 |
| New lineage | New criteria → v2 supplement/protocol → B4 → four B5 results/bundle → new task | Reusing an old artifact with a changed binding |
| Prepared execution | Supplement verifier exactly once in second preflight, token before ledger read, token consumed after start | First verification after start, second draw, TOCTOU fallback |
| Operations | JSONL stderr progress, canonical stdout result, consistency backup before claim, explicit recovery matrix | Latest scan, polling, automatic retry, user OOS parameters |
| Production boundary | At most one publisher/verifier per new immutable artifact and a later independent authorization | OOS read/reserve/start/consume, report/Gate, Promotion, Signal during implementation |

Every RED must fail for the named missing behavior. A different failure, a GREEN failure, a second correction in the same phase, an artifact/security-field change, a production DB write, or any OOS operation is an immediate stop. A publisher or verifier that has run once is never retried in that authorization.

### Phase5E1 — Stable evaluator and equivalence TDD

**Files:**

- Create: `backend/services/prototype_gate_criteria_surface.py`.
- Modify: `backend/services/prototype_gate_v2.py` only to pass the ten frozen effective fields to the stable surface and retain same-draw/report/read-audit checks locally.
- Test: `tests/test_v3_gate_criteria.py`, `tests/test_b6_alpha_report_gate_contract.py`.

- [ ] **Step 1: Write the RED tests.** Add exact nodes:
  - `test_effective_criteria_surface_matches_frozen_six_conditions` — import the new public types/function and exercise each blocking category, mixed-condition order, and no-block verdict; expected RED is missing module/symbol.
  - `test_effective_criteria_surface_never_emits_prototype_passed_or_promotion` — expected RED is missing surface.
  - `test_same_draw_revalidation_remains_in_prototype_gate` — a v2 result with a changed audit or Alpha must still fail through `PrototypeGateV2`; expected RED is missing stable delegation boundary, not a relaxed assertion.
- [ ] **Step 2: Run each RED separately.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py::test_effective_criteria_surface_matches_frozen_six_conditions -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py::test_effective_criteria_surface_never_emits_prototype_passed_or_promotion -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_b6_alpha_report_gate_contract.py::test_same_draw_revalidation_remains_in_prototype_gate -q
```

Expected result is RED only for the absent surface/delegation. Any import, fixture, or unrelated contract error stops E1.

- [ ] **Step 3: Implement the minimum surface.** Define frozen `FrozenEffectiveCriteriaInput`, frozen `EffectiveCriteriaDecision`, `is_failed_result`, and `evaluate_effective_criteria` exactly as spec 12.1. Preserve the current six IDs, order, failure predicate, `rejected`/`candidate_for_prototype_passed` mapping, and no-Promotion boundary. Do not move same-draw parsing, read-audit verification, Alpha arithmetic, report identity, or Gate persistence into the new module.
- [ ] **Step 4: Run the same three nodes GREEN.** Each must pass with no warning that hides an assertion. Then run:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_alpha_report_gate_contract -v
```

E1 stops with the stable surface and existing v1 criteria artifacts unchanged. No production publisher or DB is opened.

### Phase5E2 — Criteria v2 identity, publisher, and verifier TDD in temporary roots

**Files:**

- Modify: `scripts/publish_v3_gate_criteria.py` with an explicit v2 builder/write-once path; retain the v1 path for history only.
- Modify: `scripts/verify_v3_gate_criteria.py` with separate v1/v2 verification and no v1-to-v2 fallback.
- Test: `tests/test_v3_gate_criteria.py`.

- [ ] **Step 1: Write RED tests in `tmp_path` only.** Add exact nodes:
  - `test_v2_snapshot_id_covers_kind_content_evaluator_and_contract`;
  - `test_v2_pair_envelope_uses_v2_snapshot_ids_and_content_hashes`;
  - `test_v2_verifier_rejects_v1_manifest_and_v1_verifier_rejects_v2`;
  - `test_v2_write_once_conflict_does_not_overwrite_existing_directory`.
  Expected RED is the current content-only ID/schema and absent v2 verifier branch.
- [ ] **Step 2: Run each RED as a separate command.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py::test_v2_snapshot_id_covers_kind_content_evaluator_and_contract -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py::test_v2_pair_envelope_uses_v2_snapshot_ids_and_content_hashes -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py::test_v2_verifier_rejects_v1_manifest_and_v1_verifier_rejects_v2 -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py::test_v2_write_once_conflict_does_not_overwrite_existing_directory -q
```

- [ ] **Step 3: Implement v2 only.** Use the spec 12.2 identity payload and canonical JSON rule. New v2 directories coexist with v1 directories; v1 manifests and sidecars are read-only history. Exact v2 manifest equality, source SHA, sidecars, contract version, evaluator surface, and envelope are required.
- [ ] **Step 4: Run the four RED nodes GREEN, then run the short module regression.**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_gate_criteria.py -q
```

E2 uses only temporary roots and source copies. It must not read `data/strategy.db`, open OOS data, or change `data/pit/prototype_gate_v2_criteria`.

### Phase5E3 — One criteria v2 publication and one verifier

**Files:** no new production files; use the E2 publisher/verifier and the existing criteria tests.

- [ ] **Step 1: Read-only pre-gate.** Confirm v1 gate/kill manifest hashes, v1 evaluator binding, current stable-surface SHA, absence of v2 targets, zero target processes, and DB/OOS baseline. Do not call the publisher until all values match the reviewed handoff.
- [ ] **Step 2: Publish once.** Run exactly:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.publish_v3_gate_criteria
```

Capture the two new v2 IDs, manifest hashes, and envelope hash. A non-zero exit or a non-v2 result stops E3; no retry.
- [ ] **Step 3: Verify once.** Run the v2-aware verifier against the criteria root exactly once:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_gate_criteria D:\Codex\TraderLens\data\pit\prototype_gate_v2_criteria
```

Require `status=valid`, exactly one v2 gate/kill pair, v1 directories unchanged, and no temporary target. A verifier failure stops the chain. This phase writes no DB and consumes no OOS.

### Phase5E4 — Sequential supplement, protocol, B4, and B5 lineage rebuild

Each substep has its own stop gate. The production operations below are future independently authorized lineage operations; they do not authorize a worker or OOS draw. Long B4/B5 operations must emit the E7 progress format or stop before execution.

#### Protocol multiplicity amendment and dependency gates

The `research_protocol_snapshots` table permits immutable old/new rows with the same `strategy_revision_id` and `protocol_profile="b6_coverage_bound"`. `protocol_snapshot_id` remains the primary-key identity and write-once conflict owner. The former migration-002 partial unique index `uq_protocol_b6_profile_per_revision` is removed by a new `migration_004`; the replacement `idx_protocol_b6_profile_per_revision` is nonunique and exists only for lookup. No generation/version column or general versioning platform is added.

Every production execution, publication, task, report, and Gate caller must use an explicit server-owned `protocol_snapshot_id`. No caller may use `latest`, `current`, revision-only selection, database order, `ORDER BY`, or `LIMIT 1` to choose a protocol. The only permitted revision/profile helper is a strict typed 0/1/>1 result: `protocol_snapshot_unavailable`, one exact validated row, or `protocol_snapshot_ambiguous`; it must fail loudly for ambiguity and never silently select a row. Existing exact-ID callers remain exact-ID callers.

The required migration contract is:

```sql
BEGIN IMMEDIATE;
DROP INDEX IF EXISTS uq_protocol_b6_profile_per_revision;
CREATE INDEX IF NOT EXISTS idx_protocol_b6_profile_per_revision
  ON research_protocol_snapshots(strategy_revision_id, protocol_profile);
COMMIT;
```

An exception rolls back the migration. It does not rebuild the table or modify rows, the primary key, triggers, or foreign keys. Fresh schema creation runs migration 002 and then 004; an upgrade applies 004 to the existing migration-002 schema without data loss. The old queued task/report foreign keys continue to bind the old explicit protocol, while a future task may bind the new explicit protocol under the same revision/profile. The existing revision-only `LIMIT 1` read in `scripts/run_v3_task4_once.py` must be removed or replaced by the strict helper during the migration phase; this is the only known unsafe selector.

The schema phase is split into independent gates before the existing supplement phase:

- **E4.1a — migration contract and temporary verification:** add and test migration 004 on fresh (002→004) and upgraded file-backed databases; prove two protocol rows, strict ambiguity, exact-ID reads, old task/report foreign keys, idempotency, rollback, and competing file-backed connections.
- **E4.1b — protocol owner temporary GREEN:** run the existing narrow owner against a temporary database only; it must build/validate the v2 candidate, exact-reuse an existing candidate, and never write the production database.
- **E4.1c — one production migration:** after E4.1a/b review, authorize the migration once; verify the old row/task and index/schema post-state read-only. A failure stops before durable protocol writing.
- **E4.1d — one new protocol durable write:** after E4.1c, authorize the existing narrow owner once; verify exact new-row persistence and old-row/task immutability. A failure stops before supplement publication.

The old owner and its tests remain unverified until the multiplicity migration and explicit-ID caller review are green; no artifact or production status may be called ready from the temporary owner alone.

The actual operation order is:

```text
criteria v2 verified
  -> pure deterministic candidate protocol payload/ID
  -> freezer v2 criteria-envelope TDD/verification
  -> immutable durable new protocol snapshot
  -> supplement publisher reads the durable protocol binding
  -> supplement publish/verify
  -> B4
  -> B5 four results/bundle
  -> new B6 task
```

There is no cycle: the canonical protocol identity excludes supplement identity, while the supplement binds the durable protocol ID and payload SHA. The E4.1 candidate is fixed as protocol ID `8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe` with `model_dump_json` payload SHA `2872d63578d66e6dfc02fd767c4061fd3e291bcb9bbd65f0f2409a4482f6e2a3`. Its only four diffs from the current protocol are `protocol_snapshot_id`, `gate_snapshot_id`, `kill_criteria_snapshot_id`, and `gate_criteria_hash`; every other formal, successor, coverage, scope, window, revision, strategy, data, and criteria-content field is exact-reused.

The current freezer still accepts only the v1 criteria-envelope calculation. It is the next stop gate; do not store the candidate protocol before its v2 TDD/verification is green. The durable protocol write is separately authorized, write-once, and exact; any failure rolls back and leaves the old protocol/task unchanged. Supplement v2 publisher/verifier work begins only after that durable write.

#### E4.1a Migration contract and temporary verification

**Files:** `backend/db/migrations/migration_004_allow_protocol_multiplicity.py`, `backend/db/strategy.py`, `tests/test_protocol_multiplicity_migration.py`, and the existing protocol persistence tests only where their migration-002 historical assertion must be updated.

- [ ] RED node `test_fresh_schema_requires_migration_004_for_protocol_multiplicity` proves the migration-002 partial unique index rejects a second same-revision/profile row in a temporary database.
- [ ] GREEN registers migration 004 after migration 003. It executes only the guarded `BEGIN IMMEDIATE`/drop-old-index/create-nonunique-index/commit sequence above and rolls back on failure. It is idempotent when the old index is absent and the new index already exists.
- [ ] RED/GREEN nodes `test_two_protocol_rows_share_revision_and_profile`, `test_same_protocol_id_conflict_is_exact`, `test_strict_revision_profile_lookup_returns_ambiguous`, `test_exact_protocol_id_read_is_unambiguous`, and `test_old_task_and_report_foreign_keys_survive_new_protocol` prove multiplicity, PK conflict ownership, strict 0/1/>1 helper semantics, exact-ID reads, and old/new FK coexistence.
- [ ] RED/GREEN nodes `test_migration_004_failure_rolls_back`, `test_migration_004_is_idempotent`, and `test_two_file_backed_connections_do_not_create_duplicate_protocol_ids` prove rollback, repeatability, and persistence/concurrency boundaries. No production database or OOS table is opened.

The revision/profile helper must expose a typed result with the exact reason codes `protocol_snapshot_unavailable` and `protocol_snapshot_ambiguous`; it must not expose a `first`, `latest`, or `limit_one` mode. The migration does not add a generation/version field and does not alter migration 002.

#### E4.1b Protocol identity preparation (temporary owner)

**Files:** `contracts/strategy.py`, `backend/services/research_protocol_freezer.py`, `tests/test_b6_protocol_contract.py`, `tests/test_b6_protocol_freezer.py`; modify only if RED proves existing fields cannot carry the v2 gate/kill IDs and envelope.

- [ ] RED node `test_b6_protocol_id_changes_for_v2_criteria_identity` proves the old protocol payload cannot satisfy the v2 snapshot/content/envelope binding.
- [ ] RED also records that the current freezer's v1 envelope calculation rejects the v2 schema/contract envelope before any store.
- [ ] GREEN uses existing `compute_b6_protocol_id` and `ResearchProtocolFreezer.freeze_b6_coverage_bound_protocol` with the v2 envelope fields; no new DB columns, strategy revision, data source, or threshold. Validate the candidate payload in a temporary file-backed DB first. Only after that focused GREEN and an independent authorization may `store_protocol_snapshot_exact` perform the one immutable write. A failed write or exact identity mismatch rolls back, leaves the old protocol/task unchanged, and stops before supplement publication.

Commands:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_protocol_contract.TestB6ProtocolContract.test_b6_protocol_id_changes_for_v2_criteria_identity -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_protocol_freezer -v
```

The existing strategy revision may be reused only after its canonical revision payload is rechecked and unchanged.

The production protocol write is not part of the TDD commands above. It is the separate E4.1d stop gate after the one-time E4.1c migration. It uses the exact candidate ID and payload, with write-once/exact comparison and raw read-only post-checks. No supplement publisher or verifier is run before that gate succeeds.

#### E4.1c Single production migration stop gate

After E4.1a temporary tests and E4.1b owner review are green, the migration is run once through the registered production migration owner. No inline database script is allowed. Preflight records the current row/index/trigger/FK inventory; post-gate raw SQLite read-only checks must show the old protocol and old task unchanged, the new nonunique index present, the former partial unique index absent, and all seven protected counts unchanged. Any failure stops before E4.1d; no retry or cleanup is allowed.

#### E4.1d Single new protocol durable-write stop gate

Only after E4.1c passes may the existing narrow protocol owner run once. It must verify criteria v2, build the candidate through the canonical freezer, compare the deterministic candidate ID/payload, store it with `store_protocol_snapshot_exact`, and read back the exact row. It must not use revision-only lookup, create a task, publish a supplement, or touch OOS. Exact retry is reuse; a same-ID payload conflict fails loudly. Post-gate checks prove two immutable protocol rows under the same revision/profile, the old task/report bindings are unchanged, and the protected seven-table/OOS counts are unchanged.

#### E4.2 Supplement publication and verification

**Files:** `scripts/publish_v3_execution_semantics.py`, `scripts/verify_v3_execution_semantics.py`, `tests/test_v3_execution_semantics.py`.

- [ ] RED node `test_v3_execution_semantics_binds_v2_criteria_and_protocol` must fail because the current builder uses the v1 criteria root/old protocol constants and requires the old durable protocol binding; this RED is run only after the new protocol write checkpoint exists in the temporary fixture.
- [ ] GREEN updates only the server-owned criteria/protocol/predecessor bindings and preserves the v3 source, cost, calendar, and authorization contracts. Run the focused module in temporary roots before production.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_execution_semantics.py::test_v3_execution_semantics_binds_v2_criteria_and_protocol -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_execution_semantics.py -q
```

After GREEN, and only after the separately authorized durable protocol checkpoint, publish the new supplement once with the existing publisher and verify its returned exact path once with the official module verifier. Capture supplement ID/manifest SHA. Any source, protocol, criteria, or predecessor mismatch stops E4.2; do not republish. The old supplement remains immutable.

#### E4.3 B4 artifact publication and verification

**Files:** `scripts/run_v3_b4_is_once.py`, `tests/test_run_v3_b4_is_once.py`, and only the existing B4 verifier path required by the new supplement binding.

- [ ] RED node `test_v3_b4_runner_binds_the_new_supplement_and_protocol` proves the old B4 identity is not accepted for the new chain.
- [ ] GREEN updates server-owned supplement/protocol constants or the existing explicit supplement argument, preserves IS window/data/read-bound behavior, and keeps the old B4 artifact untouched.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_run_v3_b4_is_once.py::test_v3_b4_runner_binds_the_new_supplement_and_protocol -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_run_v3_b4_is_once.py -q
```

After GREEN, run the B4 IS publisher once, capture its new artifact ID/manifest/event hashes, and call `verify_v3_b4_is_result` once against that exact directory. A long run must emit progress; any failure stops before B5.

#### E4.3b Successor semantic reconciliation and deterministic-exit gates

This amendment supersedes any earlier E4.3 wording that could be read as requiring old/new sequence-derived records, artifact bytes, `frozen_at`, or historical floating-point tails to be cross-generation exact. The current authority is the FormalPIT status contract plus the semantic matrix below. The structurally verified but semantically blocked checkpoint is `d3ae7d51690bfef4`, manifest `ad838cc4fa4714867a3a6179f11370b5e6dd842b696fecdacc0a45c5dcdb1b5c`, event `fa097edfbdc3e252b2ffcfe85a01da41d86d7e7e0c233fd0e469125f4f158307`.

This amendment adds no generation field, semantics registry, user parameter, data source, threshold, Promotion, or Signal behavior.

**Status contract:** R-only with a valid finite daily row is not full-day suspended and preserves reason R. When `open == down_limit`, a sell rejection is `limit_down`. S/P timing and no-daily/P3 behavior remains unchanged: S/P with missing timing or no daily is suspended; R-only with no daily is P3, not carry. Historical R-only `suspended` output is immutable predecessor evidence, not a reason to restore the old behavior.

**Deterministic gap:** `_exit_symbols` returns a set, and the only consumer must call `sorted(_exit_symbols(...))` before populating `pending_exits`. This is the sole permitted production change for this gap. It preserves the exit multiset, rank, holding, stop, quantity, price, cost, data-source, and parameter semantics. No generic sort framework is allowed.

**Successor acceptance:**

- Old/new history is compared by business multiset: symbol, side, signal date, execution date, quantity, price/fill price, and fill quantity; final positions and quantities must match.
- Reject identity must match by symbol, direction/side when present, date, and quantity/order identity. Only R-only/valid-daily/open-at-down-limit may explain `suspended` to `limit_down`.
- Sequence-derived IDs, lineage IDs/hashes, artifact/result IDs, manifest hashes, `frozen_at`, and historical floating-point accumulation tails are not cross-generation exact requirements.
- Frozen IS window, revision, protocol, formal snapshot, membership, calendar, data, strategy/cost identity, `future_violations=0`, and `read_audit.oos_read_count=0` remain hard requirements.
- Two independent temporary successor processes with different `PYTHONHASHSEED` values must be exact on order sequence/derived IDs, intents/fills/rejects, final cash/value, and read-audit summary/hash. Any new business multiset, cost, or read-bound difference stops the chain.

**Checkpoint 1 — integrated status/fill characterization.**

Files: `tests/test_task3b_formal_partition_adapter.py` and the existing fill-boundary test file. Add a real adapter-plus-fill node for R-only, valid daily, and `open == down_limit`; require `is_suspended=false`, `suspend_reason="R"`, `is_limit_down=true`, and sell rejection `limit_down`. Retain the existing S/P timing, suspended, and R-only/no-daily P3 assertions. Run the exact focused nodes in temporary/read-only-safe fixtures. This checkpoint must be green before the executor RED; it does not change production code.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_task3b_formal_partition_adapter.TestFormalPITPartitionAdapter.test_r_only_valid_daily_open_at_down_limit_is_not_suspended -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b4_ashare_fill_constraints.TestB4AshareFillConstraints.test_r_only_valid_daily_open_at_down_limit_rejects_limit_down -v
```

**Checkpoint 2 — multi-exit deterministic RED.**

Files: `strategy_core/v3_relative_strength_executor.py`, `tests/test_v3_relative_strength_executor.py`. Add a real multi-exit backtest case and an independent-process/hash-seed assertion. The current code must fail specifically because the set consumer does not define order. Assert the exit business multiset is unchanged and the expected stable key is symbol ascending. Do not mock the executor or replace the engine with a sequential imitation.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_relative_strength_executor.py::test_multi_exit_order_sequence_is_stable_across_hash_seeds -q
```

**Checkpoint 3 — minimal GREEN and temporary regression.**

Change only the one exit-consumer iteration to `sorted(...)`. Re-run the focused multi-exit nodes and compare two temporary processes with different `PYTHONHASHSEED`; require exact order IDs, intents, fills, rejects, final cash/value, and read-audit summary/hash. Any new business multiset, cost, or read-bound difference is an immediate stop. No B4 artifact or production root is written here.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_relative_strength_executor.py::test_multi_exit_order_sequence_is_stable_across_hash_seeds -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile strategy_core/v3_relative_strength_executor.py tests/test_v3_relative_strength_executor.py tests/test_task3b_formal_partition_adapter.py tests/test_b4_ashare_fill_constraints.py
```

**Checkpoint 4 — successor supplement.**

The executor source SHA change requires a new immutable supplement successor with predecessor `708dbfa1c5601113`; the old supplement remains untouched. In a temporary root, update only server-owned source binding, publish once, and verify once. After temporary GREEN, production supplement publish and official verify are each allowed once. A failure at either boundary stops without retry. Criteria, protocol, and revision remain unchanged; no B4 or B5 action occurs before this checkpoint passes.

**Checkpoint 5 — successor B4 binding and semantic gate.**

Update only the server-owned B4 supplement binding and direct fixtures required by the new supplement; run focused temporary binding verification first. Then, under separate authorization, publish and verify the successor B4 once each. Require the semantic acceptance above, including the R-only status exception, business multiset/final-position equality, deterministic successor repeatability, future violations zero, and OOS read count zero. A failure stops before E4.4; the old B4 remains immutable.

The successor sequence is therefore: integrated adapter/fill test → multi-exit/hash-seed RED → one-line executor GREEN → temporary supplement verification → one production supplement publish/verify → temporary B4 binding verification → one production B4 publish/verify → semantic acceptance. B5 four-result rebuild, new task admission, worker, OOS, Gate, Promotion, and Signal remain prohibited until the successor B4 semantic gate passes.

#### E4.4 B5 four-result and bundle rebuild

**Files:** existing B5 lineage constants/builders and only the directly failing publishers in dependency order: `scripts/publish_v3_b5_ledger_observations.py`, `backend/services/v3_b5_costs.py`, `scripts/publish_v3_b5_costs.py`, `backend/services/v3_b5_comparison.py`, `scripts/publish_v3_b5_comparisons.py`, `backend/services/v3_b5_bundle.py`, and `scripts/publish_v3_b5_bundle.py`; tests `tests/test_v3_b5_costs.py`, `tests/test_v3_b5_comparisons.py`, `tests/test_v3_b5_bundle.py`, and the ledger-observation focused suite.

- [ ] RED nodes must prove each existing result payload rejects the new B4/supplement/protocol/v2-envelope lineage before any bundle write. Do not replace expected lineage with the old values.
- [ ] Use these exact focused nodes for the four result boundaries: `test_v3_b5_costs_rebinds_new_protocol_and_supplement_lineage`, `test_v3_b5_comparisons_rebinds_new_b4_and_criteria_lineage`, `test_v3_b5_ledger_observations_rebinds_new_protocol_lineage`, and `TestV3B5Bundle.test_new_lineage_bundle_references_all_four_results`. Each RED must stop before a target directory is created.
- [ ] GREEN updates only server-owned lineage bindings. Reuse the existing source inventory/data/cost/comparison contracts; do not use B5 IS numbers as OOS values and do not add a strategy or cost parameter.
- [ ] Run each affected focused node separately, then publish each required B5 source result once in dependency order, publish the new bundle once, and verify the exact new bundle once. Required result references, B4 lineage, v2 criteria envelope, fixture-only scope, and not-authorized disclosure must all match. Any failure stops before E5.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_b5_costs.py::V3B5CostTests::test_v3_b5_costs_rebinds_new_protocol_and_supplement_lineage -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_b5_comparisons.py::TestV3B5Comparisons::test_v3_b5_comparisons_rebinds_new_b4_and_criteria_lineage -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_b5_ledger_observation.py::LedgerObservationTests::test_v3_b5_ledger_observations_rebinds_new_protocol_lineage -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_v3_b5_bundle.TestV3B5Bundle.test_new_lineage_bundle_references_all_four_results -v
```

The exact production publisher order is current verified B4, then `publish_v3_b5_ledger_observations`, then `publish_v3_b5_costs`, then `publish_v3_b5_comparisons`, and finally `publish_v3_b5_bundle`; each publisher and its official verifier is a single attempt, and the next command starts only after the prior result is independently verified. No source-inventory publisher is an extra reorderable stage in this chain. Existing source inventory is used only as an exact-compared server-owned input when required by the current lineage; it is never spliced from an old bundle or rewritten to make a current result pass.

No B6 task, OOS data, report, Gate, Promotion, or Signal is touched in E4; the B5 ledger-observation artifact is the explicitly ordered E4.4 output.

#### E4.4d Dependency-order and acceptance amendment (2026-08-26)

This amendment supersedes the earlier E4.4 sentence that placed costs before ledger observations or allowed a parallel/reordered chain. It also supersedes any interpretation that assembles a current bundle from old `9d388459df4d591e` or from absent current production targets. The frozen dependency graph is:

```text
current verified B4 cb41dd1dc207642b
  -> ledger observations: publish once, official verify once
  -> base/stress costs: publish once, official verify once, exact ledger binding
  -> benchmark/control comparisons: publish once, official verify once, exact ledger+cost binding
  -> bundle: pure assembly publish once, official verify once, exact four-current-result binding
```

The required current lineage remains protocol `8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe`, revision `6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc`, criteria envelope `94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738`, supplement `1aed70f1af38a191` / manifest `70e4dfa09f11cbafd5aebf76903ecb95ca6a491635d1d94b3d713db5481beac0`, and B4 `cb41dd1dc207642b` / manifest `3d35f4be75af2f4612a39215c640d148fd3ff369040300c87e70e9b136faa0e3` / event `0146052d1d2dd051546d7ae39262266d55c7dde74d95665231a027fc457bfe1a`. The old bundle remains immutable historical evidence and is invalid for current admission.

The clean temporary acceptance already completed before this amendment is recorded as one process, one fresh `TemporaryDirectory`, `596.917` seconds, `Ran 1`, `OK`: current B4 `cb41dd1dc207642b`; ledger `176` observations, `124` fills, and `read_audit.oos_read_count=0`; cost official verification `fill_count=124`; comparison official verification with explicit temporary upstream bindings; and bundle verification of four current results, current lineage, and the fixture-only/not-authorized disclosure. The temporary directory was cleaned, so temporary stage IDs and hashes were not recorded and must not be fabricated.

The programmatic comparison verifier keyword-only seam `cost_dir`/`observation_dir` is solely a trusted temporary-caller boundary. The comparison CLI still accepts only `artifact_dir` and uses server-owned defaults in production; no user-supplied cost, observation, lineage, window, or source path is added.

Production E4.4 is split into these hard stop gates:

1. **Preflight:** verify the current B4 and exact current lineage, record the current code/test SHAs and the raw SQLite baseline, confirm current B5 targets are absent, and confirm no target process or staging directory exists. This gate is read-only.
2. **Ledger gate:** run `python -m scripts.publish_v3_b5_ledger_observations` once, then run `python -m scripts.verify_v3_b5_ledger_observations <actual_dir>` once. Require the exact current lineage, 176 observations where the verified result reports that count, 124 fills, and `oos_read_count=0`.
3. **Cost gate:** only after ledger verification, run `python -m scripts.publish_v3_b5_costs` once, then `python -m scripts.verify_v3_b5_costs <actual_dir>` once. Require the exact ledger binding and verified manifest `fill_count=124`.
4. **Comparison gate:** only after cost verification, run `python -m scripts.publish_v3_b5_comparisons` once, then `python -m scripts.verify_v3_b5_comparisons <actual_dir>` once. Require exact ledger+cost bindings and verified benchmark/control payloads.
5. **Bundle gate:** only after comparison verification, run `python -m scripts.publish_v3_b5_bundle` once, then `python -m scripts.verify_v3_b5_bundle <actual_dir>` once. Require pure assembly of four current verified results, exact lineage, write-once identity, and both unchanged fixture-only/not-authorized disclosure fields.

Every publisher/verifier pair is one attempt. Any identity, lineage, mathematical, OOS/read-audit, sidecar, or write-once conflict stops the chain without retry, cleanup, fallback, old-bundle splicing, or Task7/new-task action. Production B5 completion is a prerequisite for any later Task7 admission, new task, worker, OOS ledger/state/reservation, report, Gate, Promotion, or Signal; none is authorized by E4.4d.

The read-only preflight snapshot for this amendment recorded B5 implementation/test SHAs in the companion spec, database `quick_check=ok`, `foreign_key_check=[]`, counts `(2,1,0,0,0,0,0)`, the sole old task queued against protocol `6f7cbdcdeb26f8cdd2611a5450dbab3ff22544b6a66ec8539f5cab9151329111`, OOS tables at zero, and absent current targets `acc628b961f2da3b`, `53494507dff2f203`, and `3ad1193b3b4a8c0c` (comparison/bundle target). No production action is authorized or executed in this documentation amendment.

### Phase5E5 — New B6 task admission; old task untouched

**Files:** `scripts/run_v3_task4_once.py`, `tests/test_run_v3_task4_once.py`; reuse `contracts/b6_task.py` and `backend/db/strategy.py` without changing their v2 identity contract unless a focused RED proves a direct incompatibility.

- [ ] RED nodes:
  - `test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task`;
  - `test_old_queued_task_is_not_selected_by_new_admission`;
  - `test_new_task_admission_has_zero_oos_side_effects`.
  Expected RED is the old frozen B4/B5/protocol constants or absence of the new admission binding, not an OOS or worker call.
- [ ] GREEN discovers only the exact new B4/B5/protocol evidence, computes `build_b6_task_key`/`build_b6_task_id`, and calls `StrategyDB.create_or_get_b6_task` once. The old queued row is never updated, selected by latest, or used as a fallback. The result is queued admission evidence only.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_old_queued_task_is_not_selected_by_new_admission -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_new_task_admission_has_zero_oos_side_effects -v
```

The future production admission, if separately authorized, may create/reuse exactly one new queued v2 task and must post-check the old row unchanged. It must not claim either task.

### Phase5E6 — Prepared supplement in second preflight and recovery TDD

**Files:** `backend/services/b6_validation_worker.py`, `backend/services/b6_same_draw_executor.py`, `scripts/run_b6_validation_task.py`, `tests/test_b6_validation_worker.py`, `tests/test_b6_same_draw_executor.py`, `tests/test_run_b6_validation_task.py`.

- [ ] RED nodes:
  - `test_second_preflight_verifies_v2_supplement_before_ledger_read_and_returns_prepared_token`;
  - `test_prepared_token_is_consumed_once_after_start_without_reverification`;
  - `test_source_binding_drift_before_start_blocks_without_reservation`;
  - `test_source_binding_drift_after_start_fails_after_start_without_executor_rerun`;
  - `test_worker_progress_order_claim_preflight_token_ledger_reserve_start`.
  Expected RED is the current verifier-after-start/missing prepared-token seam. Tests use temporary file-backed SQLite and deterministic fake ledger/executor seams; no production path is opened.
- [ ] GREEN adds the narrow `_prepare_verified_supplement`/prepared-token boundary in the worker/executor owner. The official verifier is called exactly once after claim and before the only `get_ledger_state`; the returned token carries the exact v2 identity and verified representation. `execute_production_same_draw` consumes that token once and never discovers or verifies the supplement again. Existing claim, reserve, start, fail-after-start, terminal, recovery, no-Promotion, and Alpha contracts remain unchanged.
- [ ] Run each RED node separately, then the GREEN nodes and these short regressions:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_executor -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b6_validation_worker.py backend/services/b6_same_draw_executor.py scripts/run_b6_validation_task.py
```

Any post-start verifier call, second ledger read, second executor, path-based TOCTOU fallback, or fake reachable from the production CLI is a hard stop.

### Phase5E7 — Progress, one-time backup, operator runbook, and final read-only gate

**Files:** `scripts/run_b6_validation_task.py`, `tests/test_run_b6_validation_task.py`, and create `docs/operations/b6-validation-recovery-runbook.md` only after the tests prove the exact state matrix.

- [ ] RED nodes:
  - `test_cli_emits_ordered_jsonl_progress_on_stderr_and_canonical_result_on_stdout`;
  - `test_preclaim_backup_uses_sqlite_consistency_backup_and_blocks_claim_on_failure`;
  - `test_cli_rejects_user_backup_path_and_all_oos_override_arguments`;
  - `test_runbook_matches_queued_running_reserved_started_completed_failed_matrix`.
  Expected RED is missing progress/backup/runbook behavior.
- [ ] GREEN adds only the thin CLI progress emitter and server-owned pre-claim backup. Progress events use `b6_validation_progress.v1` and the exact fields in spec 12.5. The backup uses `sqlite3.Connection.backup` to `data/strategy_backups/b6_preclaim/<task_id>.<source_db_sha256>.sqlite3`, with temp+flush/fsync+atomic replace and exact reuse/conflict checks. Backup failure occurs before claim and has zero task/OOS side effects. No polling, latest scan, retry loop, or user path is added.
- [ ] Run the three CLI tests and the runbook contract test separately, then:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile scripts/run_b6_validation_task.py backend/services/b6_validation_worker.py backend/services/b6_same_draw_executor.py
```

- [ ] **Final read-only preflight.** Verify v2 criteria pair, new supplement, protocol, B4, four B5 results/bundle, new queued task, old queued task immutability, sidecars, progress/backup configuration, target processes, scratch, and raw SQLite counts. Do not run the worker or CLI against production. The final status is `Phase5E review-ready; production OOS not authorized` only when all focused checks pass.

### Phase5E handoff and coverage review

The addendum covers all required decisions: E1 freezes the evaluator types and equivalence; E2/E3 freeze and publish the v2 identity; E4 propagates immutable lineage; E5 separates old/new task identity; E6 fixes verifier timing and token ownership; E7 provides progress, backup, recovery, and the final read-only gate. The existing Phase5A–D contracts remain in force. The old v1 criteria, supplement, B4/B5 artifacts, and queued task are never overwritten. No step authorizes a production OOS draw, report/Gate write, Promotion, Signal, or Git operation.

## Active addendum: explicit-task worker and same-draw Alpha (2026-08-21)

This is a document-only design and implementation plan. It does not claim the queued production task, read or reserve production OOS, modify artifacts, or authorize the final production draw. It supersedes any historical wording that assumes a B6 worker already exists. The repository has a generic worker only; the B6 worker must be one narrow explicit-task application owner.

### Review gate: verified execution boundary and current gaps

The concrete reusable B4 execution boundary is:

```text
strategy_core.backtest_engine.run_event_backtest
  -> strategy_core.v3_relative_strength_executor.run_v3_relative_strength_backtest
```

Its frozen inputs are `V3RelativeStrengthExecutionSpec`, the formal PIT data source behind the existing read-bound adapter, the protocol snapshot ID, data snapshot hash, exact verified supplement, and the protocol-owned calendar/window. The v3 branch already enforces the supplement, strategy revision, protocol, data hash, and initial-capital bindings before calling the relative-strength execution loop. The new worker must bind this existing function; it must not invent a second OOS executor.

The review also establishes two implementation gaps that must remain explicit:

- the repository has no B6-specific worker entry that claims by explicit task ID;
- `run_event_backtest` returns the strategy event result only; `BacktestReportBuilder` currently emits `not_available_from_b4_result` for benchmark/control/base/stress fields, `CostStressRunner` validates stress assumptions but does not run a stress portfolio, and `ControlComparison` validates supplied comparisons but does not execute an OOS control.

Therefore production cannot be authorized until the result contract and one same-draw callable are implemented and focused-tested. B5 IS comparison values remain evidence only and cannot satisfy those OOS fields.

### Design variants and decision

| Variant | Decision | Reason |
|---|---|---|
| A. Narrow `B6ValidationWorker` plus thin explicit-task CLI, with a callable execution seam for tests and a production binding to the concrete B4 function above | **Selected** | Smallest owner that can enforce claim, second preflight, recovery, reserve/start, one execution envelope, terminal checks, and audit. It reuses `StrategyDB`, `OOSBudgetLedger`, existing B4 execution, report, Gate, and explanation components. |
| B. Manually chain existing flow/ledger calls from a script | Rejected | The current flow has no executor seam, does not verify B5 in the worker path, builds only the legacy B4 report facts, and manual chaining would weaken recovery and terminal auditability. |
| C. Generic worker/attribution platform | Rejected | Adds routing, polling, parallelism, and abstractions outside the one explicit task and one draw required here. |

The production callable is not a second engine: it is a narrow adapter around `run_event_backtest` with the frozen v3 spec/data boundary and deterministic benchmark/control/cost calculations over that same input envelope. Test callables are deterministic fakes and never touch production data or OOS.

### Phase 5A — same-draw result, Alpha, report, Gate, and explanation contract

**Scope:** pure contracts and temporary values only; no ledger, DB, production task, or OOS read.

**Files and functions:**

- Modify `backend/services/b5_oos_types.py` with the smallest frozen result/payload models needed for `b6_same_draw_oos_result.v1` and `b6_same_draw_oos_report.v1`. Do not add result IDs/hashes to the B6 task or add database columns.
- Modify `backend/services/backtest_report_builder.py::build_report` only as required to accept a validated same-draw result and emit the exact payload identity/lineage/Alpha fields. Preserve no-recommendation and canonical-hash rules.
- Modify `backend/services/prototype_gate_v2.py::evaluate` only as required to revalidate the same-draw fields, retain existing beta-dominated behavior, and persist deterministic report-field references/values. Do not add an Alpha threshold.
- Modify `backend/services/gate_explanation_builder.py::build_explanation` only as required to surface absolute net-return and Alpha values without instructions.
- Add `tests/test_b6_same_draw_result_contract.py` and `tests/test_b6_alpha_report_gate_contract.py` using temporary in-memory values only; no production files or DB.

**RED:** Run each focused node separately. Expected reasons are the absent result schema/identity validation, the current B4-only `not_available_from_b4_result` fields, and missing Alpha/report/Gate/explanation binding—not an OOS, ledger, or worker failure.

Required cases:

1. valid strategy/benchmark/control base+stress values produce exactly the four subtraction formulas;
2. missing series, NaN/inf, zero/non-positive NAV, mismatched window/input identity, invalid stress ordering, or arithmetic mismatch fails loudly;
3. the report payload includes task/key, protocol/revision, B5 refs, B4 lineage, OOS window/input identity, schema/version, all six net returns, four Alpha values, and cost results; canonical payload hash changes on any field change;
4. B5 IS values cannot be accepted as OOS result values;
5. Gate requires all same-draw fields but introduces no Alpha threshold and never emits `prototype_passed`/Promotion;
6. explanation binds report/Gate and states market movement versus strategy excess without a causal claim or trading instruction.

**GREEN and commands:**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_result_contract -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_alpha_report_gate_contract -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b5_oos_types.py backend/services/backtest_report_builder.py backend/services/prototype_gate_v2.py backend/services/gate_explanation_builder.py tests/test_b6_same_draw_result_contract.py tests/test_b6_alpha_report_gate_contract.py
```

Any failure outside the stated missing contract, or any attempt to use B5 values as OOS values, stops Phase 5A.

### Phase 5B — explicit-task claim, second preflight, and B5 admission

**Files and functions:**

- Create `backend/services/b6_validation_worker.py` with the narrow `B6ValidationWorker.run_task(task_id: str)` owner, conditional claim, explicit-task load, second preflight, typed blocked/failed transitions, and exact recovery lookup. No polling/latest selector.
- Reuse `backend/db/strategy.py::claim_b6_task`, `get_b6_task_by_id`, and v2 task identity; only add a minimal reservation lookup/identity check if the current public owner cannot prove task-key binding.
- Reuse the existing B5 verifier and the exact B4 lineage checks already used by Task7/Task8; do not duplicate verifier logic.
- Add `tests/test_b6_validation_worker.py` with temporary file-backed DB fixtures and transparent ledger/executor observations. No production StrategyDB, no OOS draw, and no worker mock of the unit under test.

**RED:** Separate focused nodes must show the current absence of a B6 worker/admission path. Required cases:

1. a valid queued v2 task claims only by its explicit ID and reaches a second-preflight seam;
2. missing/tampered B5, B4/B5 lineage mismatch, task/protocol/revision mismatch, or invalid security disclosure becomes `blocked` before reservation, with no ledger-state read after a failed immutable check;
3. a valid claim performs exactly one ledger-state read, while ledger state is not reserved during preflight;
4. latest/any-queued/no-task-ID invocation is rejected by the API/CLI contract;
5. a concurrent file-backed claim has one winner and one non-winner, both for the same durable task row.

**GREEN:** Implement only the explicit `task_id` owner and the second-preflight boundary. Valid claims must retain the B5 fixture-only disclosure, never create a new task, and stop before reserve/start/execution/report/Gate. Missing or invalid evidence must leave all OOS tables unchanged. Use a temporary file-backed DB and deterministic B5/B4 fixture copies only.

**Focused commands:**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker.TestWorkerClaimAndPreflight -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b6_validation_worker.py tests/test_b6_validation_worker.py
```

The phase stops on any claim race, B5 verifier bypass, unexpected ledger read, production-path access, or task identity mismatch.

### Phase 5C — reserve/start, one same-draw callable, terminal chain, and recovery

**Files and functions:**

- Extend `backend/services/b6_validation_worker.py` only with the reserve/start/recovery/terminal orchestration and a callable injection such as `execute_same_draw(envelope)`. The worker calls this callable exactly once after `start_execution`.
- Modify `backend/services/b6_validation_flow.py::run_minimal_validation` only where needed to accept the already validated same-draw result and reuse its report/Gate/explanation/terminal owners. It must not invent another executor or make a second draw.
- Modify `backend/db/strategy.py::store_b6_terminal_result_tx` only to exact-check task/reservation/report/Gate/protocol/revision/B5/window/hash bindings before commit; keep the existing one-transaction all-or-nothing shape.
- Modify `backend/services/oos_budget_ledger.py` only if the existing public methods cannot express exact task-key recovery or the frozen failure transitions; do not change budget limits or draw semantics.
- Add/extend `tests/test_b6_validation_worker.py` and `tests/test_b6_terminal_transaction.py` with temporary file-backed DBs and a deterministic fake callable.

**RED:** Separate cases must demonstrate current gaps for reserve/start/terminal/recovery, not run production OOS:

1. normal reserve rejection changes running to blocked with zero reservation/consumption;
2. invariant mismatch changes running to failed with no fabricated report/Gate;
3. `reserved` then start failure releases pre-execution without consumption;
4. `started` executor exception or ambiguous result calls `fail_after_start`, consumes exactly one draw, fails the task, and never reruns;
5. valid fake result creates a report/Gate/complete ledger/task chain in one terminal transaction;
6. injected terminal failure rolls back the complete success chain;
7. exact task/B5/protocol/revision/window mismatch fails before commit;
8. completed/failed/released recovery follows the matrix and never scans latest;
9. Promotion and Signal are not called.

**GREEN:** Bind the worker to existing ledger primitives and the existing B4 engine boundary. The production callable must construct one envelope from the protocol OOS window and use the same formal PIT source/calendar/read audit for strategy, benchmark, same-universe control, and base/stress values. A deterministic fake is the only callable used in implementation tests. No OOS read/reserve/start/consume is allowed outside these temporary DB/fake tests.

**Focused commands:**

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker.TestWorkerReservationAndRecovery -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_terminal_transaction -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker tests.test_b6_terminal_transaction -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b6_validation_worker.py backend/services/b6_validation_flow.py backend/db/strategy.py backend/services/oos_budget_ledger.py tests/test_b6_validation_worker.py tests/test_b6_terminal_transaction.py
```

Any second attempt after `started`, any terminal partial write, any missing Alpha field, or any new independent root is a hard stop. No production task may be claimed in this phase.

### Phase 5D0 — approved design gate and exact cost/read-audit decision

This gate is documentation-only. It records the approved narrow design before any Phase5D implementation. No production task claim, database access, OOS ledger read, reservation, start, execution, report, or Gate write is permitted.

**Files:** no production or test files. Review only the existing spec 11.3–11.5, `backend/services/b5_oos_types.py`, `backend/services/b6_validation_worker.py`, `strategy_core/backtest_engine.py`, `strategy_core/v3_relative_strength_executor.py`, `backend/services/v3_b5_comparison.py`, `backend/services/v3_b5_costs.py`, and the existing Phase5A–C tests.

**Acceptance:** the review must record the exact `execute_production_same_draw(envelope, *, repo_root)` owner, the local observer sidecar, one shared FormalPIT/read-bound owner, independent portfolio state, the strategy fill-cost formula, the fractional comparator formula, v2 read-audit summary, and the v1-to-v2 compatibility boundary. A missing formula or an unproven B4/observer boundary is a hard stop; do not write an approximate plan.

**Static checks:** inspect the named symbols with `rg -n` and inspect the spec/plan sections with `Get-Content`; do not run Python, tests, CLI, worker, or OOS commands in this gate.

### Phase 5D1 — same-draw result v2 and canonical read-audit contract RED → GREEN

**Files:**

- Modify `backend/services/b5_oos_types.py`: add `B6SameDrawReadAudit`, add `read_audit: B6SameDrawReadAudit | None` to the result, allow result identity schema `b6_same_draw_oos_result.v1` or `.v2`, and require the audit plus exact cost-assumption hashes through `BaseCostResult.assumptions_hash`/`StressCostResult.assumptions_hash` for v2. Keep v1 synthetic/history payloads readable; require v2/audit for a production terminal chain.
- Modify `backend/services/backtest_report_builder.py::build_report` and its same-draw validation only to carry and hash the v2 audit summary. Do not reuse `b4_read_trace_summary` as an OOS audit.
- Modify `backend/services/prototype_gate_v2.py` and `backend/services/gate_explanation_builder.py` only to revalidate/forward the v2 audit and display “read audit verified”; do not add a threshold or Promotion path.
- Create/extend `tests/test_b6_same_draw_result_contract.py` and `tests/test_b6_alpha_report_gate_contract.py`.

**Exact read-audit contract:** `B6SameDrawReadAudit` has `schema_version="b6_same_draw_read_audit.v1"`, `owner="b6_same_draw_executor"`, `allowed_end: date`, `max_requested_date: date | None`, `future_violation_count: int`, `operation_counts: dict[str, int]`, `read_count: int`, and `canonical_trace_sha256: str` (64 lowercase hex). It requires `future_violation_count == 0`, all counts non-negative finite integers, `max_requested_date is None or <= allowed_end`, and the exact owner/schema. The trace hash is SHA-256 of UTF-8 canonical JSON with `sort_keys=True`, `ensure_ascii=False`, `separators=(',', ':')`, and `allow_nan=False` over the ordered in-memory trace. Raw trace is never persisted.

**RED:** run each node separately before implementation:

1. `TestB6SameDrawResultV2.test_v2_requires_verified_read_audit` — current result has no required audit/v2 boundary.
2. `TestB6SameDrawResultV2.test_audit_bounds_owner_counts_and_trace_hash_are_strict` — current model does not reject wrong owner, future max date, nonzero future violations, invalid counts, or malformed hash.
3. `TestB6AlphaReportGateContract.test_report_hash_covers_read_audit_and_metrics` — current report does not include the audit summary in its canonical same-draw payload.
4. `TestB6AlphaReportGateContract.test_v1_fixture_remains_readable_but_not_production_terminal` — current compatibility boundary is absent.

Expected RED is only the missing additive v2/audit contract. A failure from ledger, worker, production files, or OOS access stops the phase.

**GREEN:** implement the smallest frozen model/validator and payload propagation. Six returns remain the only inputs to the four Alpha properties. Re-run the four exact nodes, then:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_result_contract -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_alpha_report_gate_contract -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b5_oos_types.py backend/services/backtest_report_builder.py backend/services/prototype_gate_v2.py backend/services/gate_explanation_builder.py tests/test_b6_same_draw_result_contract.py tests/test_b6_alpha_report_gate_contract.py
```

No production DB, OOS ledger, worker, or artifact is opened in Phase5D1.

### Phase 5D2 — concrete production same-draw executor RED → GREEN

**Files:**

- Create `backend/services/b6_same_draw_executor.py` with only `execute_production_same_draw(envelope: Mapping[str, Any], *, repo_root: Path) -> B6SameDrawOOSResult`, one local immutable strategy sidecar, one shared read-bound/audit owner, and the narrow benchmark/control loop using existing pure B5 comparison functions.
- Create `tests/test_b6_same_draw_executor.py` with temporary verified fixtures and a synthetic in-memory/file-backed source. The tests must call the real `run_event_backtest`/V3 execution boundary through the executor; they may not replace the engine with a fake. The B6 worker fake callable remains limited to worker tests.
- Do not modify historical `EventBacktestResult`, B4 artifacts, B5 publisher/verifier, or create a second engine.

**Exact execution and cost behavior:**

1. Validate the server-owned envelope and construct `V3RelativeStrengthExecutionSpec` from protocol OOS start/end, protocol/revision/data hash, verified supplement, and server-owned initial capital.
2. Create one `FormalPITPartitionAdapter` plus one local read-bound wrapper. Pass its cursor-bound views to the single strategy run and to the benchmark/control calculation. Keep three portfolio state objects independent.
3. Collect strategy observations through existing `observation_sink`. Recompute strategy fill costs with the same formula as `v3_b5_costs.calculate_cost_results`, but do not call that IS-range/artifact-bound function or load its IS rows: base uses commission `.0003`, min commission `5.0`, sell stamp `.001`, transfer `0`; stress uses commission `.0006`, the same minimum/stamp/transfer, and price `base*1.001` for buys / `base*.999` for sells, with slippage `abs(stress_price-base)*quantity`. The denominator is `sum(abs(quantity*base_price))`; cost bps are `total_cost / denominator * 10000`.
4. Use final observed strategy base NAV without subtracting base cost again; compute `strategy_ending_nav_stress = strategy_ending_nav_base - (stress_total - base_total)`. Compute both strategy returns from server-owned starting NAV. Reject any mismatch, nonfinite value, or non-positive stress NAV.
5. For benchmark/control, preserve `rebalance_fractional` exactly: turnover is `(sell_proceeds + actual_buy_total) / pre_trade_nav`; base/stress cost amounts are `turnover * BASE_COST_BPS / 10000` and `turnover * STRESS_COST_BPS / 10000`; cumulative costs are subtracted from gross NAV. Start at `INITIAL_NAV=1.0`; each return is `ending_net_nav / INITIAL_NAV - 1`. Do not read B5 IS result values or cost aggregate payloads.
6. Build v2 `B6SameDrawOOSResult`, derive all four Alpha values from the six returns, validate the read-audit summary, and return once. No reserve/start/consume/retry is allowed inside the executor.

**RED:** run separately:

1. `TestB6SameDrawExecutor.test_production_callable_is_missing_or_not_bound_to_real_b4` — current repository has no module/callable.
2. `TestB6SameDrawExecutor.test_real_v3_caller_produces_strategy_sidecar_and_six_returns` — current engine path has no same-draw comparator/result seam.
3. `TestB6SameDrawExecutor.test_strategy_stress_does_not_double_charge_base_cost` — current code has no explicit base/stress NAV formula.
4. `TestB6SameDrawExecutor.test_shared_read_audit_and_independent_portfolios` — current code has no single cross-portfolio audit owner.
5. `TestB6SameDrawExecutor.test_future_identity_cost_and_missing_series_fail_loud` — current callable boundary is absent.

Expected RED is only the missing executor/result seam. GREEN must prove one real strategy execution, one shared source/audit, independent benchmark/control state, finite v2 result, exact Alpha formulas, no B5 IS values, and no second execution/draw. If the real V3 observer cannot provide the required local sidecar without changing strategy semantics, stop before modifying B4 contracts.

**GREEN and regression:** re-run the five exact nodes, then:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_executor -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_result_contract tests.test_b6_alpha_report_gate_contract -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b6_same_draw_executor.py backend/services/b5_oos_types.py backend/services/backtest_report_builder.py backend/services/prototype_gate_v2.py backend/services/gate_explanation_builder.py tests/test_b6_same_draw_executor.py
```

All data is temporary/synthetic or isolated test input. No production task, artifact, ledger, or OOS data is read.

### Phase 5D3 — explicit-task CLI RED → GREEN

**Files:**

- Create `scripts/run_b6_validation_task.py` as a thin parser/loader. It accepts exactly one required positional `task_id`, performs dependency/config validation for the real executor before opening the task DB, constructs a worker with `functools.partial(execute_production_same_draw, repo_root=server_repo_root)`, calls `run_task(task_id=task_id, execute_same_draw=...)` once, prints one stable JSON object, and closes every handle in `finally`.
- Create `tests/test_run_b6_validation_task.py` for the real CLI caller boundary using temporary file-backed DBs and the test injection seam only; fake execution is never reachable from the production CLI builder.

**RED:** run separately:

1. `TestRunB6ValidationTask.test_no_id_latest_and_extra_parameters_are_rejected_without_db_or_oos_side_effect` — current script is absent.
2. `TestRunB6ValidationTask.test_exact_task_id_is_passed_once_and_no_polling_or_latest_scan_exists` — current CLI caller does not exist.
3. `TestRunB6ValidationTask.test_missing_real_executor_blocks_before_claim` — dependency failure must occur before DB/task/ledger access.
4. `TestRunB6ValidationTask.test_worker_boundary_maps_queued_blocked_failed_completed_recovery_required_stably` — current CLI JSON/exit mapping is absent.
5. `TestRunB6ValidationTask.test_cli_never_exposes_window_hash_cost_benchmark_or_promotion_inputs` — current argument contract is absent.

**GREEN:** the CLI has no batch mode, polling loop, retry loop, latest selector, user OOS window, hash, cost, strategy, benchmark, universe, or data-source argument. It never calls Promotion or Signal. Invalid arguments and missing dependencies have zero DB/OOS side effects; only a later explicitly authorized production invocation may claim a production task.

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task.TestRunB6ValidationTask.test_no_id_latest_and_extra_parameters_are_rejected_without_db_or_oos_side_effect -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task.TestRunB6ValidationTask.test_exact_task_id_is_passed_once_and_no_polling_or_latest_scan_exists -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task.TestRunB6ValidationTask.test_missing_real_executor_blocks_before_claim -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task.TestRunB6ValidationTask.test_worker_boundary_maps_queued_blocked_failed_completed_recovery_required_stably -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task.TestRunB6ValidationTask.test_cli_never_exposes_window_hash_cost_benchmark_or_promotion_inputs -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile scripts/run_b6_validation_task.py backend/services/b6_same_draw_executor.py tests/test_run_b6_validation_task.py
```

### Phase 5D4 — focused review checkpoint

No production invocation is permitted. Review the exact changed files against spec 11.3–11.5 and confirm: one real V3 strategy call; one shared read-audit owner; three independent portfolio states; exact base/stress formulas with no double charge; v2 audit/result/report hashes; no B5 IS values; no fake reachable from production CLI; explicit task ID only; no Promotion/Signal; and all handles closed on success and failure.

Run separately, without full pytest/build:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_executor -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker tests.test_b6_terminal_transaction -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_same_draw_result_contract tests.test_b6_alpha_report_gate_contract -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile backend/services/b6_same_draw_executor.py scripts/run_b6_validation_task.py backend/services/b5_oos_types.py backend/services/backtest_report_builder.py backend/services/prototype_gate_v2.py backend/services/gate_explanation_builder.py tests/test_b6_same_draw_executor.py tests/test_run_b6_validation_task.py
```

Any failure, missing read-audit field, unproven cost equality, second strategy execution, production dependency access, B5 IS reuse, or new independent root stops Phase5D. Phase5D is review-ready only after all focused synthetic/temp checks pass.

### Phase 5E — focused review and separately authorized production gates

No production invocation is part of Phases 5A–5D. Review must confirm:

- explicit task ID is the only selector and no generic worker/polling code is used;
- second preflight occurs before the first ledger-state read/reservation and revalidates B5 security, B4 lineage, protocol, revision, task identity, and window;
- one same-draw envelope produces strategy, benchmark, same-universe control, base/stress and four arithmetic Alpha values;
- strategy base/stress NAV uses the exact v3 fill-cost replay and `ending_nav_stress = ending_nav_base - (stress_total - base_total)`; benchmark/control preserve the exact `rebalance_fractional` turnover/BPS formula;
- one shared read-audit owner produces the v1 canonical summary, and v2 result/report hashes cover its owner, bounds, counts, future-violation value, and trace hash;
- report hash covers all required identity and result fields; Gate/explanation and terminal transaction revalidate the same chain;
- started uncertainty consumes exactly one draw and cannot rerun; Promotion and Signal remain separate;
- all implementation tests use temporary file-backed DBs/fakes and production counts/artifacts remain untouched.

Required review commands are the focused Phase 5A–5D commands separately; no full pytest/build is allowed. A later production preflight must be authorized independently, use the exact queued `task_id`, perform the second preflight once, and stop before OOS unless a further explicit one-draw authorization is granted. A production OOS authorization, if later granted, permits at most one claim/start/draw and requires a post-gate of task/reservation/ledger/report/Gate hashes and zero Promotion/Signal.

### Stop rules and handoff

Stop immediately on an unproven B4 execution boundary, a need for a new data source or strategy parameter, a B5 security-field change, any latest/queued scan, any second draw or rerun after `started`, any missing same-draw comparator, any report/Gate/terminal identity mismatch, any production DB/OOS access during implementation, or any authorized GREEN failure followed by a new independent root. The implementation is not complete merely because the worker or contract tests pass. The only accepted handoff from this document phase is a reviewable design plus fresh document hashes; the production queued task remains `queued` and untouched.

### Phase R1 — Current successor-lineage reconciliation and durable recovery decision (2026-09-03)

This amendment is documentation-only. It reconciles stale identity literals in the earlier E4.4d/E4.3b narrative; it does not rewrite historical evidence, authorize a publisher/verifier, change code, mutate a task, restore a database, or authorize another Phase D attempt.

#### R1.1 Current runtime target and historical identities

The following chain is the current runtime target because each item was separately published/verified and the current admission/runtime constants and durable task bind to it:

```text
criteria envelope: 94da0dda30af75d663a7d28deb0a15d64a4e068586a1295f3b4f52203a8c4738
protocol snapshot: 8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe
strategy revision: 6440ffc03a742f4d4632078481cf3abf171eafb1a24f2bc69bc6f352d1b19ebc
supplement: f505099849d497e1 / manifest 503724f0ddc2f0d5cc8bb351a1ecd5fed6c0d5c214484ff319eab91113279231
B4: b34022f7435082d2 / manifest 796dc5d216a5bdf2853499b80948d1e1eccb23d9bbcf322965374e402c905a38 / event f289bf323b17a44a8a330a1878e8345dac712fe105623dd690471227f09c7a09
ledger observations: b8577a9ec56f20fe / manifest 6e936a20e5b4d73f75fdd53c2fd2a268d27fc17fb574d90bcc87ddacb09add98
costs: 854c76d2dfd0021f / manifest 82113e141d536e28a27a05ad69cbbe0c428d0babef304781cfd96db93c676dfd
comparisons: d606168cc6c5b608 / manifest 03758d7688c0ecfbe1c0be41f37d44a5ffef74d0f1003feecd6edc0b61a8472e
B5 bundle: 146b93619fea3cab / manifest f54690a76f3b6a5a874379be876d05153477277d1f3b7ab97a1d03a9e8f6e7de
```

The earlier E4.4d literals `cb41dd1dc207642b` / `1aed70f1af38a191` remain immutable historical/documentation evidence only. They are superseded as *current runtime target identities* by the chain above; their historical references are not deleted or rewritten.

#### R1.2 Window ownership contract and one-root-cause correction

B4 and the four B5 results remain IS evidence with event/result window `2025-06-27..2026-03-19`. The frozen B6 protocol owns the OOS execution window `2026-03-20..2026-07-10`. The B6 same-draw executor runs the concrete engine once over the protocol OOS window and must never use B5 IS values as OOS values.

The Phase D failure exposed one contract drift at two call boundaries:

1. `backend/services/b6_validation_worker.py` must validate the loaded B4 event against its verified B4 IS identity/range and lineage; it must not require the B4 IS event window to equal the protocol OOS window.
2. `backend/services/backtest_report_builder.py` must preserve B4 IS lineage/read evidence while validating `same_draw_result.identity` against the protocol OOS identity/window; it must not repeat the B4-IS-equals-OOS comparison. The legacy B4-only path remains unchanged.

Both checks are one root-cause correction and must be fixed and tested together before any new draw. Removing only the worker check is insufficient because the report-builder check would otherwise fail after `start_execution`, invoke `fail_after_start`, and consume a draw for a valid IS-predecessor/OOS-execution chain.

#### R1.3 Durable recovery decision

The failed target `50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3` is preserved as terminal evidence. The preclaim backup is preserved as evidence and a possible owner-approved recovery input, not as an instruction to overwrite the live database. No SQL reset, in-place status mutation, automatic retry, replacement task, or backup restore is permitted in R1.

The existing schema and public API cannot create a second attempt with the same immutable task identity: `b6_validation_tasks.task_key` is unique, `build_b6_task_key` binds the v2 protocol/revision/task/B5 identity, and `StrategyDB.create_or_get_b6_task` returns the existing winner unchanged. Therefore a lawful successor attempt requires a separately specified, write-once successor-attempt contract and an explicitly owned schema/migration/tool boundary. The exact new identity dimension, migration, and state-owner tool are not invented by this amendment.

The selected default is to retain the failed row and prefer that explicit successor-attempt contract over restoring/overwriting the preclaim backup. A backup restore can be considered only under a later state-owner authorization that proves failed-attempt evidence retention, no intervening durable writes that would be lost, exact snapshot health, and atomic/recoverable operation. No ownerless direct SQL workaround is lawful.

#### R1.4 Staged gates and authorization boundaries

The next work is four separately gated stages:

- **A — temporary root-cause fix:** under new code/test authorization, add a temporary file-backed B4-IS/protocol-OOS regression and correct both production checks above. No production DB, artifact, task, publisher, verifier, or OOS draw.
- **B — temporary full regression:** run the directly relevant worker, executor, report/terminal, CLI, B4/B5 admission regressions and fresh compilation; prove legacy compatibility, one executor, one ledger read, exact recovery, and zero Promotion/Alpha/Signal reachability. No production invocation.
- **C — durable recovery/successor decision:** the designated StrategyDB/schema state owner must explicitly authorize either (i) a new successor-attempt contract plus additive migration/owner tool, preserving the failed row, or (ii) an approved backup-recovery procedure satisfying R1.3. The tool must be explicit-task scoped, write-once, auditable, and post-checked read-only; it may not silently reset the failed row or select a latest/queued task.
- **D — new one-shot:** only after A/B GREEN, C completion, fresh read-only preflight, and a separate one-draw authorization may one explicit task be claimed/started/executed once. Post-gate must verify task/reservation/ledger/report/Gate identity and hashes, zero Promotion/Alpha/Signal, and no retry.

Phase R1 is review-ready for this documentation decision after fresh document hashes and static readback. Code correction, durable recovery, successor creation, and a new Phase D remain separately authorized and blocked.

### Phase C0 — Write-once successor attempt for the contained failed v2 task (2026-09-03)

This amendment is the design-only completion of R1 gate C. It defines the
durable owner boundary required to create one successor attempt while retaining
the failed predecessor. It does not implement code, run tests or compilation,
open a production `StrategyDB`, invoke a CLI/worker/publisher/verifier/OOS
ledger, write a task, write data, restore the backup, or authorize Phase B or
Phase D. The implementation must use `writing-plans`,
`systematic-debugging`, and `verification-before-completion` discipline.

#### C0.1 Evidence and decision

The read-only baseline for this amendment is:

| Item | Evidence |
|---|---|
| Live database | `D:\\Codex\\TraderLens\\data\\strategy.db`; SHA-256 `520d2933963ee72f74c965d9e9a4235747760ed3168b6711acd695660bfc6b67`; 233472 bytes; mtime `2026-09-02T04:04:38.116386+00:00`; `quick_check=ok`; `foreign_key_check=[]` |
| Failed predecessor | task `50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`, v2, key `2e61682988c3787ced5e1814018b059827b791cfa980e49bc5c2ceba8fea9a25`, status `failed`, blocking code `invariant_error`; protocol `8770c56c5a69ef128442c0f593f9e4b081a6b13c69744b27171b27cc8c8b7bbe`; B5 `146b93619fea3cab` / `f54690a76f3b6a5a874379be876d05153477277d1f3b7ab97a1d03a9e8f6e7de` |
| Retained backup | `D:\\Codex\\TraderLens\\data\\strategy_backups\\b6_preclaim\\50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3.de496d56c718b05ec1b0585b6654b5980d77c5879abc21060f69d36776d1646c.sqlite3`; SHA-256 `3f488e2120829684c88c2cbf74ce236d14996b82bae2c14c8d93732815088a1e`; 233472 bytes; mtime `2026-09-02T04:04:24.123259+00:00`; `quick_check=ok`; `foreign_key_check=[]` |
| Preclaim distinction | The live predecessor is `failed`; the retained preclaim backup contains the same task as `queued`. The backup is evidence and is never an instruction to overwrite live state. |
| Protected tables | `oos_budget_state`, `oos_budget_reservations`, `oos_evaluation_ledgers`, `immutable_backtest_reports`, `prototype_gate_results_v2`, `strategy_promotions`, `human_promotion_confirmations`, and `human_confirmation_consumptions` are all count `0` in both read-only snapshots. |

The current `b6_validation_tasks.task_key` unique constraint and
`StrategyDB.create_or_get_b6_task` v2 exact-reuse behavior explain the failed
Task7 observation: a current v2 request returns the retained failed winner;
it cannot lawfully create another row with the same identity. The selected
solution is a separate, explicit successor owner. `create_or_get_b6_task`, the
v1/v2 model, the old rows, and the existing worker CLI contract remain
backward-compatible. Task7 admission does not silently create a successor.

#### C0.2 Successor identity contract

Modify `contracts/b6_task.py` as follows, without changing the v1 or v2
canonical objects:

1. Add `B6_TASK_CONTRACT_V3 = "v3"`.
2. Add `build_b6_successor_task_key(...)`. Its canonical object is exactly:

   ```json
   {
     "attempt_number": 1,
     "b5_bundle_id": "<predecessor.b5_bundle_id>",
     "b5_bundle_manifest_sha256": "<predecessor.b5_bundle_manifest_sha256>",
     "predecessor_task_id": "<predecessor.task_id>",
     "predecessor_task_key": "<predecessor.task_key>",
     "protocol_profile": "b6_coverage_bound",
     "protocol_snapshot_id": "<predecessor.protocol_snapshot_id>",
     "strategy_revision_id": "<predecessor.strategy_revision_id>",
     "task_contract_version": "v3",
     "task_type": "b6_validation"
   }
   ```

   Serialize with sorted-key compact JSON, `ensure_ascii=False`, UTF-8, and
   lowercase SHA-256. `build_b6_task_id()` remains unchanged and hashes this
   v3 key with the existing `{"kind":"b6_validation_task", "payload":...}`
   wrapper.
3. Extend `B6ValidationTask` with nullable
   `predecessor_task_id`, `predecessor_task_key`, and
   `successor_attempt_number`. v1 and v2 require all three to be null; v3
   requires a path-free predecessor ID/key, `successor_attempt_number == 1`,
   and the complete B5 pair. The model must reject a half-paired successor,
   any attempt number other than one, and any extra field.
4. Keep v1 absent/null B5 fields readable and keep the v2 seven-field key
   byte-for-byte unchanged. The narrow ordinal is a one-successor invariant,
   not a generation registry or general versioning system.

#### C0.3 Additive schema and StrategyDB owner

Create `backend/db/migrations/migration_005_add_b6_successor_attempt.py` with
one idempotent transactional function
`migrate_add_b6_successor_attempt(conn)`. Register it in
`backend/db/strategy.py:StrategyDB._run_migrations()` immediately after
migration 004. The migration is additive and must execute these guarded
operations:

```sql
ALTER TABLE b6_validation_tasks
  ADD COLUMN predecessor_task_id TEXT
  REFERENCES b6_validation_tasks(task_id);
ALTER TABLE b6_validation_tasks ADD COLUMN predecessor_task_key TEXT;
ALTER TABLE b6_validation_tasks ADD COLUMN successor_attempt_number INTEGER;
CREATE UNIQUE INDEX IF NOT EXISTS uq_b6_direct_successor_predecessor
  ON b6_validation_tasks(predecessor_task_id)
  WHERE predecessor_task_id IS NOT NULL;
```

Each `ALTER TABLE` is issued only when `PRAGMA table_info` lacks the column;
the function uses `BEGIN IMMEDIATE`, commits only after the index exists, and
rolls back on every exception. Existing v1/v2 rows remain null in the new
columns; the existing task-key unique index, triggers, primary key, and
foreign keys are not rebuilt or rewritten. The self-FK and partial unique
index are database defense-in-depth; the v3 model and owner enforce the
cross-field identity.

Add `StrategyDB.create_or_get_b6_successor_attempt(predecessor_task_id: str)
-> tuple[B6ValidationTask, bool]`. This is the only public creation owner and
accepts no caller-supplied protocol, revision, B5, path, key, or attempt
number. Its exact transaction is:

1. Begin `BEGIN IMMEDIATE` and load the predecessor by the exact task ID.
2. Validate the predecessor payload/columns and canonical v2 task ID/key;
   require v2, `status == "failed"`, a non-null claim time, valid protocol
   profile/revision and complete B5 pair. Missing, malformed, non-v2, or
   non-failed predecessors raise typed `B6SuccessorPreconditionError` codes
   `b6_successor_predecessor_missing`,
   `b6_successor_predecessor_identity_invalid`,
   `b6_successor_predecessor_not_v2`, or
   `b6_successor_predecessor_not_failed`.
3. Derive the v3 task and key exclusively from the predecessor. Before
   evaluating new-predecessor evidence, select by the partial unique
   `predecessor_task_id` index. An existing row is returned only after every
   v3 immutable field, payload/column pair, predecessor binding, and canonical
   task ID/key matches. It returns `(winner, False)` in any legal successor
   lifecycle state; a mismatch raises `b6_successor_existing_conflict`.
4. If no successor exists, prove the predecessor is pre-reservation and
   pre-consumption without calling `OOSBudgetLedger`: the owner state is
   absent or exactly `(consumed_draw_count=0, next_oos_draw_index=1,
   budget_status='available', active_reservation_id=NULL)`; there are no
   reservations for the owner or predecessor task key and no
   `oos_evaluation_ledgers` for the owner. Any evidence raises the stable code
   `b6_successor_oos_evidence_present`.
5. Query immutable reports for the exact protocol/revision and parse their
   payloads. A report whose `task_id` or `task_key` binds the predecessor, or
   a Gate bound to that report, raises
   `b6_successor_report_or_gate_evidence_present`. Invalid evidence in the
   matching protocol scope fails loudly; it is never ignored as an unrelated
   row.
6. Insert one ordinary queued v3 row with null blocking/claim/completion
   fields. Re-read the complete row through `_load_b6_task`, compare every
   immutable field and `created_at`, then commit and return `(winner, True)`.
   The unique predecessor index handles competing writers: the second writer
   waits, reads the committed exact winner, and returns it without a second
   row. A different unique collision rolls back and raises
   `b6_successor_existing_conflict`.

The owner performs no artifact discovery, supplement verification, B4/B5
publication, worker call, ledger materialization, reservation, report, Gate,
Promotion, Alpha, or Signal operation. `create_or_get_b6_task` remains v2-only
and unchanged. `_load_b6_task` compares the three successor columns whenever
present, while default-null legacy payloads continue to load unchanged.

#### C0.4 Explicit owner CLI and worker compatibility

Create `scripts/create_b6_successor_attempt.py` with only the server-owned
successor operation. Its exact symbols are `_parse_predecessor_task_id`,
`_emit_progress`, `_run_successor`, `main`, `EXIT_OK = 0`,
`EXIT_INVALID_INVOCATION = 64`, `EXIT_BLOCKED = 20`, and
`EXIT_OWNER_FAILURE = 70`. It accepts exactly one explicit predecessor task
ID; `latest`, `queued`, extra arguments, path arguments, identity overrides,
OOS overrides, backup paths, and worker/executor flags are invalid. It calls
`backup_strategy_db_once(predecessor_task_id, repo_root=...)` before opening
`StrategyDB` or writing the successor. It then calls the owner API once and
prints one canonical stdout object with schema
`b6_successor_attempt.cli.v1`, predecessor/successor IDs and keys, v3 status,
B5 pair, backup identity, `oos_authorized=false`, `oos_consumed=false`, and
`promotion_id=null`. The CLI never imports `B6ValidationWorker`,
`OOSBudgetLedger`, a verifier, or an executor.

Progress is JSONL on stderr with schema `b6_successor_attempt_progress.v1`
and exactly the fields `schema_version`, `event_seq`, `stage`,
`predecessor_task_id`, `successor_task_id`, and `status`. Allowed stages are
`preflight`, `backup`, `owner_write`, `terminal`, `blocked`, and `failed`;
the sequence starts at one and increases strictly. A backup or typed
precondition failure returns 20 without a task write. An unexpected owner or
database failure returns 70 after rollback. Exact reuse is exit 0 and reports
the existing successor status.

Modify `backend/services/b6_validation_worker.py` only to add an exact v3
branch in `_second_preflight`: validate
`build_b6_successor_task_key`, canonical task ID, and the predecessor's
failed immutable v2 identity before the existing B4/B5/protocol checks. Keep
the existing v2 branch byte-for-byte in behavior; v1 remains ineligible.
The existing `run_task(task_id, execute_same_draw=...)` and
`scripts/run_b6_validation_task.py` remain explicit-ID APIs. No fallback from
v3 to v2, latest scan, automatic retry, or new worker/OOS path is allowed.
The same-draw identity does not gain predecessor fields; it remains bound by
the successor's task ID/key and the existing terminal validator.

Update `docs/operations/b6-validation-recovery-runbook.md` with a
successor-owner section: the failed predecessor is preserved, the new owner
CLI is the only creator, the v3 task is queued and exact-ID only, and the
existing worker CLI may run it only after the later one-draw authorization.
Do not describe backup restore, automatic retry, or failed-row reset as an
available action.

#### C0.5 TDD fixture and RED → GREEN sequence

Maintain `tests/test_b6_successor_attempt.py` for contract/schema/owner cases and
`tests/test_create_b6_successor_attempt.py` for owner-CLI cases. The successor
worker boundary remains in `tests/test_b6_validation_worker.py`. All fixtures use a temporary
file-backed SQLite database, public `StrategyDB` model methods to create the
draft/universe/protocol and v2 task, `claim_b6_task` plus
`update_b6_task_status` to form a failed predecessor, and independent
`sqlite3.connect` readers for durable assertions. No fixture copies or opens
`data/strategy.db`, production B4/B5/supplement directories, or writes a
production artifact. The negative OOS/report/Gate cases use only temporary
DB rows made through their public APIs.

Add these exact tests before production implementation:

- `TestB6SuccessorTaskContract.test_v3_requires_predecessor_binding_and_attempt_one`;
- `TestB6SuccessorTaskContract.test_v3_key_is_distinct_and_v1_v2_keys_are_unchanged`;
- `TestB6SuccessorSchema.test_fresh_and_upgrade_migrations_are_additive_idempotent_and_fk_clean`;
- `TestB6SuccessorOwner.test_failed_pre_reservation_v2_creates_one_queued_v3_without_oos`;
- `TestB6SuccessorOwner.test_exact_retry_reuses_successor_in_any_legal_lifecycle_state`;
- `TestB6SuccessorOwner.test_two_file_backed_connections_return_one_successor_winner`;
- `TestB6SuccessorOwner.test_nonfailed_or_v1_predecessor_is_rejected_without_write`;
- `TestB6SuccessorOwner.test_oos_report_or_gate_evidence_blocks_successor_without_write`;
- `TestB6SuccessorOwner.test_insert_failure_rolls_back_and_preserves_failed_predecessor`;
- `tests.test_b6_validation_worker.TestB6SuccessorWorker.test_v3_successor_reaches_existing_second_preflight_boundary`;
- `tests.test_create_b6_successor_attempt.TestB6SuccessorCLI.test_cli_requires_one_explicit_predecessor_and_no_overrides`;
- `tests.test_create_b6_successor_attempt.TestB6SuccessorCLI.test_backup_completes_before_owner_write_and_result_is_canonical`;
- `tests.test_create_b6_successor_attempt.TestB6SuccessorCLI.test_blocked_backup_or_precondition_has_no_db_write`.

Run the RED nodes separately after adding the tests and before each matching
implementation slice:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorTaskContract.test_v3_requires_predecessor_binding_and_attempt_one -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorTaskContract.test_v3_key_is_distinct_and_v1_v2_keys_are_unchanged -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorSchema.test_fresh_and_upgrade_migrations_are_additive_idempotent_and_fk_clean -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorOwner.test_failed_pre_reservation_v2_creates_one_queued_v3_without_oos -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt.TestB6SuccessorOwner.test_two_file_backed_connections_return_one_successor_winner -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_create_b6_successor_attempt.TestB6SuccessorCLI.test_backup_completes_before_owner_write_and_result_is_canonical -v
```

The expected RED reason is the missing v3 contract/migration/owner, not a
production-lineage read or an OOS failure. Any other failure, any production
path access, or any second independent root is a hard stop. The implementation
then proceeds in this exact order: contract/key and model; migration and
`_load_b6_task`; atomic StrategyDB owner; owner CLI; worker v3 branch; runbook
and Task7 characterization updates. Each slice gets its corresponding GREEN
command before the next slice.

#### C0.6 Task7, worker, CLI, migration, and final verification

`tests/test_run_v3_task4_once.py` must characterize the current durable
collision instead of pretending it creates a new v2 row:

- keep `test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task`
  as the current characterization name and assert the exact failed winner,
  `b6_task_reused=true`, no added row, and unchanged old queued/failed rows;
- keep `test_old_queued_task_is_not_selected_by_new_admission` and assert the
  current exact failed winner is selected rather than the unrelated queued
  row;
- keep `test_progressed_current_task_is_reused_without_execution` on a fresh
  temporary current-v2 queued fixture, so its running characterization does
  not depend on the retained failed production snapshot;
- the same `test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task`
  characterization must assert that Task7 does not auto-create a successor for
  the failed v2 identity.

Keep `TestRunB6ValidationTask.test_exact_task_id_is_passed_once_and_no_polling_or_latest_scan_exists`
as the explicit-ID forwarding contract; pair it with
`tests.test_b6_validation_worker.TestB6SuccessorWorker.test_v3_successor_reaches_existing_second_preflight_boundary`
for the v3 worker boundary. The owner CLI tests stay in
`tests.test_create_b6_successor_attempt.py`.

After the focused RED/GREEN slices, run each required regression separately:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_successor_attempt -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_create_b6_successor_attempt -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_old_queued_task_is_not_selected_by_new_admission -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_progressed_current_task_is_reused_without_execution -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_v3_task4_once.TestTask7B5Admission.test_new_v2_b5_bundle_creates_new_task_identity_without_mutating_old_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_validation_worker -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_atomic_claim -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_runtime_persistence_kernel -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_task_state_consistency -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_b6_terminal_transaction -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_reservation_task_binding -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_validation_task -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m pytest tests/test_v3_execution_semantics.py -q
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile contracts/b6_task.py backend/db/migrations/migration_005_add_b6_successor_attempt.py backend/db/strategy.py backend/services/b6_validation_worker.py scripts/create_b6_successor_attempt.py tests/test_b6_successor_attempt.py tests/test_b6_validation_worker.py tests/test_run_v3_task4_once.py tests/test_run_b6_validation_task.py
```

The full verification report must give the actual method count and exact
pass/fail/error/warning count for every command. In particular, no static test
count substitutes for the worker's actual run. Review the implementation
against these dynamic/static contracts: failed predecessor unchanged; exactly
one v3 row and one direct predecessor; exact retry/concurrency convergence;
fresh/upgrade migration idempotency and FK health; no OOS state/reservation/
ledger/report/Gate on a new successor; v3 worker exact-ID compatibility; one
owner backup before one write; v1/v2 compatibility; no v3-to-v2 fallback; and
no Promotion, Alpha, or Signal reachability.

The final implementation gate uses only raw SQLite URI `mode=ro` reads for the
production database and retained backup, recording absolute path, SHA-256,
size, mtime, `PRAGMA quick_check`, `PRAGMA foreign_key_check`, exact task rows,
successor count, and protected-table counts. It also takes a read-only process
snapshot proving no B6 worker/CLI is running. This gate is evidence only and
does not create the successor or run it. No production publisher, verifier,
owner CLI, worker, OOS operation, backup restore, Git operation, deletion, or
cleanup is part of C0.

#### C0.7 Stop rules and handoff

Stop immediately on any schema rebuild, old-row/payload mutation, invalid
self-FK/index, duplicate successor, mismatch accepted as reuse, precondition
evidence ignored, report/Gate evidence bypassed, public v2 behavior changed,
production path access, OOS ledger call, CLI fallback/latest scan, failed
test outside the stated root, or second correction after an authorized
correction fails. Do not repair the live failed row, overwrite the backup, or
start Phase B. C0 is review-ready only after the implementation checks above
are fresh GREEN and the raw production read-only post-check is unchanged;
creation of the v3 row and the later one-shot execution remain separately
authorized operations.

#### C0.8 — Registered production migration owner design (C0.1 docs-only amendment, 2026-09-03)

The C2 stop gate found no independent production migration owner. The existing
`StrategyDB` constructor is not a suitable substitute: it automatically runs
all registered migrations, and the retained E4 incident records that opening
production `StrategyDB` and thereby applying a migration is not an authorized
production migration checkpoint. This amendment defines the missing narrow
owner; it does not implement or execute it.

#### C0.8.1 Scope and files

The later implementation slice is limited to these files:

- Create `scripts/run_b6_successor_migration_once.py`, the only production
  migration owner for migration 005.
- Create `tests/test_run_b6_successor_migration_once.py`, using only temporary
  file-backed databases and temporary backup roots.
- Do not modify `backend/db/strategy.py`, any existing migration, the successor
  owner CLI, worker, executor, publisher, verifier, data artifact, or runbook
  in this slice.

The module must expose this testable seam:

```python
run_once(
    *,
    repo_root: Path,
    db_path: Path,
    backup_root: Path,
    connection_factory: Callable[[str], sqlite3.Connection] = sqlite3.connect,
    migration: Callable[[sqlite3.Connection], None] = migrate_add_b6_successor_attempt,
    stdout: TextIO | None = None,
    progress_stream: TextIO | None = None,
) -> tuple[int, dict[str, Any]]
```

`run_once` is injectable only for temporary tests. The production `main` has
no positional or optional arguments: it rejects every argument with exit 64,
derives the repository root from the module location, and passes only the
fixed paths `repo_root/data/strategy.db` and
`repo_root/data/strategy_backups/b6_schema_migration`. It must never accept a
database path, backup path, migration selector, dry-run flag, or user-supplied
connection from the command line.

The exact future production command is:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/run_b6_successor_migration_once.py
```

This command is not run by C0.1. It becomes eligible only after the C1c
temporary tests and fresh compile are green and the separate C2 authorization
is active.

#### C0.8.2 Read-only preflight

Before any writable connection is opened, `run_once` must open the fixed
database through a raw SQLite URI with `mode=ro`. It must fail closed unless
all of the following are true:

1. `PRAGMA quick_check` returns exactly `ok` and
   `PRAGMA foreign_key_check` returns no rows.
2. The schema elements from migrations 001 through 004 are present and
   consistent: the runtime tables/columns and foreign keys exist, the B5
   binding columns exist, migration 004's
   `idx_protocol_b6_profile_per_revision` exists, and its former partial
   unique index is absent.
3. All three migration-005 columns
   `predecessor_task_id`, `predecessor_task_key`, and
   `successor_attempt_number` are absent, and
   `uq_b6_direct_successor_predecessor` is absent. A partially present or
   malformed 005 shape is a stable blocked result, not an attempt to repair it.
4. The complete `b6_validation_tasks` schema inventory, every row's
   pre-existing column values, raw `payload_json` bytes, task status, and the
   failed predecessor identity are snapshotted. No task is selected by
   `latest`, `queued`, database order, or a scan.
5. The seven repository protected count tables, plus strategy promotions and
   human confirmation tables when present, are counted and are all zero for
   the protected evidence set. No v3/successor row exists.
6. Any migration registry is inspected read-only. This amendment does not
   invent a registry table; when none exists, the result records
   `migration_registry="absent"`.

If all three 005 columns and the exact unique partial index already exist, the
owner returns a canonical `already_applied` result with exit 0 after a fresh
read-only shape/health/row check. It performs no backup, opens no writable
connection, and does not call the migration function. If only part of the 005
shape exists, it returns `b6_schema_migration_partial_or_invalid` with exit 20
and performs no backup or write.

#### C0.8.3 Server-owned migration backup

For a not-yet-applied database, the owner creates one consistency backup after
the successful preflight and before any writable database connection. It must
use SQLite `Connection.backup` from a raw read-only source connection and a
server-owned sibling staging file, then flush/fsync and atomically publish:

```text
data/strategy_backups/b6_schema_migration/
  migration_005.<source_db_sha256>.sqlite3
  migration_005.<source_db_sha256>.sqlite3.manifest.json
  migration_005.<source_db_sha256>.sqlite3.manifest.json.sha256
```

This directory is distinct from `data/strategy_backups/b6_preclaim`; the
owner must never reuse, overwrite, or delete a preclaim backup. The manifest
schema is `b6_schema_migration_backup.v1` and contains exactly the migration
ID, source absolute path and SHA/size/mtime, source schema/row snapshot hash,
backup SHA/size/health snapshot, creation time, and owner source SHA. The
sidecar contains the manifest SHA and target filename. An exact existing
three-file set may be read-only validated and reused for the same unchanged
source identity; missing, partial, conflicting, unhealthy, or source-drifted
files return `b6_schema_migration_backup_conflict` or
`b6_schema_migration_backup_failed` with exit 20. The backup remains evidence
on every later migration failure.

The backup helper is private to the new owner module. It must not call
`backup_strategy_db_once`, `StrategyDB`, a worker, a verifier, a publisher, an
OOS ledger, or any task/successor API.

#### C0.8.4 One registered migration call and canonical output

After backup success, the owner opens exactly one writable
`sqlite3.Connection` to the fixed database, enables foreign-key enforcement,
and calls the registered function
`migrate_add_b6_successor_attempt(connection)` exactly once. It must not
instantiate `StrategyDB`, call `_run_migrations`, import or run migrations
001–004, execute inline migration SQL, create a successor, or touch OOS or
artifact state. The migration function owns its transactional
`BEGIN IMMEDIATE`/commit-or-rollback boundary; the owner rolls back any still
active transaction on an unexpected exception and closes the connection.

The owner emits stderr JSONL with schema
`b6_successor_migration_progress.v1`. Every event has exactly these fields:
`schema_version`, `event_seq`, `stage`, `migration_id`, `status`,
`source_db_sha256`, and `backup_id`. Stages are `preflight`, `backup`,
`migration`, `terminal`, `blocked`, and `failed`; `event_seq` starts at one
and increases strictly. No event contains task payloads, OOS data, secrets, or
user configuration.

The canonical `migration_id` is exactly
`migration_005_add_b6_successor_attempt` in every result and progress event.

The only stdout object has schema `b6_successor_migration.cli.v1` and exactly
these fields:
`schema_version`, `migration_id`, `status`, `db_path`, `source_db_sha256`,
`source_size_bytes`, `source_mtime_ns`, `backup_id`, `backup_path`,
`backup_manifest_path`, `backup_manifest_sidecar_path`,
`backup_db_sha256`, `backup_manifest_sha256`, `post_schema_sha256`,
`post_task_row_snapshot_sha256`, `post_health`, `post_protected_counts`,
`migration_registry`, `reason`, and `detail`. JSON is sorted-key compact
canonical JSON with UTF-8 and `allow_nan=False`.

The exit mapping is fixed: 0 for `migrated` or verified `already_applied`, 20
for preflight/backup/shape blocks, 64 for any non-empty argument list, and 70
for an unexpected migration/database failure after the backup. A non-zero
exit never retries, restores, deletes, or edits the backup.

#### C0.8.5 Raw read-only post-audit

After the one writable connection closes, the owner opens a new raw
`mode=ro` connection and verifies:

- `quick_check=ok`, empty `foreign_key_check`, and unchanged pre-existing
  tables, triggers, primary key, foreign keys, and indexes;
- exact nullable column definitions: `predecessor_task_id TEXT` with the
  self-reference to `b6_validation_tasks(task_id)`,
  `predecessor_task_key TEXT`, and `successor_attempt_number INTEGER`;
- exact unique partial index name, columns, predicate, and SQL:
  `uq_b6_direct_successor_predecessor` on
  `b6_validation_tasks(predecessor_task_id)` where the value is not null;
- every pre-existing task row and every pre-existing `payload_json` byte is
  identical to the preflight snapshot, every new successor column on those
  rows is null, and task states are unchanged;
- no v3/successor row, no OOS state/reservation/ledger, no report/Gate, no
  Promotion/Alpha/Signal evidence, and all protected counts remain zero;
- the migration backup, manifest, sidecar, source binding, health, and
  snapshot remain exact and readable through raw read-only connections;
- if a migration registry exists, its post-state is reported without adding a
  new registry as part of this amendment.

A separate read-only process snapshot after the owner exits must show no B6
worker or migration/owner process. The post-audit is evidence only and never
creates a successor or starts a worker.

#### C0.8.6 C1c TDD and C2 acceptance sequence

Create `tests/test_run_b6_successor_migration_once.py` with temporary
file-backed databases. Seed the migration-004 pre-state using the existing
temporary migration fixture pattern, not production files. Use a separate
SQLite reader for every durable assertion. Add these exact tests:

- `test_main_rejects_arguments_without_opening_database` — every argument is
  exit 64 and no connection/backup is opened;
- `test_preflight_requires_migrations_001_to_004_and_rejects_partial_005` —
  valid pre-state is accepted, missing/invalid prior shape blocks, and a
  partial 005 shape never self-repairs;
- `test_already_applied_is_stable_without_backup_or_migration_call` — exact
  005 shape returns exit 0, no backup call, no writable connection, and zero
  migration calls;
- `test_backup_precedes_the_only_writable_connection` — event order and
  manifest/source binding are asserted, and no `b6_preclaim` path is used;
- `test_registered_migration_is_called_exactly_once` — a spy around the real
  `migrate_add_b6_successor_attempt` proves one call on a temporary DB and no
  `StrategyDB` construction or migration 001–004 call;
- `test_post_audit_preserves_rows_and_adds_exact_nullable_schema` — independent
  connection proves exact columns/index/FK, byte-identical old rows/payloads,
  null new fields, healthy schema, and zero protected evidence;
- `test_migration_failure_is_failed_closed_and_preserves_backup` — injected
  migration failure returns exit 70, retains a healthy backup, performs no
  retry/restore, and leaves the pre-existing task rows unchanged;
- `test_progress_and_result_are_canonical_for_migrated_and_blocked` — exact
  stdout fields, exact progress fields/order, and exit mapping are asserted.

Run each RED node separately before the owner implementation; the expected RED
is only the missing owner module/symbol, never a production access or OOS
failure. Then run each corresponding GREEN node and the full module:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_main_rejects_arguments_without_opening_database -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_preflight_requires_migrations_001_to_004_and_rejects_partial_005 -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_already_applied_is_stable_without_backup_or_migration_call -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_backup_precedes_the_only_writable_connection -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_registered_migration_is_called_exactly_once -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_post_audit_preserves_rows_and_adds_exact_nullable_schema -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_migration_failure_is_failed_closed_and_preserves_backup -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once.test_progress_and_result_are_canonical_for_migrated_and_blocked -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m unittest tests.test_run_b6_successor_migration_once -v
D:\Codex\TraderLens\.venv\Scripts\python.exe -m py_compile scripts/run_b6_successor_migration_once.py
```

Only after all C1c tests and compile are fresh GREEN may the separately
authorized C2 command run exactly once:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/run_b6_successor_migration_once.py
```

Before that command, record the raw production `mode=ro` preflight and no-B6
process snapshot. After it exits, record the raw post-audit, migration call
count `1`, backup identity, exact old-row/payload equality, schema/index/FK
health, protected counts, and no-B6 process snapshot. A non-zero command exits
C2 permanently with the backup retained; there is no retry, restore, cleanup,
successor creation, worker invocation, OOS read, publisher/verifier call,
Promotion, Alpha, Signal, or Git step. A zero result means only
`C2 production migration verified / eligible for C3 preflight`; it does not
authorize C3, successor creation, or Phase D.

### Phase D Attempt 2 — independent read-only preflight authorization (2026-09-07)

This is a new, independent authorization after the historical Attempt 1
stopped. Attempt 1 did call the official availability verifier exactly once,
but the caller overrode the scope, coverage, and evidence roots; the verifier
returned `invalid` because the scope manifest or sidecar was missing before
complete availability binding was evaluated. Attempt 1 is consumed and must
not be retried. It performed no publisher, worker, CLI task run, OOS, artifact,
database, Promotion, Alpha, Signal, Git, delete, or cleanup action.

Attempt 2 authorizes only one read-only Phase D preflight. The official
availability verifier may be called at most once. It must use the official
CLI/server-owned defaults for `scope`, `coverage`, and `evidence`; the
preflight must not pass `--scope-dir`, `--coverage-dir`, or `--evidence-dir`.
The exact successor and formal snapshot identities and paths are:

- successor task: `62a25009b5097c76daf2798663d7f84643bdc7af2d49d366114bba47953099de`
- failed predecessor: `50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`
- successor directory:
  `D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4`
- formal snapshot directory:
  `D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a`
- expected successor manifest SHA-256:
  `082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`

The only permitted official verifier invocation is:

```powershell
D:\Codex\TraderLens\.venv\Scripts\python.exe scripts/verify_v3_availability_bounded_qualification_successor.py --successor-dir D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4 --formal-snapshot-dir D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a
```

The omitted server-owned defaults must resolve to:

- scope: `D:\Codex\TraderLens\data\pit\historical_scope_freezes\acbc49159d989a46`
- coverage: `D:\Codex\TraderLens\data\pit\v3_historical_coverage_packages\1e79d26460c0c109`
- evidence: `D:\Codex\TraderLens\data\pit\v3_historical_suspension_evidence\4871f6ba56b40e93`

The expected verifier result is JSON with `status=valid`,
`successor_id=12f1b9aac73dfcd4`, and
`manifest_sha256=082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`.
An exception, non-zero exit, malformed output, any status other than
`valid`, or any identity/hash mismatch is a terminal Attempt 2 failure. The
verifier must not be retried, and the preflight must not invoke publisher,
worker/CLI task execution, OOS, Promotion, Alpha, or Signal.

After the single verifier call, the preflight must independently perform the
fresh read-only checks required by Phase D: migration-005 owner/marker
identity, the four relevant task rows, successor queued/unclaimed state,
failed-predecessor immutability, protected reservation/state/ledger/report/
Gate counts at zero, raw SQLite health, backup/progress state, scratch/process
state, and the exact sidecar/manifest bindings. No successor backup may be
created by this attempt; an absent or complete reusable backup is acceptable.
Only if every artifact dependency and every fresh database/protected/backup/
process check passes may the result be recorded as
`PHASE D PRECHECK READY`. This status authorizes no one-draw execution; the
one-draw step remains a separate later authorization.

### Phase D Attempt 3 — module-entry read-only preflight authorization (2026-09-07)

Attempt 2 is historical and consumed. Its direct-path command reached the
V3 verifier file but failed at the top-level `from scripts...` import with
`ModuleNotFoundError: scripts`; the verifier business logic was not entered.
All artifact, database, task, protected-state, and process prechecks preceding
that call had passed. Attempt 2 was not retried and caused no publisher,
worker/CLI task, OOS, artifact, database, Promotion, Alpha, Signal, Git,
delete, or cleanup action. The direct-path command in the Attempt 2 record is
historical evidence only and is not a reusable Attempt 3 command.

The V3 verifier CLI entry contract is now minimally closed without changing
`verify_successor`, its defaults, or its business bindings: the module has a
`main(argv=None) -> int` entry, emits one JSON object, returns 0 only for
`status=valid`, returns 1 for an invalid result, and exits through
`SystemExit(main())`. The temporary no-production CLI tests cover module
`--help` loading and invalid-result JSON/exit semantics; the target CLI has
freshly compiled successfully. These facts authorize preparation only, not a
verifier run.

Attempt 3 is a new, independent authorization for one read-only Phase D
preflight. It must start from the repository root and use the module entry
below. The official availability verifier may be called at most once. Do not
pass `--scope-dir`, `--coverage-dir`, or `--evidence-dir`; those three
server-owned defaults must remain in force.

```powershell
Set-Location -LiteralPath D:\Codex\TraderLens
& D:\Codex\TraderLens\.venv\Scripts\python.exe -m scripts.verify_v3_availability_bounded_qualification_successor --successor-dir D:\Codex\TraderLens\data\pit\v3_availability_bounded_qualification_successors\12f1b9aac73dfcd4 --formal-snapshot-dir D:\Codex\TraderLens\data\pit\v3_formal_data_snapshot_manifests\v3ds_d73256081de82e8a
```

The exact successor task remains
`62a25009b5097c76daf2798663d7f84643bdc7af2d49d366114bba47953099de`, the
failed predecessor remains
`50154863a8e04066c66ef533d8fae9b097ae287f24ce3758ff9e876196d6ffb3`, and the
expected successor manifest SHA-256 remains
`082a45061556505d4e3b2613fb1a87ed878481d0d728f73c80a9564c4ebd9f91`.
The expected result is process exit 0 and one JSON object with
`status=valid`, `successor_id=12f1b9aac73dfcd4`, and that exact manifest hash.
Any exception, non-zero exit, malformed or extra stdout, non-`valid` status,
or identity/hash mismatch is terminal for Attempt 3 and must not be retried.

After the single verifier call, perform the fresh read-only artifact,
sidecar/identity, migration-005, task, raw SQLite, protected reservation/
state/ledger/report/Gate, backup/progress, scratch, and process checks required
by Phase D. Do not publish, create a backup, run worker/CLI task execution,
run OOS, or invoke Promotion, Alpha, or Signal. Only if every dependency and
fresh state check passes may the result be recorded as
`PHASE D PRECHECK READY`; that status still does not authorize one-draw,
which remains a separate later authorization.
