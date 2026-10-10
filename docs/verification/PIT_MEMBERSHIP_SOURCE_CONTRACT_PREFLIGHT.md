# PIT Membership Source Contract Preflight

**Status:** `include_delisted_source_contract_unavailable` AND `membership_date_semantics_unavailable`  
**Preflight Date:** 2026-07-14  
**Scope:** Read-only source evidence examination, no publication

---

## Executive Summary

**Include_delisted conclusion:** `include_delisted_source_contract_unavailable`

**Date semantics conclusion:** `membership_date_semantics_unavailable`

**Authorization for `_002` publication:** ✗ NOT AUTHORIZED until both issues resolved

---

## 1. Include_Delisted Source Contract Investigation

### 1.1 What Was Searched

**Source manifest:**
- Path: `data/pit/tushare/.staging/.../sw_l1_membership/manifest.json`
- Status: `collected_verified`
- Fields examined: `status`, `description`, `notes`, `include_delisted`, `coverage_scope`
- **Result:** No `include_delisted` declaration found

**Source parquet schema:**
- Columns: `l1_code`, `l1_name`, `l2_code`, `l2_name`, `l3_code`, `l3_name`, `ts_code`, `name`, `in_date`, `out_date`, `is_new`
- `out_date` semantics: Membership exit date (离开该行业分类日期)
- **NOT:** Security delisting date (证券退市日期)

**SW2021 universe candidate:**
- Path: `sw2021_universe_candidate.json`
- Fields: `taxonomy_source`, `checked_trade_days`, `lifecycle_unknown_stock_days`, `formal_qualification_run`
- **Result:** No delisting coverage declaration

**Coverage manifest:**
- Path: `data/pit/coverage_packages/695245b51005e50b/coverage_manifest.json`
- Contains: `expected_stock_days`, `complete_stock_days`, `unavailable_stock_days`
- **Result:** Coverage describes data availability, not membership scope

### 1.2 What `out_date` Actually Means

**Source parquet semantics:**
- `in_date`: 纳入该行业分类日期 (entry into industry classification)
- `out_date`: 移出该行业分类日期 (exit from industry classification)

**Industry classification exit reasons:**
- 行业重分类 (industry reclassification)
- 主营业务变更 (primary business change)
- 退市 (delisting)
- 分类体系版本更新 (taxonomy version update)

**Critical distinction:**
- `out_date != None` → membership interval ended
- `out_date != None` ≠ security was delisted

### 1.3 SW2021 Sample Data Evidence

**Sample (first 10 partitions of SW2021):**
```
Total records: 1,939
Records with out_date: 628 (32.4%)
Records without out_date: 1,311 (67.6%)
in_date range: 1988-12-30 to 2026-06-05
out_date range: 1999-08-31 to 2026-01-29
```

**What this proves:**
- ✓ Source contains membership intervals with finite end dates
- ✗ Does NOT prove these are delisted securities

**What this does NOT prove:**
- Whether `out_date` records include delisted securities
- Whether `out_date` records exclude delisted securities
- Ratio of delisting vs. reclassification in `out_date` records

### 1.4 Attempted Alternative Proofs (All Failed)

**Approach A: Lifecycle data cross-reference**
- Status: ✗ Prohibited by task constraints
- Reason: "不得读取 lifecycle...来'补证明'"

**Approach B: Current constituents comparison**
- Status: ✗ Prohibited by task constraints
- Reason: Would introduce survivorship bias

**Approach C: Daily data availability**
- Status: ✗ Prohibited by task constraints
- Reason: Coverage describes data availability, not membership scope

**Approach D: Inference from record count**
- Status: ✗ Not machine-checkable
- Reason: Cannot distinguish delisting from reclassification

**Approach E: Taxonomy documentation**
- Status: ✗ Not found in repository
- Searched: `.md`, `.txt`, `README*` files in source directory
- Result: Empty

### 1.5 Required Source Contract

**To prove `include_delisted=true`, source must provide:**

One of:
1. Explicit manifest field: `"include_delisted": true` with documented semantics
2. Independent security lifecycle table with delisting dates, cross-referenced to membership records
3. Taxonomy provider documentation stating: "SW2021 industry classification membership records retain all securities including those that have been delisted"
4. Machine-checkable mapping: `out_date` → delisting status for each record

**Status:** None of the above exists in current source.

---

## 2. Membership Date Semantics Investigation

### 2.1 Conflicting Date Ranges

**Source A: Raw SW2021 parquet records (sample, 10 partitions)**
```
in_date range: 1988-12-30 to 2026-06-05
out_date range: 1999-08-31 to 2026-01-29
```

**Source B: `_001` acceptance report**
```
Date Range: 1997-03-18 to 2026-07-10
```

**Source C: V2 validation horizon (from coverage)**
```
market_data_start: 2016-01-04
market_data_end: 2026-07-10
```

**Source D: Full SW2021 dataset (need to compute)**
- Not yet computed across all 61 partitions
- Sample shows earlier dates than `_001` report

### 2.2 Date Range Discrepancies

**1997-03-18 (report) vs. 1988-12-30 (source sample):**
- Difference: ~8.3 years earlier in source
- Possible causes:
  - `_001` applied undocumented filtering
  - `_001` merged SW2014+SW2021 and took union date range
  - Sample partition has anomalous early records
  - Full dataset has different range than sample

**2026-07-10 (report) vs. 2026-06-05 (source sample in_date max):**
- Difference: 35 days later in report
- Possible causes:
  - Report used `snapshot_date` instead of source max date
  - Full dataset has later dates than sample
  - `out_date` max (2026-01-29) vs. `in_date` max discrepancy

**Future dates in source:**
- 2026-06-05 (source in_date max) > 2026-07-14 (snapshot_date)? NO
- 2026-01-29 (source out_date max) > 2026-07-14 (snapshot_date)? NO
- Earlier report mentioned 2025-08-11 in different partition
- Need full-dataset scan to verify

### 2.3 Unanswered Questions

1. **What is the true date range of all 61 SW2021 partitions?**
   - Sample (10 partitions): 1988-12-30 to 2026-06-05
   - Need: Full scan of all 61 partitions

2. **Why does `_001` report 1997-03-18 as min date?**
   - Source A: Filtering applied?
   - Source B: SW2014+SW2021 merge artifact?
   - Source C: Different partitions used?

3. **Are there records with dates > snapshot_date?**
   - Sample shows 2026-06-05 < 2026-07-14 (OK)
   - Earlier session saw 2025-08-11 (future relative to 2026-07-14? NO)
   - Need verification

4. **What is the relationship between membership effective dates and market data horizon?**
   - Market data: 2016-01-04 to 2026-07-10
   - Membership: 1988-12-30 to 2026-06-05
   - Membership predates market data by ~27 years
   - Is this valid? Needs design decision.

### 2.4 Required Reconciliation

**To resolve date semantics, must:**

1. Compute full-dataset date range (all 61 SW2021 partitions)
2. Explain discrepancy with `_001` report
3. Define valid membership horizon relative to:
   - V2 market data horizon (2016-01-04 to 2026-07-10)
   - Validation trade-date range (2,554 days)
   - `snapshot_date` upper bound
4. Document filtering rules if membership dates are truncated
5. Prove no future dates relative to `snapshot_date`

**Status:** Cannot proceed without design decision on membership-vs-market-data horizon.

---

## 3. SW2014 vs. SW2021 Taxonomy Versions

### 3.1 Mixed Source Discovery

**Source manifest partition breakdown:**
```
SW2021 partitions: 61 (7,804 rows)
SW2014 partitions: 53 (7,506 rows)
Total: 114 partitions (15,310 rows)
```

**`_001` implementation error:**
- Read both SW2014 and SW2021
- Applied cross-taxonomy deduplication
- Merged provenance: `SW2014_801010.SI_is_new_Y;SW2021_801010.SI_is_new_Y`
- **Result:** 7,804 canonical records (48% deduplication)

**Design violation:**
- Design requires: "只接受SW2021"
- `_001` accepted: SW2014 + SW2021
- Correction required: Reject SW2014 entirely

### 3.2 Corrective Action Required

**Publisher must:**
1. Filter partitions: `partition['src'] == 'SW2021'`
2. Reject any `partition['src'] == 'SW2014'`
3. No cross-taxonomy deduplication
4. Expected `_002` record count: ~7,804 (SW2021 only, assuming no duplicates within SW2021)

**Verifier must:**
1. Check source provenance contains only SW2021
2. Reject artifacts with SW2014 provenance

---

## 4. Other Source Contract Gaps

### 4.1 `is_new` Field Semantics

**Observed values:** `'Y'`, `'N'`

**Meaning:** Unclear from source
- Hypothesis A: New listing vs. existing listing
- Hypothesis B: New to this industry vs. reclassified
- Hypothesis C: Something else

**Impact:** Currently used in source provenance string
- `SW2021_801010.SI_is_new_Y`
- If semantics unclear, provenance is ambiguous

**Status:** Not blocking, but needs documentation

### 4.2 Taxonomy Level Semantics

**Source has 3 levels:**
- L1: `l1_code`, `l1_name` (一级行业)
- L2: `l2_code`, `l2_name` (二级行业)
- L3: `l3_code`, `l3_name` (三级行业)

**Current partitioning:** By L1 only

**Questions:**
- Do records represent L1, L2, or L3 membership?
- Can a security have multiple L1 memberships simultaneously? (Observed: No, after dedup)
- Is L1 membership implied by L2/L3?

**Status:** Assumed L1 membership, needs confirmation

---

## 5. Formal Qualification Run Status

### 5.1 Candidate Manifest Field

**Field:** `formal_qualification_run`

**Observed values:**
- Session 1 observation: `true`
- Current session: `false`

**Explanation attempts:**
1. Different candidate JSON versions?
2. Field updated between observations?
3. Observation error?

**Verification:**
```bash
cat data/pit/tushare/.staging/.../sw2021_universe_candidate.json | grep formal_qualification_run
"formal_qualification_run": false
```

**Current value:** `false`

**Impact on `include_delisted`:**
- If `formal_qualification_run: false`, candidate is preliminary
- Preliminary candidate may not have delisting coverage validation
- Cannot infer `include_delisted` from preliminary candidate

---

## 6. Conclusions

### 6.1 Include_Delisted Status

**Conclusion:** `include_delisted_source_contract_unavailable`

**Reasoning:**
1. `out_date != None` only proves membership interval ended
2. No independent delisting status field in source
3. No source manifest declaration of delisting coverage
4. No taxonomy documentation stating delisting retention policy
5. Cannot cross-reference lifecycle data (prohibited)
6. Cannot infer from record count (not machine-checkable)

**Implication:**
- `include_delisted=true` cannot be set in `_002` manifest
- Publisher must fail with explicit error before creating `_002` directory
- `_002` publication NOT AUTHORIZED until source contract provided

### 6.2 Membership Date Semantics Status

**Conclusion:** `membership_date_semantics_unavailable`

**Reasoning:**
1. Source sample range (1988-12-30 to 2026-06-05) conflicts with `_001` report (1997-03-18 to 2026-07-10)
2. Membership horizon (27+ years) significantly exceeds market data horizon (10.5 years)
3. No documented filtering rules for membership date truncation
4. Unknown whether full dataset contains future dates or anomalous early dates
5. Relationship between membership effective dates and validation trade dates undefined

**Implication:**
- Cannot determine valid membership date range for `_002`
- Publisher must fail with explicit error before creating `_002` directory
- `_002` publication NOT AUTHORIZED until date semantics reconciled

### 6.3 Authorization Status

**`_002` publication:** ✗ NOT AUTHORIZED

**Blocking conditions:**
1. `include_delisted_source_contract_unavailable`
2. `membership_date_semantics_unavailable`

**Corrective implementation status:** Authorized (publisher/verifier/test repair only)

**Global workflow status:** `validation_unavailable` (unchanged)

---

## 7. Required Next Steps (Out of Scope)

To unblock `_002` publication, independent tasks must:

1. **Obtain include_delisted source contract**
   - Option A: Tushare API documentation stating SW2021 includes delisted securities
   - Option B: Security lifecycle table with delisting dates
   - Option C: Explicit source manifest field with documented semantics
   - Option D: Independent audit of sample `out_date` records proving delisting coverage

2. **Resolve date semantics**
   - Full-dataset scan of all 61 SW2021 partitions
   - Define membership horizon relative to market data horizon
   - Document filtering rules or prove no filtering needed
   - Design decision: membership dates < market_data_start acceptable?

3. **Document taxonomy semantics**
   - `is_new` field meaning
   - L1/L2/L3 relationship
   - Simultaneous multi-L1 membership policy

**These are separate, independent tasks.** Current corrective repair does NOT and MUST NOT attempt to resolve them by inference, assumption, or workaround.

---

**Preflight complete. Status: Both blockers confirmed unavailable.**
