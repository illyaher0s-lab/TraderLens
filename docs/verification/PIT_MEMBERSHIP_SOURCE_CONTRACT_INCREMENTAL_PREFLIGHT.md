# PIT Membership Source Contract Incremental Evidence Preflight

**Task:** Task 1 from `docs/superpowers/plans/2026-07-10-credible-manual-trading-decision-closure-plan.md`  
**Date:** 2026-07-15  
**Scope:** Incremental evidence check for `include_delisted` and `membership_date_semantics`  
**Status:** `include_delisted_source_contract_unavailable` AND `membership_date_semantics_unavailable`

---

## Executive Summary

**Upstream blockers this task aims to resolve:**
- `include_delisted_source_contract_unavailable` (blocks formal PIT membership snapshot `_002`)
- `membership_date_semantics_unavailable` (blocks formal PIT membership snapshot `_002`)

**Root cause:** Both issues block the formal qualification path required by Task 0 Step 5 `no_validated_signal_visible_in_dom`.

**Outcome:** Both blockers remain **UNAVAILABLE**. No independent, machine-checkable source contract evidence was found.

**Authorization for `_002` publication:** ✗ NOT AUTHORIZED

**Global status:** `validation_unavailable` (unchanged)

---

## 1. Task Context and Constraints

### 1.1 Main Plan Reference

**From Section 2 (Gate 0), Task 1:**
> "Complete Gate 0 before formal validation wiring"
> 
> B6/OOS validation is mechanically impossible without:
> - An approved source-backed template, AND
> - Either a replayable, scope-matching `formal_qualified` PIT manifest OR
> - (for `b6_coverage_bound` only) an exactly bound availability-bounded successor plus every other B6 hard precondition

**Dependency chain:**
```
include_delisted_unavailable + membership_date_semantics_unavailable
  → Cannot publish formal _002 snapshot
  → Cannot perform formal PIT qualification
  → Cannot run B6/OOS/Gate/Promotion
  → Cannot generate separately validated signal
  → Task 0 Step 5 remains blocked
```

### 1.2 Scope Boundaries (Enforced)

**Allowed:**
- Read Tushare official API documentation
- Examine existing source manifests for previously unchecked fields
- Locate stable source contract references (API doc URLs, version identifiers, interface specifications)
- Document date semantics from source field definitions

**Prohibited:**
- Scan daily, daily_basic, adj_factor, coverage, or expected universe data
- Infer include_delisted=true from out_date presence, record counts, or current constituents
- Merge SW2014 and SW2021 evidence
- Create, modify, publish, or pre-occupy `pims_traderlens_v2_shsz_sw2021_pit_002`
- Modify `_001` (must remain retired/unaccepted as audit evidence)
- Create new DataSnapshot, protocol, ledger, or B6/OOS/Gate/Promotion/Signal artifacts
- Modify main plan or production code

**Evidence standard:**
- **Include_delisted:** Only accept if source contract explicitly states historical membership scope includes/excludes delisted securities, OR explicitly states unavailable
- **Date semantics:** Must separately document membership effective dates, source publication dates, snapshot freeze dates, and V2 market data range (2016-01-04 to last closed trading day); cannot conflate membership start date with market data start date

---

## 2. Pre-execution State Verification

### 2.1 Protected Artifact Status

**`pims_traderlens_v2_shsz_sw2021_pit_001` (retired):**
```bash
$ sha256sum data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_001/manifest.json
20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913
```

**Status:** EXISTS, no RETIRED marker file, but publisher/verifier reject it (verified in `PIT_MEMBERSHIP_CORRECTIVE_REPAIR_ACCEPTANCE_REPORT.md`)

**`pims_traderlens_v2_shsz_sw2021_pit_002`:**
```bash
$ ls data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_002/
ls: cannot access: No such file or directory
```

**Status:** NOT EXISTS ✓

### 2.2 Source Binding Verification

**SW2021 membership manifest:**
```bash
$ sha256sum data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json
a38b3cc6be947b290078fe637466991ee8d13dee2794d398fb709d5c4c3826f3
```
**Matches expected:** ✓

**SW2021 candidate:**
```bash
$ sha256sum data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2021_universe_candidate.json
8374602c2b4fda9ca5f9ae2d27daa2ceceee1fe31fb7894dc10d1d8d789fb994
```
**Matches expected:** ✓

**Universe reference:**
```bash
$ sha256sum data/pit/universe_references/uref_traderlens_v2_shsz_sw2021_pit_001/manifest.json
ff34d4c5ba884b1bf9aa55d09880d7e08cb0d39841d1518c002b265275dff0d9
```

**Formal data snapshot:**
```bash
$ sha256sum data/pit/data_snapshot_manifests/ds_traderlens_v2_shsz_pit_001/manifest.json
4c4552a86afa09c5936db85d0c65df85fe28445d87b2372783a5c3f7281b0736
```

**V2 approved template:**
```python
template_id: relative_strength_rotation_shsz_sw2021_v2
version: v2_shsz_sw2021_pit_12m
template_hash: 867a47eeece1c0d208c591f35b5ca31d663ccda183c8721eef803483921238b6
market_fit: SW2021 PIT membership universe
```

---

## 3. Incremental Evidence Investigation

### 3.1 Include_Delisted Source Contract

#### 3.1.1 Previously Checked (from `PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md`)

**Local source manifest:**
- Path: `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json`
- Fields examined: `status`, `description`, `notes`, `collected_at`, `partition_count`, `sw_overlap`
- **Result:** No `include_delisted` declaration found

**Parquet schema:**
- Columns: `l1_code`, `l1_name`, `l2_code`, `l2_name`, `l3_code`, `l3_name`, `ts_code`, `name`, `in_date`, `out_date`, `is_new`
- **Result:** `out_date` semantics clarified as "移出该行业分类日期" (exit from industry classification), NOT delisting date

**SW2021 universe candidate:**
- Path: `sw2021_universe_candidate.json`
- Fields: `status`, `taxonomy_source`, `checked_trade_days`, `lifecycle_unknown_stock_days`, `formal_qualification_run`
- **Result:** No delisting coverage declaration

#### 3.1.2 New Investigation: Tushare Official API Documentation

**Source locator:**
- URL: `https://tushare.pro/document/2?doc_id=182`
- Interface: `index_member_all`
- Description: "按三级分类提取申万行业成分，可提供某个分类的所有成分，也可按股票代码提取所属分类，参数灵活"
- Accessed: 2026-07-15

**Input parameters:**
| Parameter | Type | Required | Description |
|---|---|---|---|
| l1_code | str | N | 一级行业代码 |
| l2_code | str | N | 二级行业代码 |
| l3_code | str | N | 三级行业代码 |
| ts_code | str | N | 股票代码 |
| is_new | str | N | 是否最新（默认为"Y是") |

**Output parameters:**
| Parameter | Type | Default Display | Description |
|---|---|---|---|
| l1_code | str | Y | 一级行业代码 |
| l1_name | str | Y | 一级行业名称 |
| l2_code | str | Y | 二级行业代码 |
| l2_name | str | Y | 二级行业名称 |
| l3_code | str | Y | 三级行业代码 |
| l3_name | str | Y | 三级行业名称 |
| ts_code | str | Y | 股票代码 |
| name | str | Y | 股票名称 |
| in_date | str | Y | 纳入日期 |
| out_date | str | Y | 移出日期 |
| is_new | str | Y | 是否最新 |

**Critical missing fields:**
- No `include_delisted`, `delisted_coverage`, or `历史退市成分` field
- No explicit statement about whether returned membership includes delisted securities
- No explicit statement about whether `out_date != None` records include delisted securities

**What the documentation proves:**
- ✓ Interface exists and is documented
- ✓ `in_date` / `out_date` are documented fields
- ✓ `is_new` parameter controls "是否最新" (whether latest)

**What the documentation does NOT prove:**
- ✗ Whether `is_new='Y'` excludes delisted securities
- ✗ Whether `is_new='N'` includes delisted securities
- ✗ Whether `out_date != None` indicates delisting vs. reclassification
- ✗ Coverage scope for historical membership

#### 3.1.3 Conclusion

**Status:** `include_delisted_source_contract_unavailable`

**Reason:** Tushare official documentation for `index_member_all` does not explicitly state whether the interface includes or excludes delisted securities in historical membership records.

**Evidence gap:**
- `out_date` field semantics documented as "移出日期" (exit date), but exit reason (delisting vs. reclassification vs. taxonomy version change) is not documented
- No `delisted`, `delist_date`, or similar field in output schema
- No statement in documentation about coverage scope for delisted securities

**What would resolve this:**
- Tushare documentation explicitly stating: "本接口包含已退市证券的历史行业分类记录" OR
- Tushare documentation explicitly stating: "本接口不包含已退市证券" OR
- An independent cross-reference field (e.g., `delist_flag`, `exit_reason`) that machine-checkably separates delisting from reclassification

**What does NOT resolve this:**
- Presence of `out_date != None` records (reason ambiguous)
- Record count comparisons (cannot distinguish delisting from reclassification)
- Current constituent checks (introduces survivorship bias)
- Lifecycle data cross-reference (prohibited by task constraints; also would not prove source contract scope)

---

### 3.2 Membership Date Semantics

#### 3.2.1 Previously Identified Issues (from `PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md`)

**Section 2.2 findings:**
- `in_date` / `out_date` are membership effective dates
- No explicit statement about alignment with trading calendar
- No explicit statement about relationship between membership snapshot date and market data range
- Risk: conflating membership horizon, market data horizon, and snapshot freeze date

#### 3.2.2 New Investigation: Date Field Semantics from Tushare Documentation

**From `index_member_all` documentation (2026-07-15):**

**in_date:**
- Chinese: "纳入日期"
- English translation: "Inclusion date" / "Entry date"
- **Interpretation:** Date when security was assigned to this industry classification

**out_date:**
- Chinese: "移出日期"
- English translation: "Exit date" / "Removal date"
- **Interpretation:** Date when security was removed from this industry classification

**What the documentation proves:**
- ✓ `in_date` / `out_date` are membership effective dates (classification assignment/removal dates)
- ✓ These are NOT data collection dates, NOT API call dates, NOT snapshot freeze dates

**What the documentation does NOT prove:**
- ✗ Relationship between `in_date` and first observable market data
- ✗ Relationship between `out_date` and last observable market data
- ✗ Whether these dates align with trading calendar (trade_cal)
- ✗ Whether membership is effective T+0, T+1, or other lag relative to announcement
- ✗ Whether V2 market data range (2016-01-04 to last closed trading day) is covered by membership effective range

#### 3.2.3 Date Semantic Disambiguation (Required)

**Four distinct date concepts that must NOT be conflated:**

1. **Membership effective dates** (`in_date`, `out_date` from SW2021 source)
   - Semantics: Industry classification assignment period
   - Source: Tushare `index_member_all` interface
   - Evidence: Documented as "纳入日期" / "移出日期"

2. **Source data publication/collection dates**
   - Semantics: When Tushare collected or published this membership data
   - Source: Local manifest `collected_at` field
   - Evidence: `"collected_at": "2026-07-12T14:40:17.677866"` (only covers collection, not historical publication)

3. **Formal snapshot freeze date**
   - Semantics: Date when membership snapshot is published as immutable artifact
   - Source: `snapshot_date` in `pims_traderlens_v2_shsz_sw2021_pit_002/manifest.json` (when published)
   - Evidence: NOT YET PUBLISHED (awaiting source contract resolution)

4. **V2 market data trading day range**
   - Semantics: Daily OHLCV data coverage required for formal validation
   - Source: Main plan Section 2 Gate 0
   - Evidence: `2016-01-04` (first SSE trading day after provider's 2016-01-01 start) through last fully closed trading day

**Critical missing reconciliation policy:**
- If membership `in_date` is earlier than V2 market data start (`2016-01-04`), how should snapshot truncate or flag this?
- If membership `out_date` is later than last closed trading day, is this a forward-looking membership (invalid for PIT)?
- If membership spans 1984–2026 but market data is qualified only for 2016-01-04 onwards, can membership be used? With what boundary policy?

#### 3.2.4 Observed Date Ranges (from local source data)

**From `_001` manifest (retired, audit evidence only):**
```json
"date_range_min": "1984-05-09",
"date_range_max": "2026-06-05"
```

**From `sw2021_universe_candidate.json`:**
```json
"checked_trade_days": 2554,
"excluded_pre_listing_stock_days": 71035
```

**Interpretation:**
- Membership source spans **1984-05-09 to 2026-06-05**
- V2 market data formal qualification spans **2016-01-04 to last closed trading day**
- **Gap:** 1984–2016 membership has no qualified market data
- **Question:** Can 1984–2016 membership be used for 2016+ trading? If so, under what boundary rules?

#### 3.2.5 Conclusion

**Status:** `membership_date_semantics_unavailable`

**Reason:** No independent source contract or documented reconciliation policy explains how membership effective dates relate to market data trading day range.

**Evidence gaps:**
1. No documented T+0/T+1 lag between membership assignment and market data observability
2. No documented policy for membership-market data horizon mismatch (1984–2026 membership vs. 2016-01-04+ market data)
3. No documented rule for handling `in_date` < market data start or `out_date` > last closed trading day
4. No explicit statement about whether snapshot_date must be <= last closed trading day

**What would resolve this:**
- Tushare documentation stating: "Membership effective dates align with trading calendar; in_date is the first trading day when classification is effective" OR
- Owner-approved policy document stating: "For V2 formal validation, use membership where `in_date` or `out_date` intersects [2016-01-04, last_closed_trading_day]; truncate or flag memberships outside this range as boundary cases" OR
- Independent reconciliation protocol defining PIT snapshot semantics relative to market data range

**What does NOT resolve this:**
- Observing that `checked_trade_days=2554` (this is universe candidate processing output, not source contract)
- Assuming membership=market data because both exist (different horizons, no documented alignment)
- Using snapshot_date as a truncation policy without explicit design approval

---

## 4. Next Steps

### 4.1 To Resolve `include_delisted_source_contract_unavailable`

**CRITICAL BOUNDARY:**
- `include_delisted` status can ONLY be resolved by explicit source contract evidence
- Owner CANNOT authorize interpretation of missing source facts (e.g., inferring from `out_date` span, record counts, or sample characteristics)
- Prohibition applies to: `out_date` presence, current constituents, lifecycle data cross-reference, coverage row counts, date range spans

**Resolution paths (exhaustive):**
1. Tushare provides explicit written statement about `index_member_all` delisted security coverage (via documentation update, support response, or API changelog), OR
2. Independent authoritative SW2021 taxonomy source document explicitly states historical membership includes/excludes delisted securities

**Required output:**
- Stable reference (Tushare doc URL with explicit include_delisted statement, support ticket ID with written confirmation, or independent SW2021 taxonomy specification)
- Machine-checkable evidence (not interpretation, inference, or policy decision)
- Recorded in formal source contract binding before `_002` publication

### 4.2 To Resolve `membership_date_semantics_unavailable`

**CRITICAL BOUNDARY:**
- Owner CAN decide consumption boundary rules (how to handle horizon mismatch)
- Owner CANNOT redefine source semantics (`in_date`/`out_date` remain membership effective dates from Tushare)
- Reconciliation policy defines TraderLens processing rules, NOT source data meaning

**Owner must:**
1. Approve an explicit reconciliation policy for membership-market data horizon mismatch (1984–2026 membership vs. 2016-01-04+ market data), AND
2. Define boundary rules for `in_date < 2016-01-04` or `out_date` beyond last closed trading day (truncate, flag, or reject), AND
3. State whether snapshot_date must be <= last closed trading day or can be "as of" future date

**Required output:**
- Owner-approved policy document (e.g., `PIT_MEMBERSHIP_DATE_RECONCILIATION_POLICY.md`)
- Explicit rules for truncation, flagging, or rejection of out-of-range memberships
- Policy recorded in formal source contract binding before `_002` publication
- Policy does NOT alter `in_date`/`out_date` source semantics, only defines consumption boundaries

### 4.3 Prohibited Actions Until Resolution

**Cannot proceed:**
- ✗ Publish `pims_traderlens_v2_shsz_sw2021_pit_002`
- ✗ Mark _002 as `formal_qualified`
- ✗ Run B6/OOS validation against SW2021 membership
- ✗ Generate signals from V2 template
- ✗ Claim Task 0 Step 5 unblocked

**Can proceed (preparatory work):**
- ✓ Draft candidate reconciliation policies for owner review
- ✓ Prepare test data for boundary cases (in_date < 2016-01-04, out_date > last closed day)
- ✓ Document other Gate 0 prerequisites (template approval, market guard validation, etc.)

---

## 5. Post-execution Verification

### 5.1 Protected Artifact Integrity

**`pims_traderlens_v2_shsz_sw2021_pit_001/manifest.json`:**
```bash
$ sha256sum data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_001/manifest.json
20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913
```
**Status:** UNCHANGED ✓

**`pims_traderlens_v2_shsz_sw2021_pit_002`:**
```bash
$ ls data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_002/
ls: cannot access: No such file or directory
```
**Status:** STILL NOT EXISTS ✓

### 5.2 Deliverable

**This report:**
- Path: `docs/verification/PIT_MEMBERSHIP_SOURCE_CONTRACT_INCREMENTAL_PREFLIGHT.md`
- Size: 11,897 bytes
- Created: 2026-07-15

**Content:**
- ✓ Distinguished new investigation from prior preflight
- ✓ Recorded Tushare official documentation findings with stable URL
- ✓ Documented exact evidence gaps (no include_delisted statement, no date reconciliation policy)
- ✓ Provided explicit next steps for owner decision
- ✓ Did NOT fabricate evidence, did NOT publish _002, did NOT claim resolution

---

## 6. Global Status

**Blockers resolved:** NONE

**Blockers remaining:**
- `include_delisted_source_contract_unavailable` (Task 1, requires owner/Tushare input)
- `membership_date_semantics_unavailable` (Task 1, requires owner policy approval)
- `no_validated_signal_visible_in_dom` (Task 0 Step 5, downstream of above blockers)

**Global status:** `validation_unavailable` (unchanged)

**V2 template status:** `approved` (Task 1-E completed, but cannot proceed to B6/OOS/Gate without PIT qualification)

**Formal qualification status:** CANNOT START (blocked by membership source contract gaps)

---

## Appendix A: Evidence Retrieval Log

**Tushare API documentation:**
- URL: `https://tushare.pro/document/2?doc_id=182`
- Title: "申万行业成分（分级）"
- Interface: `index_member_all`
- Accessed: 2026-07-15 via browser
- Stable: ✓ (official Tushare documentation)

**Local source manifests:**
- `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/manifest.json`
- `data/pit/tushare/.staging/08857219e6fd61e9/worker_0/formal/sw_l1_membership/sw2021_universe_candidate.json`
- Already examined in prior preflight; no new fields discovered

**Repository search:**
- Searched for: `README`, `INTERFACE_SPEC`, `*_doc.md` in `data/pit/`
- Result: No additional source documentation found

---

## Appendix B: Comparison with Prior Preflight

**`PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md` (2026-07-14):**
- Examined: Local manifests, parquet schema, candidate JSON
- Conclusion: `include_delisted_source_contract_unavailable` + `membership_date_semantics_unavailable`

**This incremental preflight (2026-07-15):**
- **New evidence added:** Tushare official `index_member_all` documentation
- **New findings:** Confirmed `in_date`/`out_date` semantics, but still no include_delisted statement
- **Conclusion:** UNCHANGED (both issues remain unavailable)

**Incremental value:**
- ✓ Verified no additional fields in official API documentation
- ✓ Recorded stable source locator (Tushare doc URL)
- ✓ Confirmed evidence gap is upstream (Tushare documentation itself), not local manifest missing
- ✓ Clarified owner decision points for next steps

---

**Report End**

---

## Owner Decision Addendum — 2026-07-15

The owner has approved the bounded consumption policy in
`PIT_MEMBERSHIP_DATE_RECONCILIATION_POLICY.md`. It preserves raw
`effective_from`/`effective_to`, uses a closed interval only for SH/SZ common
trading days within the validation window and no later than `snapshot_date`,
and structurally rejects invalid or post-snapshot source dates.

Accordingly, the current TraderLens processing-policy blocker
`membership_date_semantics_unavailable` is resolved. This addendum does not
alter the earlier source-evidence finding: it does not redefine Tushare field
semantics or prove delisted-security coverage.

The remaining publication blocker is
`include_delisted_source_contract_unavailable`. `_002` remains unoccupied and
unauthorized.

---

## Scope Semantics Supersession — 2026-07-15

**Context:** Task 3 前置（主计划对应 Task 3 "Qualify PIT universe and real execution inputs"），为解除 `formal_pit_membership_snapshot_unavailable` 的上游阻断，owner 已确定来源范围准入语义的可验证边界。

**Prior blocker semantics (SUPERSEDED):**

`include_delisted_source_contract_unavailable` 的旧含义：
> "外部供应商（Tushare）必须提供合同性保证，声明 `index_member_all` 接口包含全市场全部历史退市证券的完整覆盖，或明确定义覆盖边界。"

**Why superseded:**
1. Tushare 官方文档示例（doc_id=335）直接包含退市证券，证明接口**会返回**此类记录
2. 但无法从外部来源获得"全部退市证券均覆盖"的独立保证或边界声明
3. 该要求将 TraderLens 正式验证阻断在**外部供应商文档完整性声明**上，而非 TraderLens 自身发布器行为的可验证性上

**New semantics (EFFECTIVE 2026-07-15):**

`include_delisted` 的准入语义现定义为：
> 对已绑定的 `index_member_all` 历史 membership 来源，TraderLens 的正式 PIT snapshot 发布器**不得**依据证券后来退市、当前 constituents、lifecycle、coverage、expected universe 或人工名单删除、替换或补造任何来源 membership record。

**What this means:**
- ✓ 发布器必须原样保留来源 membership records（包括标注为退市的记录）
- ✓ 发布器不得因"证券已退市"而过滤掉来源中存在的 membership 记录
- ✓ 发布器不得因"证券未退市"而补造来源中不存在的 membership 记录
- ✗ 不声称 Tushare 数据是全市场退市证券的独立完备登记册
- ✗ 不声称来源覆盖边界已被外部供应商文档验证

**Mandatory disclosure for future formal artifacts:**

未来 `_002` 及后续正式 snapshot 必须在 manifest 中包含：
```json
"vendor_scope_disclosure": {
  "historical_membership_scope": "vendor_provided_unverified",
  "disclosure_text": "This snapshot preserves all membership records from bound source partitions (Tushare index_member_all SW2021). TraderLens does not independently verify that the vendor's historical membership data constitutes a complete registry of all market-wide delisted securities. Vendor coverage boundaries, if any, are not contractually documented."
}
```

**New blocker (replaces old blocker):**

`include_delisted_source_contract_unavailable` (旧) → `source_record_retention_verification_pending` (新)

**New blocker semantics:**
> 在 `_002` 发布前，必须通过代码验证以下事实：
> 1. Snapshot records 仅来自已绑定的 SW2021 source partitions
> 2. 不混入 SW2014 source records
> 3. 原始 `effective_from` / `effective_to` 原样保留（不依据消费政策修改来源日期）
> 4. 不存在按退市状态过滤的代码路径（无 `if delisted: skip` 等逻辑）
> 5. Record 数量、canonical source hash、source partition hash 映射可复核
> 6. Duplicate、overlap、非法区间、日期晚于 `snapshot_date` 仍为结构性失败（既有 verifier 行为）

**Verification responsibility shift:**
- **旧责任**：证明外部来源包含全部退市证券（TraderLens 无法独立验证）
- **新责任**：证明 TraderLens 发布器不篡改来源记录（TraderLens 可自主验证）

**What is NOT resolved:**
- ✗ 旧 blocker 不标记为"来源事实已证明"
- ✗ 不声称 Tushare 覆盖边界已知
- ✗ `formal_pit_membership_snapshot_unavailable` 仍保持（`_002` 未发布、未验证）
- ✗ `validation_unavailable` 全局状态保持

**Future publication preconditions (unchanged in count, updated in content):**
1. ✓ Date reconciliation policy approved (already resolved via `PIT_MEMBERSHIP_DATE_RECONCILIATION_POLICY.md`)
2. ✓ SW2014 rejection enforcement (publisher already implements)
3. ✓ `_001` retired/unaccepted (publisher already rejects)
4. **→ Source-to-record retention verification (replaces old include_delisted requirement)**

**Authorization status:**
- `_002` publication: ✗ STILL NOT AUTHORIZED (verification pending)
- B6/OOS/Gate/Promotion: ✗ STILL BLOCKED (no formal qualified snapshot)
- Task 0 Step 5: ✗ STILL BLOCKED (no validated signal)

**Global status:** `validation_unavailable` (unchanged)

**Artifacts protected:**
- `_001` hash: `20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913` (verified unchanged)
- `_002`: NOT EXISTS (verified)
- `data/pit/` partitions: 20,694 files unchanged

---

**Supersession End**
the global workflow status remains `validation_unavailable`.
