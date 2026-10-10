# Task 4 / B6 Runtime Schema & Persistence Audit

**Date:** 2026-07-18  
**Auditor:** Hermes Agent  
**Scope:** StrategyDB schema readiness for approved B6 runtime design  
**Method:** Read-only code inspection

---

## Executive Summary

**Status:** 3 critical gaps found (schema, transaction semantics, design conflicts)

**Key Findings:**
1. **Schema gaps:** No tasks table, no protocol_profile field, no task_key mechanism
2. **Transaction semantics:** B6ValidationFlow writes report/Gate in Promotion branch only (violates design)
3. **Design conflict:** run_minimal_validation() still accepts human_decision (design explicitly forbids)

**Conclusion:** Current StrategyDB schema and B6ValidationFlow transaction boundaries do NOT comply with approved B6 runtime design. Minimum implementation requires: schema migration, B6ValidationFlow refactor, new application service.

---

## A. StrategyDB Capability Audit

### A.1 Existing Schema

Evidence: backend/db/strategy.py:62-298

| Table | Primary Key | Unique Constraints | Foreign Keys | Status |
|-------|-------------|-------------------|--------------|--------|
| strategy_drafts | strategy_revision_id | - | backtest_universe_spec_id | ✓ Exists |
| research_protocol_snapshots | protocol_snapshot_id | - | strategy_revision_id | ✓ Exists |
| oos_budget_state | (theme_id, hypothesis_source_snapshot_id) | - | - | ✓ Exists |
| oos_budget_reservations | reservation_id | uq_oos_idempotency_per_owner | FK to oos_budget_state | ✓ Exists |
| immutable_backtest_reports | report_id | report_hash | strategy_revision_id, protocol_snapshot_id | ✓ Exists |
| prototype_gate_results_v2 | gate_result_id | gate_result_hash | strategy_revision_id, report_id | ✓ Exists |
| **tasks** | - | - | - | ✗ Missing |

Database path: data/traderlens.sqlite3 (no tasks table confirmed via sqlite3 inspection)

---

### A.2 Gap Matrix

| Design Requirement | Current Schema Evidence | Gap | File |
|-------------------|------------------------|-----|------|
| tasks table | ✗ Does not exist | Completely missing | N/A |
| task_key (deterministic SHA-256) | ✗ No field | Need tasks.task_key TEXT UNIQUE | N/A |
| task_type | ✗ No field | Need tasks.task_type TEXT | N/A |
| status (queued/running/blocked/completed/failed) | ✗ No field | Need tasks.status TEXT CHECK | N/A |
| protocol_profile (b6_coverage_bound) | ✗ research_protocol_snapshots missing | Need protocol_profile field + B6 unique constraint | backend/db/strategy.py:114-124 |
| B6 binding fields | ✗ research_protocol_snapshots missing | Need availability_qualification_successor_id, etc. | Same |
| task_key → reservation_id link | ✗ oos_budget_reservations missing task_key | Need task_key TEXT column | backend/db/strategy.py:241-262 |
| Conditional claim | ✗ No tasks table | worker.py needs conditional UPDATE | backend/app/worker.py:34-40 |

**Current worker.py implementation (violates design):**
- Line 21-40: SELECT first, then unconditional UPDATE (not atomic claim)
- Design requires: UPDATE ... WHERE status='queued' AND ... with rowcount=1 check

---

### A.3 OOS Ledger Transaction Semantics

| Design Requirement | Current Implementation | Compliance | Evidence |
|-------------------|----------------------|-----------|----------|
| Reserve short transaction | ✓ BEGIN IMMEDIATE → writes → COMMIT | ✓ Compliant | backend/services/oos_budget_ledger.py:106-221 |
| Terminal short transaction | ✗ B6ValidationFlow writes DB after ledger complete | ✗ Non-compliant | backend/services/b6_validation_flow.py:300-330 |
| Idempotent reserve | ✓ uq_oos_idempotency_per_owner + return existing | ✓ Compliant | oos_budget_ledger.py:109-132 |
| Idempotent complete | ✓ Checks existing_report == report_id | ✓ Compliant | oos_budget_ledger.py:305-312 |
| No cross-DB writes | ✓ OOSBudgetLedger uses only self.db | ✓ Compliant | oos_budget_ledger.py:41 |

**Key finding:** OOSBudgetLedger itself complies with short-transaction design, but B6ValidationFlow call order violates design.

---

## B. B6ValidationFlow Design Conflicts

### B.1 Terminal Transaction Boundary Conflict

**Design (2026-07-18-b6-runtime-validation-task-design.md section 6):**
> After OOS returns, every successful validation writes in one terminal transaction: (1) immutable report and Gate result; (2) completed ledger/reservation state; (3) task completed state.

**Current implementation (backend/services/b6_validation_flow.py:300-330):**

Line 300-304: Complete reservation first (transaction 1)
Line 318-319: Write report + Gate later (transactions 2, 3) inside Promotion branch only

**Conflict:**
1. Design requires report/Gate/ledger in ONE transaction
2. Current splits into 4 independent transactions
3. If store_gate_result() fails, ledger already completed and cannot rollback

**Root cause:** StrategyDB store_* methods each auto-commit (e.g. strategy.py:446)

---

### B.2 Report/Gate Only Written in Promotion Branch

**Design (B6_PROTOCOL_FREEZE_CONTRACT_BINDING_DESIGN.md):**
> A successful validation persists its report and Gate even when no Promotion occurs.

**Current implementation (b6_validation_flow.py:310-319):**
- Only writes report/Gate inside Promotion branch
- If verdict = rejected/needs_review OR human_decision != approve, report/Gate NOT persisted

**Conflict:** Design requires ANY successful validation to persist report/Gate

---

### B.3 human_decision Parameter

**Design (2026-07-18-b6-runtime-validation-task-design.md section 6):**
> The B6 validation API and worker do not accept human_decision.

**Current implementation (b6_validation_flow.py:51, 64, 93, 315):**
- run_minimal_validation() accepts human_decision parameter
- Line 315 uses human_decision == "approve" condition

**Conflict:** B6 should produce report/Gate; Promotion is independent subsequent step

---

## C. Minimum Implementation Boundary

### C.1 Schema Migration

**File:** backend/db/migrations/migration_002_add_b6_runtime_schema.py (new)

**Required changes:**
1. CREATE TABLE tasks (task_id, task_key UNIQUE, task_type, status CHECK, protocol_snapshot_id FK, ...)
2. ALTER TABLE research_protocol_snapshots ADD protocol_profile, B6 binding fields, unique constraint
3. ALTER TABLE oos_budget_reservations ADD task_key, protocol_snapshot_id FK

---

### C.2 StrategyDB API Extensions

**File:** backend/db/strategy.py (modify)

**Required additions:**
1. create_task_if_not_exists() - idempotent task creation
2. claim_task() - conditional UPDATE WHERE status='queued'
3. update_task_status() - terminal state update
4. get_task_by_key() - read by deterministic key
5. store_b6_terminal_result_tx() - ONE transaction for report + Gate + ledger + task

---

### C.3 B6ValidationFlow Refactor

**File:** backend/services/b6_validation_flow.py (modify)

**Required changes:**
1. Remove human_decision parameter
2. Replace terminal writes with store_b6_terminal_result_tx() call
3. Always persist report/Gate (remove Promotion branch condition)
4. Remove Promotion logic (independent subsequent step)

---

### C.4 Application Service

**File:** backend/services/strategy_validation_request_service.py (new)

**Responsibilities:**
1. Read Approval Card context + strategy revision
2. Resolve exactly-one B6 protocol
3. Compute deterministic task_key
4. Run first preflight (read-only checks)
5. create_task_if_not_exists() and return task state

---

### C.5 API Endpoint

**File:** backend/api/strategy_validations.py (modify)

**Add:** POST /api/strategy-validations/{strategy_revision_id}/continue

---

### C.6 Worker Executor

**File:** backend/app/b6_executor.py (new) or modify worker.py

**Responsibilities:**
1. Conditional claim
2. Second preflight
3. Call B6ValidationFlow.run_minimal_validation()
4. Handle terminal states

---

### C.7 Composition Root Wiring

**File:** backend/app/main.py (modify)

**startup event additions:** Construct StrategyDB, OOSBudgetLedger, B6ValidationFlow, register executor

---

## D. Implementation Boundary Summary

| Component | File | Change Type | Necessity |
|-----------|------|-------------|-----------|
| Schema migration | backend/db/migrations/migration_002_add_b6_runtime_schema.py | New | ✓ Required |
| StrategyDB API | backend/db/strategy.py | Extend | ✓ Required |
| B6ValidationFlow | backend/services/b6_validation_flow.py | Refactor | ✓ Required |
| Application service | backend/services/strategy_validation_request_service.py | New | ✓ Required |
| API endpoint | backend/api/strategy_validations.py | Add POST | ✓ Required |
| Worker executor | backend/app/b6_executor.py | New | ✓ Required |
| Composition root | backend/app/main.py | Extend | ✓ Required |

**Out of scope:** Second task DB, Saga/outbox, generic workflow engine, new approval system, freeze_b6_coverage_bound_protocol() implementation

---

## E. Test Gaps

| Design Test Requirement | Current File | Status | Gap |
|------------------------|--------------|--------|-----|
| First unavailable request zero task write | tests/test_b6_oos_ledger_boundary.py | ✓ Partial | Need extend to tasks table |
| Repeat clicks idempotency | - | ✗ Missing | Need new test |
| Concurrent claim | tests/test_oos_budget_ledger_persistence.py | ✓ Partial | Need extend to tasks table |
| Terminal transaction atomicity | - | ✗ Missing | Need new test |
| Task_key uniqueness | - | ✗ Missing | Need new test |
| Worker second preflight writes only blocked | - | ✗ Missing | Need new test |
| B6 rejects human_decision | tests/test_b6_validation_flow.py | ✗ Currently accepts | Need modify test |
| Report/Gate persist without Promotion | tests/test_b6_validation_flow.py | ✗ Currently Promotion-only | Need modify test |

---

## F. Current State Declaration

- Task 3 = not complete (runtime entry unavailable, see TASK3_RUNTIME_B3_READINESS_AUDIT.md)
- Task 4 = not started (this audit only confirms implementation boundary)
- Task 0 Step 5 = no_validated_signal_visible_in_dom (upstream condition unavailable)
- Workflow status = validation_unavailable (correct)

This audit:
- ✓ Confirmed StrategyDB schema and B6ValidationFlow transaction boundary gaps vs approved design
- ✓ Listed minimum implementation boundary (7 file changes)
- ✗ Does NOT modify any files or schema
- ✗ Does NOT execute B6/OOS/Gate/Promotion/Signal
- ✗ Does NOT mark Task 4 started/complete
- ✗ Does NOT remove Task 0 Step 5 browser blocker

---

## G. Risks & Dependencies

### G.1 Load-Bearing Product/Architecture Choices

None found. All changes implementable within existing StrategyDB + SQLite + OOS ledger architecture.

### G.2 Data Migration Risk (Low)

- protocol_profile defaults to legacy_b3 (protects existing data)
- tasks table empty initialization
- oos_budget_reservations extensions nullable

### G.3 Test Coverage Gap (Medium)

- Existing tests cover OOS ledger short transactions
- Missing terminal transaction atomicity tests
- Missing tasks table concurrent claim tests

---

## H. Recommended Implementation Order

1. Migration + StrategyDB API (atomic change, independently testable)
2. B6ValidationFlow refactor (remove human_decision, use terminal helper)
3. Application service + API endpoint (testable with in-memory StrategyDB)
4. Worker executor + composition root (final integration)

Each stage has independent test boundary for incremental delivery.

---

## Conclusion

**Minimum implementation boundary confirmed:** 7 file changes (1 migration + 6 new/modified service layer)

**Major conflicts:**
1. Schema missing tasks table and protocol_profile
2. B6ValidationFlow terminal transaction non-compliant (split across multiple commits)
3. human_decision parameter violates design

**Implementability:** High. All changes within existing single-StrategyDB architecture. No new DB, saga, outbox, or generic workflow required.

**Next step:** After Task 3 runtime wiring complete, can begin Task 4 implementation per this audit boundary.
