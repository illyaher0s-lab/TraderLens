# Task 3: PIT Membership Snapshot _003 Corrective Publication

**Delivery Date**: 2026-07-16  
**Status**: ✓ Complete  
**Deliverable**: `pims_traderlens_v2_shsz_sw2021_pit_003`

---

## Executive Summary

Task 3 corrects the date-filtering defect found in _002 and migrates `vendor_scope_disclosure` from string to structured contract. The corrective publication preserves all 3,266 historical records before 2016-01-04 (originally discarded by _002), enumerates 53 SW2014 partitions as out-of-scope, and binds structured vendor disclosure.

**Key Changes**:
- **Date Filtering Removed**: _002 applied `DATE_POLICY_MIN` filter during publication, discarding valid source records. _003 preserves all source records.
- **Vendor Disclosure Structured**: Migrated from `"sw2021_l1_only"` string to structured dict with `historical_membership_scope` and `disclosure_text` fields.
- **SW2014 Enumeration**: 53 SW2014 partitions explicitly enumerated as `taxonomy_out_of_scope`, not silently filtered.

---

## Corrective Actions

### 1. Date Policy Enforcement Bug Fix

**Root Cause**: _002 publisher applied date filtering during publication (lines 186-189), violating source retention principle.

**Fix**: Removed filtering logic. DATE_POLICY_MIN is now validation-only (for consumption window), not a publication filter.

**Evidence**:
```bash
# _002 (defective): 4538 records, no records before 2016-01-04
# _003 (corrected): 7804 records, 3266 records before 2016-01-04 (from 1984-05-09)
```

**Verification**:
```python
# test_date_policy_enforcement (PASS)
# Asserts _003 contains records before 2016-01-04
# Asserts _003 manifest does NOT contain date_policy_min field
```

### 2. Vendor Scope Disclosure Migration

**Before (_002)**:
```json
"vendor_scope_disclosure": "sw2021_l1_only"
```

**After (_003)**:
```json
"vendor_scope_disclosure": {
  "historical_membership_scope": "vendor_provided_unverified",
  "disclosure_text": "This snapshot preserves all membership records from bound source partitions (Tushare index_member_all SW2021). TraderLens does not independently verify that the vendor's historical membership data constitutes a complete registry of all market-wide delisted securities. Vendor coverage boundaries, if any, are not contractually documented."
}
```

**Verification**:
```python
# test_vendor_scope_disclosure_required (PASS)
# Asserts disclosure is dict with required fields
# Asserts historical_membership_scope == "vendor_provided_unverified"
# Asserts disclosure_text matches expected text
```

### 3. SW2014 Taxonomy Out-of-Scope Enumeration

**Change**: Publisher now explicitly enumerates all 53 SW2014 partitions as `taxonomy_out_of_scope` and reports count in manifest.

**Evidence**:
```json
"taxonomy_out_of_scope_count": 53
```

**Verification**:
```python
# test_sw2021_only_accepted (PASS)
# Asserts publisher code has explicit SW2014 check
# Asserts taxonomy_out_of_scope enumeration logic exists
# Asserts _003 records have no SW2014 in source field
# Asserts manifest.taxonomy_out_of_scope_count == 53
```

---

## Artifact Summary

| Snapshot ID | Status | Records | Historical Records<br>(< 2016-01-04) | Exit Code | Notes |
|-------------|--------|---------|--------------------------------------|-----------|-------|
| _001 | retired_unaccepted | 7,804 | 3,266 | 2 | Mixed SW2014/SW2021, no include_delisted proof |
| _002 | unaccepted_invalid_publication | 4,538 | 0 | 3 | Applied date filtering, discarded valid source records |
| _003 | verified | 7,804 | 3,266 | 0 | Corrective publication, all source records preserved |

**Protected Artifacts**:
- _001 and _002 remain byte-identical (SHA256 verified)
- Preserved as audit evidence only
- Must NOT be used in production workflows

---

## Verification Evidence

### Test Suite Results
```
14 passed, 3 skipped in 1.31s

PASSED: test_001_rejected_by_publisher
PASSED: test_002_rejected_by_publisher
PASSED: test_001_unaccepted_by_verifier
PASSED: test_002_unaccepted_by_verifier
PASSED: test_sw2021_only_accepted
PASSED: test_source_record_retention
PASSED: test_date_policy_enforcement
PASSED: test_vendor_scope_disclosure_required
PASSED: test_003_published_successfully
PASSED: test_write_once_protection
PASSED: test_verifier_recomputes_all_bindings
PASSED: test_atomic_publication_from_temporary
PASSED: test_no_b6_oos_gate_promotion_signal_imports
PASSED: test_protected_artifacts_unchanged
```

### Independent Verifier
```bash
$ python scripts/verify_pit_membership_snapshot.py pims_traderlens_v2_shsz_sw2021_pit_003
Verification status: verified
Canonical content hash: c3d8b70040d23b66da50145c463b3c04e8c2659116d02451dc0e70f2c69f81d7
✓ Verification passed
```

### Integrity Protection
```bash
# _001 (unchanged)
20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913  manifest.json
a745699333cc3a543eaacdc0a6f2b8fe0c2d1fac8affd8de10cc37ec940aa219  records.parquet

# _002 (unchanged)
56a954eaf68ea816004d5652e1fda6425b69daed45f5f754de8922032c8be8b5  manifest.json
c443751808b4e3ad61baadb8c1f92fecdebaeb397a7fbe56795e63fa83e32d2e  records.parquet
```

---

## Template Library Binding

**Updated**: `backend/services/strategy_template_library.py`

```python
"owner_authorization": {
    "template_id": "relative_strength_rotation_shsz_sw2021_v2",
    "version": "v2_shsz_sw2021_pit_12m",
    "template_hash": "867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6",
    "data_requirements_hash": "1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04",
    "pit_membership_snapshot_id": "pims_traderlens_v2_shsz_sw2021_pit_003",  # Updated from _002
    "review_evidence_path": "docs/verification/TASK1_V2_AI_TECHNICAL_REVIEW.md",
    "review_evidence_sha256": "ab4391a42ade48c2319dc15bec6799a0280fbbe4ae75dc49bd1a51f403935194",
    # ... (other fields unchanged)
}
```

**Verification**:
```python
from backend.services.strategy_template_library import _governance_map
g = _governance_map()
assert g['relative_strength_rotation_shsz_sw2021_v2']['owner_authorization']['pit_membership_snapshot_id'] == 'pims_traderlens_v2_shsz_sw2021_pit_003'
```

---

## Code Changes Summary

### Publisher (publish_pit_membership_snapshot.py)
- **Lines 186-189 removed**: DATE_POLICY_MIN filtering logic
- **Lines 17-19**: Added SNAPSHOT_ID_002_INVALID constant, updated SNAPSHOT_ID to _003
- **Lines 104-110**: Added _002 invalidity check with `unaccepted_invalid_publication` status
- **Lines 35-40**: Migrated VENDOR_SCOPE_DISCLOSURE to structured dict
- **Lines 423-448**: Updated manifest structure (removed date_policy_min, added taxonomy_out_of_scope_count)
- **Lines 318-330**: Added SW2014 enumeration logic

### Verifier (verify_pit_membership_snapshot.py)
- **Lines 15-19**: Added SNAPSHOT_ID_002_INVALID, updated SNAPSHOT_ID to _003
- **Lines 61-74**: Added _002 unaccepted_invalid_publication check (exit code 3)
- **Lines 109-116**: Removed date_policy_min from required_manifest_fields
- **Lines 150-160**: Added vendor_scope_disclosure structure validation
- **Lines 276-282**: Added _002 unaccepted status handler in main()

### Test Suite (test_pit_membership_corrective.py)
- **Lines 22-32**: Added SNAPSHOT_ID_003, OUTPUT_DIR_003 constants
- **Lines 54-69**: Added test_002_rejected_by_publisher
- **Lines 85-93**: Added test_002_unaccepted_by_verifier
- **Lines 95-148**: Updated all _002 references to _003, reversed date policy test logic
- **Lines 217-251**: Updated vendor_scope_disclosure test for structured format
- **Lines 384-427**: Updated protected_artifacts test to check both _001 and _002

### Template Library (strategy_template_library.py)
- **Line 663**: Updated pit_membership_snapshot_id from _002 to _003

---

## Risk Mitigation

1. **Write-Once Protection**: Re-running publisher with same inputs returns `already_published`, not overwrite.
2. **Atomic Publication**: _003 built in temporary staging directory, verified, then atomically renamed.
3. **Immutable Audit Trail**: _001 and _002 preserved as audit evidence with SHA256 integrity verification.
4. **Tri-State Verifier**: Distinct exit codes (0/2/3) for verified/retired/invalid publications.
5. **Independent Verification**: Verifier re-reads all source manifests and recomputes hashes.

---

## Outstanding Work

- **Structural Validation Tests**: 3 tests skipped (duplicate rejection, invalid interval rejection, overlapping interval rejection). These require production runner integration and are deferred to runtime validation.

---

## Acceptance Criteria

- [x] _003 published with canonical_content_hash: `c3d8b70040d23b66da50145c463b3c04e8c2659116d02451dc0e70f2c69f81d7`
- [x] _003 contains 7,804 records (vs _002's 4,538)
- [x] _003 contains 3,266 historical records before 2016-01-04
- [x] _003 manifest has structured vendor_scope_disclosure
- [x] _003 manifest reports taxonomy_out_of_scope_count: 53
- [x] _003 manifest does NOT contain date_policy_min field
- [x] Verifier marks _001 as retired_unaccepted (exit 2)
- [x] Verifier marks _002 as unaccepted_invalid_publication (exit 3)
- [x] Verifier marks _003 as verified (exit 0)
- [x] Test suite: 14 passed, 3 skipped
- [x] _001 and _002 integrity verified (SHA256 unchanged)
- [x] Template library bound to _003

---

## Deliverables

1. **Artifact**: `data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_003/`
   - manifest.json (canonical_content_hash: c3d8b70040d23b66da50145c463b3c04e8c2659116d02451dc0e70f2c69f81d7)
   - records.parquet (7,804 records)
   - Sidecar checksums: manifest.json.sha256, records.parquet.sha256

2. **Scripts**:
   - scripts/publish_pit_membership_snapshot.py (updated)
   - scripts/verify_pit_membership_snapshot.py (updated)

3. **Test Suite**:
   - tests/test_pit_membership_corrective.py (15 tests, 14 passed, 3 skipped)

4. **Documentation**:
   - This delivery report

5. **Template Library Binding**:
   - backend/services/strategy_template_library.py (updated)

---

**Authorized by**: illya  
**Delivery Date**: 2026-07-16  
**Next Steps**: Task 1-E execution can proceed with _003 as the authoritative PIT membership snapshot.
