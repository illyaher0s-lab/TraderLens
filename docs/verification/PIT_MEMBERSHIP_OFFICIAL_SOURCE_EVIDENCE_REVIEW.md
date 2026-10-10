# PIT Membership Official Source Evidence Review

**Task:** Task 1 from `docs/superpowers/plans/2026-07-10-credible-manual-trading-decision-closure-plan.md`  
**Date:** 2026-07-15  
**Scope:** Read-only review of official Tushare `index_member_all` documentation for SW2021 historical delisted coverage evidence  
**Reviewer:** AI agent (read-only capacity)

---

## Executive Summary

**Upstream blocker addressed:** `include_delisted_source_contract_unavailable`

**Evidence source reviewed:**
1. Tushare official documentation `index_member_all` (doc_id=335) ✓
2. 申万官方《申万行业分类标准 2021》PDF (retrieval failed) ✗

**Key finding:** Tushare official documentation **数据示例** (data examples) section directly includes delisted securities:
- Row 10: `600687.SH 退市刚泰(退市)` (in_date: 20130701)
- Row 12: `600311.SH *ST荣华(退市)` (in_date: 20140102)

**Conclusion:** `delisted_member_retention_demonstrated_but_completeness_unverified`

**Status upgrade:** `include_delisted_source_contract_unavailable` → `delisted_member_retention_demonstrated_but_completeness_unverified` (sub-state, NOT admission to publish `_002`)

**Authorization for `_002` publication:** ✗ STILL NOT AUTHORIZED (completeness unverified)

**Global status:** `validation_unavailable` (unchanged)

---

## 1. Task Context

### 1.1 Main Plan Reference

**From Section 2 (Gate 0), Task 1:**
> Complete Gate 0 before formal validation wiring

**Dependency chain:**
```
include_delisted_unavailable
  → Cannot publish formal _002 snapshot
  → Cannot perform formal PIT qualification
  → Cannot run B6/OOS/Gate/Promotion
  → Cannot generate separately validated signal
  → Task 0 Step 5 `no_validated_signal_visible_in_dom` remains blocked
```

### 1.2 Prior Evidence Status

**From previous preflight reports:**
- `PIT_MEMBERSHIP_SOURCE_CONTRACT_PREFLIGHT.md` (2026-07-14): examined local manifests, parquet schema, no `include_delisted` field found
- `PIT_MEMBERSHIP_SOURCE_CONTRACT_INCREMENTAL_PREFLIGHT.md` (2026-07-15): examined Tushare doc_id=182 (OUTDATED), no explicit delisted coverage statement

**Doc ID correction:** Previous review examined **doc_id=182**, which is outdated. Current official documentation is **doc_id=335**.

---

## 2. Pre-execution State Verification

### 2.1 Protected Artifact Status

**`pims_traderlens_v2_shsz_sw2021_pit_001` (retired):**
```bash
$ sha256sum data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_001/manifest.json
20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913
```
**Status:** UNCHANGED ✓

**`pims_traderlens_v2_shsz_sw2021_pit_002`:**
```bash
$ ls data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_002/
_002_STILL_NOT_EXISTS
```
**Status:** NOT EXISTS ✓

---

## 3. Official Source Evidence Review

### 3.1 Source 1: Tushare `index_member_all` Documentation

**Locator:**
- URL: `https://tushare.pro/document/2?doc_id=335`
- Title: "申万行业成分构成(分级)"
- Interface: `index_member_all`
- Accessed: 2026-07-15
- Local cache: `/tmp/tushare_doc335.txt`
- Cache SHA-256: `3acb7e2cd7fdb7a9dc8587c1d04e3a7c4a5085045a9f9cd9f29e2733a077b922`

**Interface description (official Chinese text):**
> "按三级分类提取申万行业成分，可提供某个分类的所有成分，也可按股票代码提取所属分类，参数灵活"

**Translation:** "Extract Shenwan industry components by three-level classification, can provide all components of a classification, or extract classification by stock code, flexible parameters"

**Output parameters:**
| Field | Type | Default Display | Description (Chinese) | Description (English) |
|---|---|---|---|---|
| ts_code | str | Y | 成分股票代码 | Component stock code |
| name | str | Y | 成分股票名称 | Component stock name |
| in_date | str | Y | 纳入日期 | Inclusion date |
| out_date | str | Y | 剔除日期 | Removal date |
| is_new | str | Y | 是否最新Y是N否 | Whether latest (Y=yes, N=no) |

**Official data example (数据示例):**
```
Row 10: 801050.SI 有色金属 801053.SI 贵金属 850531.SI 黄金 600687.SH 退市刚泰(退市) 20130701
Row 12: 801050.SI 有色金属 801053.SI 贵金属 850531.SI 黄金 600311.SH *ST荣华(退市) 20140102
```

**Key observations:**
1. ✓ Example includes `600687.SH 退市刚泰(退市)` — explicitly labelled as delisted "(退市)"
2. ✓ Example includes `600311.SH *ST荣华(退市)` — explicitly labelled as delisted "(退市)"
3. ✓ Both delisted securities have `in_date` values (20130701, 20140102)
4. ✓ No `out_date` values shown in truncated example (full data not displayed)

### 3.2 Evidence Matrix: Proposition-Level Assessment

**Proposition A:** `index_member_all` returns historical industry members (not only current)

| Evidence Type | Support | Details |
|---|---|---|
| Field definition | ✓ Direct | `in_date` (纳入日期) and `out_date` (剔除日期) fields exist |
| Official example | ✓ Direct | Example shows `in_date` ranging from 2003-2023 |
| Inference prohibited | N/A | Not needed; directly stated in schema |

**Conclusion:** ✓ PROVEN — Interface explicitly supports historical membership via `in_date`/`out_date` fields.

---

**Proposition B:** The interface returns delisted securities as members

| Evidence Type | Support | Details |
|---|---|---|
| Official example | ✓ Direct | Row 10: `600687.SH 退市刚泰(退市)` |
| Official example | ✓ Direct | Row 12: `600311.SH *ST荣华(退市)` |
| Field definition | ✗ Insufficient | No `delisted` field in schema; relies on name suffix "(退市)" |
| Inference prohibited | N/A | Not needed; examples explicitly include "(退市)" label |

**Conclusion:** ✓ DEMONSTRATED — Official examples directly include delisted securities with "(退市)" label.

**Classification:** **DIRECT EVIDENCE** (not inference from `out_date` presence or record counts)

---

**Proposition C:** The interface guarantees complete historical delisted coverage (all delisted securities, defined boundary)

| Evidence Type | Support | Details |
|---|---|---|
| Official text | ✗ Not stated | No statement about delisted coverage completeness |
| Official example | ✗ Insufficient | Examples prove retention exists, not completeness |
| Coverage boundary | ✗ Not stated | No statement about which delisted securities are included/excluded |
| Historical scope | ✗ Not stated | No statement about delisted coverage start date or cutoff |

**What the evidence proves:**
- ✓ At least some delisted securities are retained in historical membership records
- ✓ At least 2 specific delisted securities (600687.SH, 600311.SH) are present

**What the evidence does NOT prove:**
- ✗ All delisted securities are retained
- ✗ Delisted coverage boundary (e.g., "delisted after 2000", "delisted within last 20 years")
- ✗ Completeness guarantee (e.g., "all A-share delisted securities included")
- ✗ Selection criteria for retained vs. excluded delisted securities (if any)

**Conclusion:** ✗ UNVERIFIED — Retention demonstrated, completeness unverified.

**Classification:** **INSUFFICIENT EVIDENCE** (examples show existence, not completeness)

---

**Proposition D:** SW2021 taxonomy document provides contractual statement about historical member coverage

| Evidence Type | Support | Details |
|---|---|---|
| PDF retrieval | ✗ Failed | `https://wxweb.swsresearch.com/swsreport/2021_08/328340.pdf` download failed |
| Alternative source | ✗ Not attempted | Task constraint: only check two pre-specified sources |

**Conclusion:** ✗ UNAVAILABLE — PDF retrieval failed, cannot assess.

---

## 4. Evidence Classification Summary

### 4.1 Direct Evidence (官方示例直接证据)

**What official examples directly prove:**
1. ✓ `index_member_all` returns historical membership records (via `in_date`/`out_date` schema)
2. ✓ Interface includes at least some delisted securities in returned data (600687.SH, 600311.SH)
3. ✓ Delisted securities are labelled with "(退市)" suffix in `name` field

**Classification:** DIRECT EVIDENCE — no inference required, explicitly shown in official documentation.

### 4.2 Insufficient Evidence (不足证据)

**What official examples do NOT prove:**
1. ✗ Complete coverage of all delisted securities (examples show 2, not all)
2. ✗ Coverage boundary (which delisted securities are included/excluded)
3. ✗ Historical scope (delisted coverage start date or cutoff)
4. ✗ Selection criteria (if any filter is applied to delisted securities)

**Classification:** INSUFFICIENT EVIDENCE — retention demonstrated, completeness unverified.

### 4.3 Prohibited Inference (禁止推断)

**The following would violate evidence standards if used:**
1. ✗ Inferring completeness from `out_date` field presence
2. ✗ Inferring completeness from record count (15,310 rows in local manifest)
3. ✗ Inferring completeness from date range span (1984-2026 in local data)
4. ✗ Inferring completeness from current constituents comparison
5. ✗ Inferring completeness from lifecycle data cross-reference

**Classification:** PROHIBITED — these are NOT source contract evidence.

---

## 5. Status Determination

### 5.1 Can `include_delisted_source_contract_unavailable` Be Resolved?

**Criteria for resolution (from incremental preflight):**
> `include_delisted` status can ONLY be resolved by explicit source contract evidence. Owner CANNOT authorize interpretation of missing source facts.

**What resolution requires:**
- Tushare provides explicit written statement: "本接口包含所有已退市证券的历史行业分类记录" OR
- Tushare provides coverage boundary: "本接口包含YYYY年以后退市的证券" OR
- Independent SW2021 taxonomy document explicitly states delisted coverage scope

**What was found:**
- ✓ Evidence that delisted retention exists (2 examples)
- ✗ No explicit statement about completeness
- ✗ No coverage boundary definition

**Decision:** Resolution criteria NOT met.

### 5.2 Precise Status After Review

**Previous status:** `include_delisted_source_contract_unavailable`

**New findings:**
- Delisted member retention: ✓ DEMONSTRATED (direct evidence)
- Completeness verification: ✗ UNVERIFIED (insufficient evidence)

**Updated status:**
```
PRIMARY: include_delisted_source_contract_unavailable (unchanged)
SUB-STATE: delisted_member_retention_demonstrated_but_completeness_unverified (new)
```

**Interpretation:**
- "Retention demonstrated" = Tushare official examples prove the interface returns at least some delisted securities
- "Completeness unverified" = No evidence about whether all delisted securities are included or coverage boundary

**This sub-state is NOT admission to publish `_002`** — it documents progress but does not satisfy resolution criteria.

---

## 6. Date Semantics Status

**From `PIT_MEMBERSHIP_DATE_RECONCILIATION_POLICY.md`:**
- Date consumption policy: FROZEN (already resolved)
- `in_date`/`out_date` semantics: membership effective dates (confirmed by doc_id=335)
- Source semantics: NOT ALTERED by policy (policy only defines consumption boundaries)

**Status:** `membership_date_semantics_resolved` (via policy, not source contract)

---

## 7. Authorization Decision

### 7.1 Can `_002` Be Published?

**Requirements (from publisher preconditions):**
1. `include_delisted` source contract resolved: ✗ NO (completeness unverified)
2. Date reconciliation policy approved: ✓ YES (frozen policy exists)
3. SW2014 rejection enforcement: ✓ YES (publisher already enforces)
4. `_001` retired/unaccepted: ✓ YES (publisher already rejects)

**Blocking requirement:** `include_delisted` completeness unverified

**Decision:** `_002` publication ✗ STILL NOT AUTHORIZED

### 7.2 What Changed?

**Before this review:**
- Status: `include_delisted_source_contract_unavailable`
- Evidence: None (no retention examples found in doc_id=182)

**After this review:**
- Status: `include_delisted_source_contract_unavailable` (primary, unchanged)
- Sub-state: `delisted_member_retention_demonstrated_but_completeness_unverified` (new)
- Evidence: 2 delisted securities in official examples (direct evidence)

**Progress:** Retention existence proven, completeness gap identified.

---

## 8. Next Steps

### 8.1 To Resolve Completeness Gap

**Owner must obtain ONE of the following:**

**Option A: Tushare explicit statement**
- Contact Tushare support with specific question: "Does `index_member_all` return all historically delisted A-share securities, or only a subset? If subset, what is the coverage boundary?"
- Accept only explicit written answer (support ticket, documentation update, or API changelog)
- Record as source contract binding

**Option B: Independent SW2021 taxonomy specification**
- Obtain official 申万 (Shenwan) SW2021 taxonomy document that explicitly states membership coverage scope for delisted securities
- Document must be authoritative (not third-party analysis or unofficial summary)
- Record as independent source contract

**Option C: Coverage boundary from Tushare**
- If Tushare cannot guarantee all delisted securities, request explicit coverage boundary (e.g., "delisted after 2000", "delisted within last 20 years")
- Owner approves bounded scope as acceptable for V2 formal validation
- Record as bounded source contract (analogous to `availability_bounded_qualified`)

### 8.2 Prohibited Approaches

**Cannot resolve via:**
- ✗ Owner interpretation of examples ("2 examples prove all delisted are included")
- ✗ Statistical inference ("15,310 rows suggest complete coverage")
- ✗ Cross-reference with lifecycle data ("all lifecycle delisted symbols are in membership")
- ✗ Historical date range ("1984-2026 span proves complete historical coverage")

**Reason:** These violate the evidence standard: "Owner CANNOT authorize interpretation of missing source facts."

### 8.3 Preparatory Work (Can Proceed)

**Allowed while completeness unverified:**
- ✓ Draft bounded-scope proposal for owner review (if Option C is pursued)
- ✓ Prepare test data for coverage boundary edge cases
- ✓ Document other Gate 0 prerequisites (market guard validation, etc.)
- ✓ Review V2 template approval status (Task 1-E already completed)

**Still prohibited:**
- ✗ Publish `pims_traderlens_v2_shsz_sw2021_pit_002`
- ✗ Mark any snapshot as `formal_qualified`
- ✗ Run B6/OOS validation
- ✗ Generate signals from V2 template
- ✗ Claim Task 0 Step 5 unblocked

---

## 9. Post-execution Verification

### 9.1 Protected Artifact Integrity

**`pims_traderlens_v2_shsz_sw2021_pit_001/manifest.json`:**
```bash
$ sha256sum data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_001/manifest.json
20a41a626d2b70afa11e7292566702541a143deea2e39be9e3901ae0df691913
```
**Status:** UNCHANGED ✓

**`pims_traderlens_v2_shsz_sw2021_pit_002`:**
```bash
$ ls data/pit/pit_membership_snapshots/pims_traderlens_v2_shsz_sw2021_pit_002/
_002_STILL_NOT_EXISTS
```
**Status:** STILL NOT EXISTS ✓

### 9.2 Files Created

**This report:**
- Path: `docs/verification/PIT_MEMBERSHIP_OFFICIAL_SOURCE_EVIDENCE_REVIEW.md`
- Created: 2026-07-15

**No other files modified or created** ✓

---

## 10. Global Status

**Task correspondence:** Task 1 (Gate 0 PIT membership source contract)

**Evidence conclusion:**
- ✓ Delisted member retention: DEMONSTRATED (Tushare official examples)
- ✗ Delisted coverage completeness: UNVERIFIED (no explicit statement or boundary)

**Blocker status:**
- `include_delisted_source_contract_unavailable` (PRIMARY, unchanged)
- `delisted_member_retention_demonstrated_but_completeness_unverified` (SUB-STATE, new)
- `no_validated_signal_visible_in_dom` (Task 0 Step 5, downstream, still blocked)

**Artifact status:**
- `_001`: retired, hash unchanged, not used as B6 input
- `_002`: not created, not authorized for publication

**Unverified facts:**
1. Whether all A-share delisted securities are included in `index_member_all` historical membership
2. If not all, what is the coverage boundary (date cutoff, listing board, or other criteria)
3. Whether 申万官方 SW2021 taxonomy specification provides contractual coverage statement

**Allow progression to publication:** ✗ NO

**Global status:** `validation_unavailable` (unchanged)

---

## Appendix A: Doc ID Correction

**Obsolete reference:** `doc_id=182` (examined in incremental preflight, 2026-07-15)

**Current official documentation:** `doc_id=335` (examined in this review, 2026-07-15)

**Difference:** `doc_id=335` includes **数据示例** (data examples) section with actual delisted securities, which `doc_id=182` lacked or did not display.

**Impact:** Previous conclusion "no delisted evidence in Tushare documentation" was based on outdated doc_id. Current doc_id provides direct evidence of retention.

---

## Appendix B: Evidence Locators

**Tushare official documentation:**
- Current URL: `https://tushare.pro/document/2?doc_id=335`
- Title: "申万行业成分构成(分级)"
- Interface: `index_member_all`
- Accessed: 2026-07-15
- Local cache: `/tmp/tushare_doc335.txt`
- Cache SHA-256: `3acb7e2cd7fdb7a9dc8587c1d04e3a7c4a5085045a9f9cd9f29e2733a077b922`
- Stable: ✓ (official Tushare documentation)

**申万官方 SW2021 taxonomy PDF:**
- URL: `https://wxweb.swsresearch.com/swsreport/2021_08/328340.pdf`
- Retrieval status: ✗ FAILED (download error)
- Alternative retrieval: Not attempted (task constraint)

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

---

**Report End**
