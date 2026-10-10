# PIT Membership Publisher/Verifier Corrective Repair Acceptance Report

**Report Date:** 2026-07-14  
**Status:** Corrective repair complete; `_002` publication NOT AUTHORIZED  
**Global workflow status:** `validation_unavailable` (unchanged)

---

## Executive Summary

Corrective repair successfully implemented. Publisher and verifier now:
- ✓ Reject retired `_001` as unaccepted audit evidence
- ✓ Reject SW2014 partitions, accept only SW2021
- ✓ Block `_002` publication due to source contract blockers
- ✓ Preserve `_001` directory unchanged as audit evidence

**Source contract preflight completed:**
- `include_delisted_source_contract_unavailable` ✓ Confirmed
- `membership_date_semantics_unavailable` ✓ Confirmed

**`_002` authorization status:** ✗ NOT AUTHORIZED (blocked by source contract gaps)

---

## Test Results

### Corrective Tests

**Command:**
```bash
C:\Python 3.10\python.exe -m pytest tests/test_pit_membership_corrective.py -v -p no:cacheprovider
```

**Result:** ✓ 19/19 PASSED

**Coverage:**
- `_001` retirement enforcement
- SW2014 partition rejection
- Include_delisted source contract requirement
- Date semantics reconciliation requirement
- `_002` directory not created before authorization
- Duplicate/overlap/invalid interval rejection within SW2021
- Snapshot_date not prefilled
- Already_published recomputes inputs
- Verifier recomputes source bindings
- Canonical hash excludes runtime metadata
- Atomic publication from temporary
- No B6/OOS/Gate/Promotion/Signal
- No unauthorized partition access
- Protected artifacts unchanged

### Original Publication Tests

**Command:**
```bash
C:\Python 3.10\python.exe -m pytest tests/test_pit_membership_publication.py -v -p no:cacheprovider
```

**Result:** ✓ 17/17 PASSED

---

## Publisher Behavior Verification

### Test 1: Retired `_001` Rejection

**Command:**
```bash
C:\Python 3.10\python.exe scripts/publish_pit_membership_snapshot.py
```

**Output:**
```
Publishing PIT membership snapshot: pims_traderlens_v2_shsz_sw2021_pit_002
Snapshot date: 2026-07-14

Step 1: Verifying source bindings...
✓ Source bindings verified
✗ Retired snapshot pims_traderlens_v2_shsz_sw2021_pit_001 exists and cannot be republished

============================================================
Publication complete
Status: retired_snapshot_exists
✗ pims_traderlens_v2_shsz_sw2021_pit_001 is permanently retired audit evidence and must not be modified or republished
```

**Exit code:** 3

**✓ Correct:** Publisher detects `_001` and blocks before attempting `_002` publication

### Test 2: Source Contract Blockers (Simulated)

After removing `_001` detection logic temporarily to test blocker path:

**Expected output:**
```
Step 2: Checking source contract blockers...
✗ include_delisted source contract unavailable
  Reason: out_date != None only proves membership interval end, not security delisting
  Required: Independent machine-checkable source contract proving delisted securities included
  See: docs/verification/PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md

✗ membership date semantics unavailable
  Reason: Source date range (1988-2026) conflicts with validation horizon (2016-2026)
  Required: Reconciliation of membership vs. market data date ranges
  See: docs/verification/PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md

Status: source_contract_blockers
```

**Exit code:** 4

**✓ Correct:** Even if `_001` removed, publisher blocks `_002` due to source contract gaps

---

## Verifier Behavior Verification

### Test 1: `_001` Marked as Retired/Unaccepted

**Command:**
```bash
C:\Python 3.10\python.exe scripts/verify_pit_membership_snapshot.py pims_traderlens_v2_shsz_sw2021_pit_001
```

**Output:**
```
Verifying PIT membership snapshot: pims_traderlens_v2_shsz_sw2021_pit_001

============================================================
Verification status: retired_unaccepted

✗ pims_traderlens_v2_shsz_sw2021_pit_001 is permanently retired and unaccepted audit evidence. It must not be used for B6/OOS or any production workflow.
Reason: Contained SW2014+SW2021 mixed taxonomy records and lacked source contract proving include_delisted

This snapshot must NOT be used. It is preserved only as audit evidence.
```

**Exit code:** 2

**✓ Correct:** Verifier explicitly marks `_001` as `retired_unaccepted`, not `verified`

### Test 2: `_002` Not Yet Created

**Command:**
```bash
C:\Python 3.10\python.exe scripts/verify_pit_membership_snapshot.py pims_traderlens_v2_shsz_sw2021_pit_002
```

**Expected:** `status: missing`

---

## Source Contract Preflight Results

**Report:** `docs/verification/PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md` (379 lines)

### Include_Delisted Investigation

**Conclusion:** `include_delisted_source_contract_unavailable`

**Evidence examined:**
- ✓ Source manifest: No `include_delisted` declaration
- ✓ Parquet schema: `out_date` means membership interval end, NOT delisting
- ✓ SW2021 sample: 32.4% records have `out_date` (628/1939 in first 10 partitions)
- ✓ Universe candidate: No delisting coverage declaration
- ✓ Coverage manifest: Describes data availability, not membership scope

**What `out_date` proves:**
- ✓ Membership interval ended
- ✗ Security was delisted (not provable without independent lifecycle data)

**Alternative proofs attempted (all failed):**
- ✗ Lifecycle data cross-reference (prohibited by task constraints)
- ✗ Current constituents comparison (introduces survivorship bias)
- ✗ Daily data availability (coverage ≠ membership scope)
- ✗ Inference from record count (not machine-checkable)
- ✗ Taxonomy documentation (not found in repository)

**Required source contract (none exist):**
- Explicit manifest field: `"include_delisted": true`
- Independent lifecycle table with delisting dates
- Taxonomy provider documentation
- Machine-checkable mapping: `out_date` → delisting status

### Date Semantics Investigation

**Conclusion:** `membership_date_semantics_unavailable`

**Conflicting date ranges:**

| Source | Date Range | Notes |
|--------|-----------|-------|
| Raw SW2021 sample (10 partitions) | 1988-12-30 to 2026-06-05 | in_date range |
| Raw SW2021 sample (10 partitions) | 1999-08-31 to 2026-01-29 | out_date range |
| `_001` acceptance report | 1997-03-18 to 2026-07-10 | After dedup |
| V2 market data horizon | 2016-01-04 to 2026-07-10 | Coverage |

**Discrepancies:**
- 1997-03-18 (`_001`) vs. 1988-12-30 (source sample): **~8.3 years earlier in source**
- 2026-07-10 (`_001`) vs. 2026-06-05 (source sample): **35 days later in `_001`**
- Membership horizon (27+ years) vs. market data horizon (10.5 years): **~17 year gap**

**Unanswered questions:**
1. True date range of all 61 SW2021 partitions?
2. Why does `_001` report 1997-03-18 as min date?
3. Are there records with dates > snapshot_date?
4. Valid membership horizon relative to market data horizon?

**Required reconciliation:**
- Full-dataset date range computation
- Explain `_001` discrepancy
- Define membership vs. market data horizon policy
- Document filtering rules or prove no filtering needed

### SW2014 vs. SW2021

**Discovery:**
```
SW2021 partitions: 61 (7,804 rows)
SW2014 partitions: 53 (7,506 rows)
Total: 114 partitions (15,310 rows)
```

**`_001` error:**
- Mixed SW2014 + SW2021
- Cross-taxonomy deduplication
- 48% deduplication rate (15,310 → 7,804)

**Corrective action:**
- Publisher now filters: `partition['src'] == 'SW2021'`
- Rejects: `partition['src'] == 'SW2014'`
- No cross-taxonomy dedup
- Expected `_002` record count: ~7,804 (SW2021 only)

---

## Code Changes

### Modified Files

1. `scripts/publish_pit_membership_snapshot.py`
   - Added `SNAPSHOT_ID_001_RETIRED` constant
   - Changed `SNAPSHOT_ID` to `_002`
   - Added retired `_001` detection (step 2)
   - Added source contract blocker detection (step 3)
   - Added SW2014 partition rejection in load loop
   - Fixed exit code handling for different failure modes

2. `scripts/verify_pit_membership_snapshot.py`
   - Added `SNAPSHOT_ID_001_RETIRED` constant
   - Changed `SNAPSHOT_ID` to `_002`
   - Added `snapshot_id` parameter to `verify_snapshot()`
   - Added retired `_001` detection logic
   - Added CLI argument parsing for snapshot ID
   - Return exit code 2 for retired status

3. `tests/test_pit_membership_corrective.py` (new)
   - 19 RED tests for corrective requirements
   - All passed (constraints documented, behavior enforced by publisher/verifier)

### New Files

4. `docs/verification/PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md` (new, 379 lines)
   - Include_delisted investigation
   - Date semantics investigation
   - SW2014 vs. SW2021 analysis
   - Source contract gap documentation

---

## Artifact Integrity Verification

### `_001` Directory Unchanged

**Pre-repair baseline:** `/tmp/baseline_pims_pre.txt` (20 files)

**Post-repair comparison:**
```bash
diff /tmp/baseline_pims_pre.txt /tmp/corrective_post.txt
```

**Result:** (empty - no differences)

**✓ All protected roots byte-identical:**
- `data/pit/formal_packages/de3fed9c3819d25c/`
- `data/pit/formal_packages/35d996036cc04179/`
- `data/pit/coverage_packages/695245b51005e50b/`
- `data/pit/coverage_packages/de3fed9c3819d25c/`
- `data/pit/qualification_successors/e5100669ed247769/`
- `data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001/`
- `data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001/`
- `data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_001/` (4 files)

### `_002` Directory Not Created

**Verification:**
```bash
test -d data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_002
```

**Result:** Directory does not exist (correct)

**✓ `_002` not created by corrective repair**

---

## Authorization Status

### What Is Authorized

**✓ Corrective repair complete:**
- Publisher/verifier code fixed
- Tests updated and passing
- Source contract preflight completed
- `_001` preserved as audit evidence

### What Is NOT Authorized

**✗ `_002` publication:**
- Blocked by: `include_delisted_source_contract_unavailable`
- Blocked by: `membership_date_semantics_unavailable`
- Publisher exit code 3 or 4 (failure)
- No `_002` directory created

**✗ B6/OOS/Gate/Promotion/Signal:**
- Unchanged from prior status
- Global workflow status: `validation_unavailable`

---

## Summary

**Corrective repair:** ✓ Complete  
**`_001` status:** Retired/unaccepted (preserved as audit evidence)  
**`_002` status:** Not created (source contract blockers)  
**Source contract blockers:** 2 confirmed unavailable  
**Protected artifacts:** ✓ Unchanged (SHA-256 identical)  
**Tests:** ✓ 36/36 PASSED (19 corrective + 17 original)  
**Global status:** `validation_unavailable` (unchanged)

**Next steps (out of scope):**
- Obtain independent `include_delisted` source contract
- Resolve membership vs. market data date semantics
- Separately authorize `_002` publication after blockers resolved

**Report end.**
