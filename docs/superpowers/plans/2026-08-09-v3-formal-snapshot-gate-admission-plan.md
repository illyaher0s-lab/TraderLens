# V3 Formal Snapshot and Gate Admission Implementation Plan

> **For agentic workers:** Execute this plan inline with focused RED → GREEN checkpoints. Do not commit or enter downstream workflow stages.

**Goal:** Publish exact v3 formal snapshot and availability-bounded successor artifacts, admit them through freezer Gates 1–4, then stop at the next real prerequisite.

**Architecture:** Add a v3-only metadata snapshot publisher/verifier and a v3-only successor publisher/verifier. Extend `DataSnapshotManifest` with strict optional v3 fields while preserving legacy validation, then dispatch freezer Gates 1–4 by explicit v3 schema/identity. Update one-shot prerequisite discovery only after read-only Gate 1–4 validation.

**Tech Stack:** Python, Pydantic, JSON/Parquet SHA-256 manifests, pytest, SQLite read-only checks.

---

### Task 1: Establish focused RED coverage

**Files:**
- Create: `tests/test_v3_formal_snapshot.py`
- Create: `tests/test_v3_availability_successor.py`
- Modify: `tests/test_b6_protocol_freezer.py`
- Modify: `tests/test_run_v3_task4_once.py`

- [ ] Add real-boundary tests for v3 identity, scope/coverage/source tamper, `data_fault > 0`, authorization disclosure, write-once, legacy `ds_001` compatibility, v2 successor rejection, and Gate 1–4-only admission.
- [ ] Run each focused file separately and record the expected missing-symbol or legacy-contract RED failure.

### Task 2: Implement the minimum v3 formal snapshot contract

**Files:**
- Modify: `backend/services/b3_protocol_types.py`
- Create: `scripts/publish_v3_formal_snapshot.py`
- Create: `scripts/verify_v3_formal_snapshot.py`

- [ ] Add strict optional v3 fields and validation requiring complete exact bindings before `not_authorized_for_b6_oos_gate_promotion_signal=False`.
- [ ] Build deterministic metadata-only snapshot payload from the existing scope, coverage, evidence, membership, lifecycle, B3, and source manifests; publish write-once manifest and sidecars.
- [ ] Independently verify all bound hashes and coverage arithmetic without copying data.
- [ ] Run snapshot-focused tests GREEN.

### Task 3: Implement the v3 availability successor

**Files:**
- Create: `scripts/build_v3_availability_bounded_qualification_successor.py`
- Create: `scripts/verify_v3_availability_bounded_qualification_successor.py`

- [ ] Bind the v3 scope, coverage, formal snapshot, evidence, adapter, template, requirements, and parquet hashes.
- [ ] Set `availability_bounded_qualified` and the explicit b6 coverage-bound authorization scope; reject legacy v1/v2 inputs.
- [ ] Publish once in the new v3 successor root and independently verify.

### Task 4: Admit v3 through freezer Gates 1–4

**Files:**
- Modify: `backend/services/research_protocol_freezer.py`
- Modify: `contracts/strategy.py` only if the preflight result needs a minimal stable field.

- [ ] Add explicit v3 schema dispatch that calls the v3 successor and snapshot verifiers, validates exact approved v3 identity, and leaves Gate 5+ unchanged.
- [ ] Run the freezer read-only preflight once with real v3 artifact paths and record the first returned prerequisite.

### Task 5: Update one-shot prerequisite discovery and verify boundaries

**Files:**
- Modify: `scripts/run_v3_task4_once.py`
- Modify: `tests/test_run_v3_task4_once.py`

- [ ] Add read-only artifact discovery and independent Gate 1–4 validation to the real one-shot path, preserving audit injection and no DB/task/OOS writes.
- [ ] Run one production one-shot, compare DB counts before/after, and stop at its actual first blocker.
- [ ] Run only the required focused verification commands; do not run historical qualifier, protocol freeze, B4, OOS, Gate 5+, Promotion, or Signal.
