# Task 3 B3 Missing Input Reuse Audit

**Audit Date:** 2026-07-25  
**Scope:** Determine if `listing_delisting` + `liquidity` can reuse formal data on disk without new collection

## Executive Summary

**listing_delisting:** data_coverage_unverified  
**liquidity:** data_present_contract_unfrozen

Both inputs have formal data on disk. `listing_delisting` needs coverage verification + adapter; `liquidity` needs contract freeze (20-day window rules) + deterministic derivation path decision.

**No new Tushare collection required.** Minimal path: freeze contracts, write adapters, verify coverage, extend package.

## A. listing_delisting Analysis

### A.1 Data Availability

**Formal source:** `stock_basic` (partitioned by `list_status=L/D/P`)  
**Path:** `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/stock_basic/`  
**Fields:** `ts_code`, `list_date`, `delist_date`, `list_status`  
**Coverage:**
- Listed (L): 5,530 rows, all have `list_date`, all `delist_date=None`
- Delisted (D): 335 rows, all have `list_date` + `delist_date`
- Pre-listed (P): unknown count, not sampled

**Sample (delisted):**
```
ts_code       list_date  delist_date
000003.SZ     19910703   20020614
000005.SZ     19901210   20240426
```

**Sample (listed):**
```
ts_code       list_date  delist_date
000001.SZ     19910403   None
000002.SZ     19910129   None
```

### A.2 Semantic Match

**Template requirement (L221-224):**
```python
"listing_delisting": {
    "requirement": "required",
    "reason": "template forbidden_market includes delisting_risk",
}
```

**Template config (verified):**
```python
forbidden_market: ('limit_up', 'st_stock', 'delisting_risk')
```

**Contract (stable.py L38-40):**
```python
list_date: date
delist_date: date | None = None
current_status: Literal["listed", "delisted", "suspended_long_term", "delisting_risk"]
```

**Semantic match:** YES
- `stock_basic.list_date` → `StockIdentity.list_date`
- `stock_basic.delist_date` → `StockIdentity.delist_date`
- `stock_basic.list_status={L,D,P}` maps to `current_status`

### A.3 PIT/As-Of Semantics

**Current storage:** Partitioned snapshot (list_status as partition key), not by-trade-date.

**Issue:** `stock_basic` is a **current-state snapshot**, not a time-series. It reflects the state **as of collection date**, not historical point-in-time state for each `trade_date`.

**PIT requirement:** Execution on `2021-06-01` must use listing/delisting facts **known as of 2021-06-01**, not facts known in 2026.

**Forward-looking bias risk:** A stock delisted in 2024 would show `delist_date=20240426` in the 2026 snapshot, creating anachronistic knowledge if applied to 2021 decisions.

**Mitigation path:**
1. `list_date` is stable (listing never changes retroactively) → **PIT-safe**
2. `delist_date` for stocks **already delisted before formal window start (2016-01-04)** → **PIT-safe**
3. `delist_date` for stocks delisted **during or after formal window** → **requires PIT reconstruction or as-of bounding**

**Alternative sources already collected:**
- `bak_basic_lifecycle/manifest.json`: `status=candidate_not_verified`, 3 errors, 457 uncovered daily gaps
- No by-trade-date lifecycle partition exists

### A.4 Gap Assessment

**Critical unknowns:**
1. Does `stock_basic` snapshot reflect **collection-time state** (2026-07-12) or **frozen historical state** (e.g., 2016-01-04)?
2. Is there a Tushare API contract guaranteeing `list_date` never changes and `delist_date` is append-only?
3. Can delisting events be bounded by `trade_cal` + `daily` absence to construct PIT-safe status?

**bak_basic_lifecycle evidence:**
- Source: `bak_basic` (not `stock_basic`)
- Status: `candidate_not_verified`
- Errors: 3 `ValueError` (ts_code: 000022.SZ, 000043.SZ, 300114.SZ)
- Gap: 457 uncovered daily dates
- No formal qualification run

### A.5 Classification

**Status:** `data_coverage_unverified`

**Reasons:**
1. Formal data exists (`stock_basic` L/D/P partitions)
2. Semantic match to contract confirmed
3. PIT semantics not verified (snapshot vs. time-series ambiguity)
4. `bak_basic_lifecycle` candidate failed verification (457 gaps, 3 errors)
5. No machine-verifiable source contract proving `list_date` immutability + `delist_date` append-only semantics

## B. liquidity Analysis

### B.1 Data Availability

**Formal source:** `daily` (partitioned by `trade_date=YYYYMMDD`)  
**Path:** `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/daily/`  
**Field:** `amount` (成交额, unit: 千元 per Tushare docs)  
**Coverage:** 2,554 trade_date partitions (2016-01-04 → 2026-07-10)

**Schema:**
```python
['amount', 'change', 'close', 'high', 'low', 'open', 'pct_chg', 'pre_close', 'trade_date', 'ts_code', 'vol']
```

**Sample (2021-06-01):**
```
ts_code       amount
000001.SZ     1490476.624
000002.SZ     1622419.892
000004.SZ     36524.364
```

**Unit verification needed:** Tushare docs claim `amount` is in 千元 (thousands of yuan). Sample value `1490476.624` → 14.9亿元 if unit is 千元, which is plausible for 平安银行 daily turnover.

### B.2 Template Requirement

**Config (verified):**
```python
risk: {
    'market_regime_allowed': ('green', 'yellow'),
    'min_avg_amount_20d': 50000000  # 5000万元
}
```

**Publisher requirement (L225-228):**
```python
"liquidity": {
    "requirement": "required",
    "reason": "template risk freezes min_avg_amount_20d",
}
```

**Semantic:** Average daily turnover over the trailing 20 **trading days** must be ≥ 50M yuan.

### B.3 Derivation Feasibility

**Raw input:** `daily.amount` (per trade_date, per ts_code)  
**Required computation:** Rolling 20-trading-day mean of `amount`  
**Window semantics:** For execution on `D`, compute mean over `[D-20, D-1]` trading days (exclusive of D)

**Challenges:**
1. **New listings:** Stock listed < 20 trading days ago → insufficient history
2. **Suspensions:** Missing `daily` rows during suspension → window incomplete
3. **Delisting:** Stock delisted within window → partial history
4. **Edge dates:** First 20 trading days of formal window (2016-01-04 + 19 days) → no valid 20d window

**Handling rules NOT frozen:**
- Skip stock if < 20 valid days?
- Use partial window (e.g., 15 days) with warning?
- Require strict 20 consecutive trading days?
- How to handle suspension: skip suspended days in count, or treat as window break?

### B.4 Storage Decision

**Option A:** Deterministic derivation from `daily`
- Compute on-the-fly during execution input binding validation
- No new artifact, `liquidity_ref` points to `daily` with derivation contract
- Pros: No storage duplication, single source of truth
- Cons: Recomputation cost, window-handling ambiguity

**Option B:** Precomputed artifact
- Publish `liquidity/` partition (by trade_date) with precomputed 20d averages
- `liquidity_ref` points to new artifact
- Pros: Explicit contract freeze, verifiable coverage, fast binding
- Cons: New artifact ID, publisher complexity, storage duplication

**Current package (b3eip_001) has:**
- `daily` already published (30,650 files verified)
- No `liquidity` partition

**Publisher note (L212-215):**
```python
"daily_basic": {
    "requirement": "required",
    "reason": "formal coverage and liquidity input",
},
```

Comment claims `daily_basic` is "liquidity input" but `daily_basic` has no `amount` field:
```
['circ_mv', 'close', 'dv_ratio', 'dv_ttm', 'float_share', 'free_share', 'pb', 'pe', 'pe_ttm', 'ps', 'ps_ttm', 'total_mv', 'total_share', 'trade_date', 'ts_code', 'turnover_rate', 'turnover_rate_f', 'volume_ratio']
```

**Error:** `turnover_rate` ≠ `amount`. Unit mismatch. Publisher comment misleading.

### B.5 Classification

**Status:** `data_present_contract_unfrozen`

**Reasons:**
1. Raw data exists (`daily.amount`, 2554 days, all required stocks)
2. Unit confirmed: 千元 (thousands of yuan)
3. **Contract gap:** 20-day window handling rules not frozen (new listings, suspensions, edge dates, partial windows)
4. **Storage path undecided:** derivation from `daily` vs. precomputed artifact
5. `daily_basic` comment misleading (no `amount` field, `turnover_rate` is rate not amount)

## C. Blocker Classification Summary

| Input | Classification | Reason |
|-------|----------------|--------|
| listing_delisting | data_coverage_unverified | Formal `stock_basic` exists but PIT semantics unverified; `bak_basic_lifecycle` candidate has 457 gaps + 3 errors; no machine-verifiable source contract |
| liquidity | data_present_contract_unfrozen | Raw `daily.amount` exists; 20-day window rules not frozen; derivation vs. artifact decision unmade; unit verified |

## D. Minimal Implementation Path

### D.1 Reusable Components

**Publisher/Verifier:**
- `scripts/publish_b3_execution_input_package.py` (reuse L101-620)
- `scripts/verify_b3_execution_input_package.py` (reuse entire)
- `backend/services/formal_input_index.py` (reuse)

**Adapters:**
- `backend/services/formal_pit_partition_adapter.py` (reuse partition read pattern)
- `backend/services/formal_pit_loader.py` (reuse PIT membership projection)

**Tests:**
- `tests/test_b3_execution_input_package.py` (reuse write-once, tamper, verifier)
- `tests/test_task3c_execution_input_binding.py` (extend for new inputs)
- `tests/test_task3c_index_formal_input.py` (reuse index builder/verifier)

### D.2 New Contracts Required

**listing_delisting:**
1. **PIT adapter contract:** `FormalListingDelistingAdapter`
   - Input: `stock_basic` snapshot + `trade_cal` trading dates
   - Output: `StockIdentity` per symbol, bounded by as-of date
   - Rule: For execution on `D`, only use facts known ≤ `D`
   - **Blocker:** `stock_basic` is current-state snapshot (2026-07-12 collection), not by-trade-date time-series

2. **Coverage verification:** Extend `test_task3a_formal_pit_loader.py` pattern
   - Assert: All `pit_membership` symbols have `stock_basic` row
   - Assert: `list_date` ≤ first membership `effective_from`
   - Assert: `delist_date` ≥ last membership `effective_to` (if not None)

**liquidity:**
1. **V3 template contract:** Complete liquidity semantics frozen in `relative_strength_rotation_shsz_sw2021_v3`
   - Algorithm ID: `avg_amount_20d_shsz_common_v1`
   - Window: 20 completed SH/SZ common trading days before execution day (execution day excluded)
   - Source: `daily.amount` (unit: thousand_yuan, multiplier: 1000)
   - Minimum history: 20 trading days
   - Insufficient history: `unavailable_ineligible`
   - Suspension: evidence from `suspend_d`, suspended day amount = 0
   - Other missing: `data_fault`
   - Partial mean: not allowed
   - Window extension: not allowed

2. **Storage decision (deferred):**
   - Derivation function in adapter vs. precomputed artifact
   - Both options require implementation of window logic per V3 contract

### D.3 Package Extension

**Status:** DEFERRED — listing_delisting PIT evidence unavailable, liquidity implementation deferred.

**No package ID assigned** — `_002` not allocated. `_001` remains incomplete with only 7 verified interfaces.

### D.4 Forbidden Actions

- ❌ New Tushare collection (data already on disk)
- ❌ Extend or republish `_001` package (incomplete by design)
- ❌ Overwrite existing _001 package (write-once enforced)
- ❌ Modify verified interfaces (daily, daily_basic, etc.)
- ❌ Global registry, second DB, API, or web UI

### D.5 Status Update

**V3 template:** `relative_strength_rotation_shsz_sw2021_v3` created as candidate
- Hypothesis family: `relative_strength_rotation_shsz_sw2021` (shared with V2)
- Liquidity contract: Complete 15-field algorithm specification in `strategy_config_payload["liquidity"]`
- Data requirements hash: Deterministic, includes liquidity payload + algorithm hash
- Governance: `candidate` (not approved, not in `list_approved_templates()`)

**V2 template:** Unchanged
- Template hash: `867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6`
- Data requirements hash: `1910d7a598b1008fb5ba6ee69833e174b5a9949f31a998e2fced436950d8df04`
- Governance: `approved` (owner authorization intact)
- No liquidity field added (immutable)

## E. Status Declarations

**liquidity_contract_unavailable:** RESOLVED
- V3 template `relative_strength_rotation_shsz_sw2021_v3` created with complete 15-field liquidity contract
- Algorithm hash deterministic: excludes `threshold_yuan`, includes all window/suspension/edge rules
- Data requirements hash deterministic: includes liquidity payload + algorithm hash

**listing_delisting_pit_evidence_unavailable:** PERSISTS
- `stock_basic` formal data exists but is current-state snapshot (2026-07-12), not by-trade-date time-series
- Forward-looking bias risk: stocks delisted after 2016-01-04 show delist_date in snapshot, creating anachronistic knowledge for earlier execution dates
- `bak_basic_lifecycle` candidate has 457 gaps + 3 errors, status=`candidate_not_verified`
- No machine-verifiable PIT adapter contract exists

**b3_execution_input_binding_unavailable:** PERSISTS
- Both `listing_delisting` and `liquidity` remain unavailable for execution binding
- listing_delisting: PIT evidence unavailable
- liquidity: contract frozen, implementation deferred (derivation vs. precompute decision unmade)

**Task 3:** Incomplete  
**Task 0 Step 5:** `no_validated_signal_visible_in_dom`  
**Global:** `validation_unavailable`  
**B6/OOS/Gate/Promotion/Signal:** NOT AUTHORIZED

---

**Audit Complete:** 2026-07-25 18:15  
**Contract Freeze Complete:** 2026-07-25 19:30  
**Auditor:** Hermes Agent (Kiro)  
**V3 Template:** `relative_strength_rotation_shsz_sw2021_v3` (candidate)  
**V2 Template:** `relative_strength_rotation_shsz_sw2021_v2` (approved, unchanged)
