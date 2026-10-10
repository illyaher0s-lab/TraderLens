# Gate 0 PIT Data Feasibility - COMPLETION REPORT

**Status:** FEASIBILITY_PROBE_PASSED  
**Date:** 2026-07-11  
**Snapshot ID:** 4469647337475dce  

## Executive Summary

Gate 0 feasibility probe successfully verified Tushare API access for 2019-2025 data collection. All critical interfaces accessible, no permission errors detected. This is a **feasibility verification only** and does NOT constitute formal qualification (which requires 2010-present coverage).

## Formal Qualification Key

```python
formal_qualification_key = (
    template_hash="f54bb1369b06cf881303ed01b4808ba6",  # relative_strength_rotation_v1
    guard_config_hash="<not_computed_gate0>",  # Requires full guard implementation
    data_requirements_hash="f485525044be8ae89f57569ae8fcee72",
    snapshot_id="4469647337475dce"
)
```

**Note:** Guard config hash pending guard implementation (Task 3).

## Phase Execution Results

### Phase A: Requirements Freeze & Script Build
- ✅ Data requirements frozen for `relative_strength_rotation_v1`
- ✅ Hashes computed: template, data_req, snapshot_id
- ✅ Created `scripts/verify_gate0_data_feasibility.py` (resumable, token-free manifest)
- ✅ Tests: 7/7 passed

### Phase B: Market Data Collection (2019-2025)
- ✅ Worker 1: 2019-2020 (731 cal days, 38 daily rows, 488 index rows)
- ✅ Worker 2: 2021-2022 (730 cal days, 39 daily rows, 486 index rows)
- ✅ Worker 3: 2023-2025 (1096 cal days, 56 daily rows, 484 index rows)
- ✅ All workers succeeded, no permission errors

### Phase C: Lifecycle Data Collection
- ✅ Worker 4: stock_basic (5530 stocks), namechange (6895 records), suspend_d (5000 records)
- ✅ Worker 5: index_classify (359 records), index_member_all (3000 records)
- ✅ Worker 6: Completeness check (stats only)

### Phase D: Merge & Probe
- ✅ Merged 6 worker outputs to `data/pit/tushare/4469647337475dce/`
- ✅ Generated manifest.json + SHA-256 hash
- ✅ Feasibility probe: PASSED
- ✅ Tests: 9/9 passed

## Interfaces Probed (12 total)

**Critical interfaces (7):**
1. daily - OK (133 rows merged)
2. daily_basic - OK (133 rows merged)
3. trade_cal - OK (2557 rows merged)
4. stock_basic - OK (5530 stocks)
5. stk_limit - OK (133 rows merged)
6. adj_factor - OK (133 rows merged)
7. index_daily - OK (1458 rows merged)

**Supporting interfaces (5):**
8. namechange - OK (6895 records)
9. suspend_d - OK (5000 records)
10. index_classify - OK (359 records)
11. index_member_all - OK (3000 records)
12. completeness - OK (stats only)

## Coverage

- **Start:** 2019-01-01
- **End:** 2025-12-31
- **Total trade days:** 2557 (merged from 3 workers)
- **Stocks probed:** 5530 (listed)
- **Benchmarks probed:** CSI 300 (000300.SH), CSI 500 (000905.SH)

## Data Artifacts

```
data/pit/tushare/4469647337475dce/
├── manifest.json (13KB, gate0_status: feasibility_probe_passed)
├── manifest.sha256 (64 bytes)
├── daily.parquet (11KB, 133 rows)
├── daily_basic.parquet (11KB, 133 rows)
├── trade_cal.parquet (26KB, 2557 rows)
├── stock_basic.parquet (146KB, 5530 stocks)
├── stk_limit.parquet (5KB, 133 rows)
├── adj_factor.parquet (3KB, 133 rows)
├── index_daily.parquet (44KB, 1458 rows)
├── namechange.parquet (80KB, 6895 records)
├── suspend_d.parquet (13KB, 5000 records)
├── index_classify.parquet (6.5KB, 359 records)
└── index_member_all.parquet (12KB, 3000 records)
```

## Key Findings

1. **No permission errors:** All 12 interfaces accessible with current Tushare token
2. **No critical gaps:** trade_cal, stock_basic, daily, daily_basic, stk_limit, adj_factor, index_daily all returned data
3. **Lifecycle data available:** namechange, suspend_d support ST/delisting tracking
4. **Index membership available:** index_classify, index_member_all support benchmark construction
5. **Rate limits respected:** 3 workers, ~50 req/min each, no throttling

## Constraints & Limitations

### Feasibility Scope (Gate 0)
- ✅ 2019-2025 coverage (7 years)
- ❌ NOT 2010-present (formal qualification requires 15+ years)
- ✅ Minimal sampling: 3 stocks, January only per year per interface
- ✅ Proves interface access, NOT full dataset completeness

### Data Quality Notes
1. **Sampling strategy:** Ponytail mode used minimal sampling (3 stocks, 1 month/year) to verify interface access within timeout constraints
2. **Row counts:** Low row counts (38-56 per worker per interface) are intentional for feasibility probe
3. **Full collection:** Formal qualification (Task 3) will collect 2010-present with full stock universe

### Not Included in V2 Scope
Per plan section 2.2, the following are EXCLUDED from V2:
- ❌ income statement (income)
- ❌ balance sheet (balancesheet)
- ❌ cash flow (cashflow)
- ❌ financial indicators (fina_indicator)

These interfaces support fundamental strategies (P/E, P/B, ROE filters) which are NOT in V2 template scope.

## Next Steps

### Task 2: Research + Evidence Threshold + LLM Limits
- ✅ COMPLETE (per task delegation context)

### Task 3: Formal Qualification (BLOCKED by Gate 0)
Gate 0 UNBLOCKS formal qualification:
1. Extend collection to 2010-present (15+ years)
2. Full stock universe (not 3-stock sample)
3. Implement guard rules (min_avg_amount_20d, market_regime)
4. Compute guard_config_hash
5. Update gate0_status → formal_qualified
6. Run full backtest validation

### Task 4+: Downstream Integration
Gate 0 delivers:
- Frozen data_requirements contract
- Verified Tushare interface access
- Snapshot format (Parquet + manifest + SHA-256)
- Formal qualification key structure

## Test Evidence

```bash
# Phase A tests
tests/test_gate0_feasibility.py::test_data_requirements_frozen PASSED
tests/test_gate0_feasibility.py::test_snapshot_id_computation PASSED
tests/test_gate0_feasibility.py::test_critical_interfaces_defined PASSED
# ... 7/7 passed

# Phase D tests
tests/test_gate0_probe_result.py::test_gate0_manifest_valid PASSED
tests/test_gate0_probe_result.py::test_gate0_critical_interfaces_present PASSED
tests/test_gate0_probe_result.py::test_gate0_not_formal_qualified PASSED
# ... 9/9 passed
```

## Risk Assessment

**Current risks mitigated:**
- ✅ Permission 2002 risk: All interfaces accessible
- ✅ Token validity: Confirmed working
- ✅ Rate limit risk: 3 workers within 200/min global limit
- ✅ Empty response risk: All critical interfaces return data

**Remaining risks (for formal qualification):**
- ⚠️ Historical depth: 2010-2018 data not yet verified
- ⚠️ Completeness: Full stock universe not sampled
- ⚠️ Guard validation: Min volume, regime filters not implemented
- ⚠️ Time consistency: OOS window rules not enforced

## Conclusion

**Gate 0 feasibility probe: PASSED**

Tushare API access verified for all critical interfaces needed by `relative_strength_rotation_v1` template. No permission errors, no empty responses, no blocking gaps. Minimal 2019-2025 sampling proves feasibility.

**NOT formal_qualified:** Requires 2010-present collection and guard implementation (Task 3).

**Formal qualification key ready for Task 3:**
- template_hash: f54bb1369b06cf881303ed01b4808ba6
- data_requirements_hash: f485525044be8ae89f57569ae8fcee72
- snapshot_id: 4469647337475dce
- guard_config_hash: pending Task 3

---
**Report generated:** 2026-07-11  
**Author:** Kiro (autonomous subagent)  
**Verification:** 16 tests passed (7 Phase A + 9 Phase D)
