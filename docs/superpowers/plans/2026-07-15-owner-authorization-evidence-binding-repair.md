# Owner Authorization Evidence Binding Repair Implementation Plan

> **For agentic workers:** Execute inline with focused RED → GREEN checks. Do not create a worktree or commit; this shared worktree is intentionally dirty.

**Goal:** Make the existing V2 owner authorization verifiable against the final AI-review document bytes at every template conversion entry point.

**Architecture:** Keep `governance_map` as the sole authorization source. Its V2 record carries only repo-relative review evidence and canonical authorization fields. Conversion recomputes the review SHA-256, rejects a missing/mismatched review to `candidate`, and exposes canonical review/authorization hashes through the existing template contract.

**Tech Stack:** Python standard library (`hashlib`, `json`, `Path`), Pydantic, pytest.

---

### Task 1: Bind owner authorization to immutable review evidence

**Files:**
- Modify: `contracts/strategy.py`
- Modify: `backend/services/strategy_template_library.py`
- Modify: `tests/test_owner_authorization_binding.py`
- Modify: `docs/verification/TASK1_V2_AI_TECHNICAL_REVIEW.md`
- Modify: `docs/verification/TASK1_E_OWNER_AUTHORIZATION_BINDING.md`

- [ ] **Step 1: Write RED tests**

Add focused tests that use a copied review file under a temporary repository root. They must assert that a missing file, changed bytes, or an incorrect expected SHA-256 produces `candidate`; that `list_approved_templates()` excludes V2; and that the real `B6ValidationFlow.run_minimal_validation()` blocks before ledger reserve/runner/Gate. Add a positive assertion that the approved frozen contract exposes `review_evidence_path`, `review_evidence_sha256`, `owner_authorization_hash`, `authorized_by`, and `authorized_at`.

- [ ] **Step 2: Verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_owner_authorization_binding.py -q
```

Expected: failures because conversion currently neither hashes review bytes nor exposes the required contract fields.

- [ ] **Step 3: Implement the minimal shared conversion guard**

Keep the authorization only in the V2 `governance_map` record. Add repo-relative `review_evidence_path` and final-byte `review_evidence_sha256`; canonicalize the required authorization payload with sorted-key compact JSON; calculate `owner_authorization_hash`; include that hash and the actual effective governance status in `governance_evidence_hash`. Extend the existing contract with optional review/authorization fields and make its `approved` validator require them. Delete or reject the unused `owner_authorization` call parameter.

- [ ] **Step 4: Verify GREEN and regressions**

Run separately:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_owner_authorization_binding.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_relative_strength_v2_candidate.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_template_governance_v2.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_b6_validation_flow.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_b2_template_library.py -q
```

- [ ] **Step 5: Correct both evidence reports from actual output**

Record each exact command, exit code, pytest count, and subtest count separately. Freeze the AI-review document only after its final count correction, then compute and record its byte SHA-256 in the owner authorization report.

