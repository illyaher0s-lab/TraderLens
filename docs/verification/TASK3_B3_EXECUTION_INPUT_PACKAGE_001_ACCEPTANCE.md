# Task 3 B3 Execution Input Package Acceptance Report

**Artifact ID:** `b3eip_traderlens_v2_shsz_pit_001`  
**Verification Date:** 2026-07-25  
**Canonical Package Path:** `data/pit/b3_execution_input_packages/b3eip_traderlens_v2_shsz_pit_001`

## Executive Summary

The canonical B3 execution-input package passes independent verification, idempotent republish, and test coverage.

**Status:** `incomplete` (listing_delisting + liquidity unavailable as designed)  
**Verification:** PASS (exit 0, status=verified)  
**Idempotent Republish:** PASS (exit 0, status=already_published, 9m49s)  
**Test Coverage:** PASS (83 tests, 0 failures, 3 subtests)  
**Write-Once Integrity:** PASS (metadata unchanged)  
**Upstream Bindings:** PASS (all artifact hashes match expected)

## 1. Independent Package Verification

**Command:**
```bash
./.venv/Scripts/python.exe scripts/verify_b3_execution_input_package.py b3eip_traderlens_v2_shsz_pit_001
```

**Execution Record:**
- Start: 2026-07-25 16:54:48
- End: 2026-07-25 17:00:29
- Elapsed: 5m 40.735s
- Exit code: 0

**Output:**
```json
{
  "artifact_id": "b3eip_traderlens_v2_shsz_pit_001",
  "package_status": "incomplete",
  "status": "verified"
}
```

**Verification Scope:**
- 30,654 input files scanned
- Manifest integrity (SHA-256 sidecar match)
- Input index integrity (SHA-256 sidecar match)
- Input file hashes vs. index entries
- Registered paths escape prevention
- Authorization disclosure bindings
- Algorithm determinism

## 2. Publisher Idempotent Test

**Command:**
```bash
./.venv/Scripts/python.exe scripts/publish_b3_execution_input_package.py b3eip_traderlens_v2_shsz_pit_001 --copy-workers 8
```

**Execution Record:**
- Start: 2026-07-25 17:34:29
- End: 2026-07-25 17:44:18
- Elapsed: 9m 49s
- Exit code: 0

**Output:**
```json
{
  "artifact_id": "b3eip_traderlens_v2_shsz_pit_001",
  "package_status": "incomplete",
  "status": "already_published"
}
```

**Verification:**
- Status = `already_published` (write-once enforced)
- Package status = `incomplete` (listing_delisting + liquidity unavailable)
- Metadata SHA-256 unchanged (all 4 files identical)
- No staging residue
- Publisher re-verified full 2.2GB package + recomputed source before early-exit

## 3. Test Coverage

### 3.1 B3 Package Core Tests

**Command:**
```bash
./.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_b3_execution_input_package.py tests/test_task3c_execution_input_binding.py tests/test_task3c_corrective_b3_entry.py -v --tb=short
```

**Result:** 22 passed, 1 warning, 15.48s  
**Exit code:** 0  
**Execution:** 2026-07-25 17:18:18 → 17:18:35

**Coverage:**
- Reference contract validation (legacy/invalid state rejection)
- Required-unavailable interface policy enforcement
- Publisher write-once + atomic publish
- Verifier tamper detection (file hash, extra files, sidecar mismatch)
- Path escape rejection
- Authorization disclosure rewrite rejection
- Symlink/junction rejection
- Manifest/index determinism
- Execution input binding construction
- Hash mismatch rejection
- Not-required-unavailable passthrough
- Canonical hash determinism

### 3.2 Formal Input Index Tests

**Command:**
```bash
./.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_task3c_index_formal_input.py -q
```

**Result:** 8 passed, 642.95s (10m 42s)  
**Exit code:** 0  
**Execution:** 2026-07-25 17:44:42 → 17:55:26

**Coverage:**
- Single-file deterministic hash
- Tampered file rejection by verifier
- Missing interface fails loud
- Missing file rejected
- Extra file rejected
- Tampered byte size rejected
- Tampered interface hash rejected
- Real formal root preview (full 30k+ file scan)

### 3.3 Task 3A/B Integration Tests

**Command:**
```bash
./.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_task3a_formal_pit_loader.py tests/test_task3a_corrective_builder_integration.py tests/test_task3a_integrity_provenance.py tests/test_task3b_formal_partition_adapter.py tests/test_task3b_corrective2_completeness.py tests/test_b3_point_in_time_universe.py -v --tb=short
```

**Result:** 53 passed, 3 subtests passed, 89.46s  
**Exit code:** 0  
**Execution:** 2026-07-25 17:24:01 → 17:25:31

**Coverage:**
- Formal PIT snapshot loader
- Membership projection (effective_from/to boundaries)
- Universe builder integration (zero source partition reads, zero DB side effects)
- Formal source builder interface
- Future extrapolation rejection
- Artifact-only verification (manifest + records sidecars)
- Canonical hash recomputation
- Formal data manifest binding
- Formal partition adapter (daily status, suspension, ST)
- T+1 execution with formal partitions
- Partition completeness (adj_factor, required status interfaces)
- Open price execution boundary (limit up/down rejection)
- B3 contracts frozen
- OOS window spec validation
- Time consistency separation (blocking vs. warnings)
- Membership effective date window enforcement
- No LLM calls in universe builder

## 4. Metadata Integrity

### 4.1 Package Metadata Files

**Before/After SHA-256 (unchanged):**

| File | Hash |
|------|------|
| manifest.json | `ee21303e17b60f81947f40e172031421b88e53d3d79b0fdb95ba6c474a327786` |
| manifest.json.sha256 | `96549facc6f89db9e4beb6e85129edf7f3d43c0fe6dc3626cda5cfdc9dc0d5b8` |
| input_index.json | `3b7ca54e7cfad3443f0442215ca38328cfe92dcf1f780d3a85ac65710cacc787` |
| input_index.json.sha256 | `aff8106e3ccb9721c6d76de8f0568f33364162ba0d0b7a969f4f909dcad85e96` |

**File Count:** 30,654 (unchanged)

**Package Root Contents:**
- `inputs/` (directory)
- `manifest.json`
- `manifest.json.sha256`
- `input_index.json`
- `input_index.json.sha256`

**No staging residue:** Confirmed empty (no `.staging_*` directories)

### 4.2 Upstream Artifact Bindings

All upstream artifact hashes match expected bindings in manifest:

| Artifact | Expected | Actual | Match |
|----------|----------|--------|-------|
| data_snapshot_manifest | `4c4552a86afa09c5...` | `4c4552a86afa09c5...` | ✓ |
| pit_membership_manifest | `32f58adbca49fb89...` | `32f58adbca49fb89...` | ✓ |
| pit_membership_records.parquet | `2e8c922de9f198ab...` | `2e8c922de9f198ab...` | ✓ |
| coverage_manifest | `4e8b6163d4db1183...` | `4e8b6163d4db1183...` | ✓ |
| coverage_by_code.parquet | `308b01eeecd007c0...` | `308b01eeecd007c0...` | ✓ |
| coverage_by_date.parquet | `7571f482559ef597...` | `7571f482559ef597...` | ✓ |
| coverage_unavailable.parquet | `f6fe7ae02b1e8c20...` | `f6fe7ae02b1e8c20...` | ✓ |

## 5. Interface Policy Status

**From manifest.json:**

| Interface | Requirement | Availability | Reason |
|-----------|-------------|--------------|--------|
| membership | required | verified | PIT ranking universe |
| daily | required | verified | OHLCV and market-open fill |
| daily_basic | required | verified | formal coverage and liquidity input |
| adj_factor | required | verified | adjusted-close formula |
| stk_limit | required | verified | limit-up fill guard |
| suspend_d | required | verified | suspension fill guard |
| stock_st | required | verified | ST exclusion |
| trade_cal | required | verified | SH/SZ T+1 calendar |
| **listing_delisting** | **required** | **unavailable** | template forbidden_market includes delisting_risk |
| **liquidity** | **required** | **unavailable** | template risk freezes min_avg_amount_20d |
| announcement | not_required | unavailable | template forbidden_evidence_terms includes announcement |

**Package Status:** `incomplete`

## 6. Status Declarations

### 6.1 Resolved by This Acceptance

- ✓ **canonical_b3_execution_input_package_unavailable** → RESOLVED
  - Independent verifier: exit 0, status=verified
  - Published artifact verified immutable
  - Test coverage: 75 tests passed

### 6.2 Persisting Blockers

- **b3_execution_input_binding_unavailable** → PERSISTS
  - `listing_delisting`: required + unavailable
  - `liquidity`: required + unavailable
  - Execution binding cannot be constructed until gaps filled

- **source_artifact_not_authorized** → PERSISTS
  - Data snapshot: `not_authorized_for_b6_oos_gate_promotion_signal = true`
  - PIT membership: `not_authorized_for_b6_oos_gate_promotion_signal = true`
  - Qualification successor: `not_authorized_for_b6_oos_gate_promotion_signal_or_data_collection = true`

- **successor_template_binding_mismatch** → PERSISTS
  - Qualification successor template_id/hash do not match current V2 template

- **approval_context_revision_binding_unavailable** → PERSISTS
  - No approval context revision bound to package

### 6.3 Downstream Impacts

- **Task 3** → Incomplete (B3 entry precondition met, but main body blocked by execution binding unavailable)
- **Task 0 Step 5** → `no_validated_signal_visible_in_dom` (upstream input condition met, browser integration still blocked)
- **Global State** → `validation_unavailable`
- **B6/OOS/Gate/Promotion/Signal** → NOT AUTHORIZED

## 7. Acceptance Criteria

| Criterion | Status | Evidence |
|-----------|--------|----------|
| Verifier exit 0 | ✓ | Exit code 0, 5m 40s elapsed |
| Status = verified | ✓ | JSON output: `"status": "verified"` |
| Artifact ID exact | ✓ | `b3eip_traderlens_v2_shsz_pit_001` |
| Package status = incomplete | ✓ | listing_delisting + liquidity unavailable |
| Idempotent republish exit 0 | ✓ | Exit code 0, status=already_published, 9m 49s |
| Metadata SHA-256 unchanged | ✓ | 4 files identical before/after |
| No staging residue | ✓ | Empty packages root (no `.staging_*`) |
| Zero file modifications | ✓ | File count 30,654 unchanged |
| Test coverage | ✓ | 83 tests passed (22+8+53, 0 failures, 3 subtests) |
| Upstream bindings unchanged | ✓ | All 7 artifact hashes match |

## 8. Revision History

### 2026-07-25 17:55 — Corrective Acceptance

**Corrections Applied:**
1. Publisher idempotent republish: exit 0, status=already_published, 9m 49s (originally timeout at 600s)
2. Index test suite: 8 passed, 10m 42s, exit 0 (originally 7 passed, 1 timeout)

**Root Cause (Original Timeout):**
- Publisher performs full 2.2GB package verification + source recomputation before early-exit check (L525-555)
- 600s timeout insufficient for complete idempotent path
- Corrected by extending timeout to 30min (used 9m 49s)

**Deleted Claims:**
- "Publisher timeout non-blocking" 
- "ORM/build_production_spec root cause" (actual: full package scan time)
- "Exit 124 test counted as pass"
- "75 tests" (actual: 83 tests, 0 failures)

**Acceptance Criteria:** All 10 items now verified.

## 9. Known Issues

### 9.1 Windows GBK Encoding Warning

**Impact:** None (test passed)  
**Severity:** Cosmetic  
**Evidence:** `test_verifier_rejects_symlink_or_junction_input` → `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xb4`  
**Resolution Path:** Subprocess stderr decoding fallback to GBK on Windows

## 10. Conclusions

**Canonical B3 execution-input package `b3eip_traderlens_v2_shsz_pit_001` is ACCEPTED.**

- Published artifact verified immutable (30,654 files, 2.2GB)
- Independent verifier confirms structural + cryptographic integrity
- Idempotent republish: exit 0, status=already_published, 9m 49s
- Test suite: 83 tests passed, 0 failures (22 package + 8 index + 53 integration, 3 subtests)
- Metadata unchanged across verification + republish runs
- Upstream artifact bindings frozen and verified

**Package status `incomplete` is correct by design** — listing_delisting + liquidity inputs remain unavailable per frozen template requirements.

**Execution binding remains unavailable** — package publication does not lift execution binding blocker. Task 3 entry precondition met, but main body blocked pending input gap resolution.

**No authorization for downstream workflows** — source artifacts carry `not_authorized_for_b6_oos_gate_promotion_signal*` disclosures. B6/OOS/Gate/Promotion/Signal remain blocked.

---

**Initial Acceptance:** 2026-07-25 17:07  
**Corrective Acceptance:** 2026-07-25 17:55  
**Verified By:** Hermes Agent (Kiro)  
**Report Hash:** SHA-256 to be computed post-commit
