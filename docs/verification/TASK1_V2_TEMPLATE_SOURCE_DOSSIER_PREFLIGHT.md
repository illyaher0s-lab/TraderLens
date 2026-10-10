# Task 1-B: V2 Template Source Dossier Preflight Report

**Report Date:** 2026-07-15  
**Task Reference:** Main plan `docs/superpowers/plans/2026-07-10-credible-manual-trading-decision-closure-plan.md` Task 1, section 2.3, L168–171  
**Upstream Blocker:** `template_governance_review_unavailable`  
**Browser Chain Blocker (unchanged):** Task 0 Step 5 `no_validated_signal_visible_in_dom`  
**Canonical Evidence:** `docs/verification/CREDIBLE_RUN_20260715_100308/`

---

## Executive Summary

**Status (Updated 2026-07-15):** `source_locator_available` + `mapping_draft_ready` → **Human review input required**

**Audit Note:** Initial tool access attempt (web_extract via ddgs backend) failed with `source_locator_unavailable`. Corrected via browser navigation to verified PDF source: `https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf` (28 pages, Journal of Finance 48(1):65-91). Prior conclusion no longer current.

**Current State:**
- V2 candidate template: `relative_strength_rotation_shsz_sw2021_v1`
- Governance status: `candidate`
- Source citation: DOI `10.1111/j.1540-6261.1993.tb04702.x` (Jegadeesh & Titman, 1993)
- Source retrieval date: 2026-07-10
- Verified source URI: https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
- Production approved templates: **0**
- Global status: `validation_unavailable`

**Locators Verified:** p.65 abstract (3-12 month horizons), p.67 (NYSE/AMEX 1965-1989), p.68 (monthly formation and overlapping K-month cohorts), p.73 Table II (decile portfolios, equal-weight), p.90 conclusion (long-term performance not permanent).

**Candidate Mapping Draft:** 19 enumerated mapping rows (Section 3): 2 `source_claim` and 17 `implementation_constraint`. The draft is subject to the recorded AI technical review and owner authorization path.

**Next Step (Blocked):** `template_revision_required` — the current template does not freeze the formation/lookback period.

---

## 1. Source Evidence Availability

### 1.1 Formal Citation
- **Title:** Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency
- **Authors:** Narasimhan Jegadeesh, Sheridan Titman
- **Journal:** Journal of Finance
- **Volume/Issue:** Volume 48, Issue 1
- **Publication Date:** March 1993
- **Pages:** 65-91
- **DOI:** 10.1111/j.1540-6261.1993.tb04702.x
- **Retrieval Date:** 2026-07-10

### 1.2 Access Status (Updated 2026-07-15)
- **Existence:** ✓ Formal publication verified via JSTOR, Wiley Online Library, RePEc
- **Direct Content Access:** ✓ **source_locator_available**
  - **Verified PDF URI:** https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
  - **Access Method:** Browser navigation (web_extract ddgs backend failed, not repeated)
  - **Document Length:** 28 pages (Journal of Finance 48(1):65-91)
  - **Status:** Page-level content, tables, and verbatim claims retrieved

### 1.3 Primary Source Locators (Verified)
The following locators were directly observed via browser navigation to the verified PDF:

- **p.65 Abstract:** "This paper documents that strategies which buy stocks that have performed well in the past and sell stocks that have performed poorly in the past generate significant positive returns over 3- to 12-month holding periods."
- **p.67 Section II.A (The Data):** "Our sample includes all stocks on the NYSE and AMEX for the period 1965 to 1989." Formation periods and holding periods range from 3 to 12 months.
- **p.73 Table II:** "Returns to Portfolios Formed on the Basis of Their Prior Six-Month Returns." Shows decile portfolios (10 groups) with equal-weighted construction. Winner portfolio (highest past returns) shows positive subsequent returns.
- **p.90 Conclusions:** "The evidence...suggests that the profitability of the momentum strategies is unlikely to be permanent." Long-term reversals observed after 12 months.

---

## 2. Frozen Rule Inventory

### V2 Template: `relative_strength_rotation_shsz_sw2021_v1`
**Version:** `v1_shsz_sw2021_pit`  
**Governance Status:** `candidate`  
**Universe Rule Type:** `point_in_time_membership`

**Frozen Rules (from `backend/services/strategy_template_library.py` L360-392):**

| Rule Category | Current Frozen Rule |
|---------------|---------------------|
| **entry_rules** | "Top 15% relative strength confirmed over 3 days" |
| **exit_rules** | "Exit when rank drops below 40% or max 15 days or 8% stop-loss" |
| **risk_rules** | "Green/yellow market regime, min 50M avg daily volume" |
| **position_sizing_rules** | "Equal weight across max 5 positions, weekly rebalance" |
| **market_fit** | "A-share relative strength, SH/SZ markets, SW2021 PIT industry control group" |
| **forbidden_market** | `("limit_up", "st_stock", "delisting_risk")` |
| **supported_universe_rule_types** | `("point_in_time_membership",)` |

**Strategy Config Payload:**
```json
{
  "entry": {"relative_strength_rank_pct_max": 15, "confirm_days": 3},
  "exit": {"rank_exit_pct_min": 40, "max_holding_days": 15, "stop_loss_pct": 8},
  "risk": {"market_regime_allowed": ["green", "yellow"], "min_avg_amount_20d": 50000000},
  "rebalance": {"frequency": "weekly", "max_positions": 5}
}
```

---

## 3. Source-to-Rule Evidence Matrix (Candidate Mapping Draft)

**Mapping Status:** `mapping_draft_ready` → **Awaiting human review**

This is a **candidate-only** structured mapping. Each frozen rule is classified and traced to source locators where applicable. This draft does not constitute approval; an attributable AI technical approval plus explicit owner authorization is required for the exact frozen content.

### Classification Discipline Applied:
- **source_claim:** Paper directly supports the directional hypothesis (past winners outperform)
- **implementation_constraint:** Adaptation for A-share market structure, regulatory requirements, or operational constraints not specified in source
- **unsupported:** No academic foundation (none identified)

---

### 3.1 Entry Rules

| Frozen Rule ID | Current Rule Text | Classification | Source Locator | Faithful Summary | Why Source Supports/Does Not Support | Market-Scope Difference | Human Review Required |
|----------------|-------------------|----------------|----------------|------------------|--------------------------------------|-------------------------|-----------------------|
| **relative_strength_direction** | "Top [X]% relative strength" concept | `source_claim` | p.65 abstract, p.73 Table II | "Strategies which buy stocks that have performed well in the past...generate significant positive returns." Table II shows decile portfolios formed on past 6-month returns. | Paper's core hypothesis: past return ranking predicts future returns. Directional claim supported. | US NYSE/AMEX 1965-1989 vs SH/SZ A-shares 2020+. T+1 settlement, 10% daily limits, ST designation, state intervention risk not present in original sample. | ✓ Yes |
| **top_15_pct_threshold** | "Top 15% relative strength" | `implementation_constraint` | N/A (paper uses deciles = top 10%) | Table II constructs 10 equal-sized groups (deciles), not 15% threshold. | Paper does not specify 15%. Discretionary parameter choice. | N/A — implementation detail | ✓ Yes |
| **confirm_days_3** | "confirmed over 3 days" | `implementation_constraint` | N/A | Paper formation period: 3-12 months (p.67). No intra-period daily confirmation requirement. | Paper does not impose day-by-day confirmation. Template adds confirmation for A-share T+1 settlement and volatility. | A-share 10% daily limit + T+1 settlement requires confirmation window not needed in US continuous trading. | ✓ Yes |
| **formation_period_mismatch** | Template uses no explicit formation period parameter | `implementation_constraint` | p.67: "formation periods...from 3 to 12 months" | Paper tests multiple formation horizons (3, 6, 9, 12 months). Template does not freeze a formation period. | **Mismatch:** Paper's "past performance" is 3-12 month trailing returns. Template "relative_strength" unspecified lookback. | Cannot verify fidelity without frozen formation period. | ✓ Yes — **Critical gap** |

**Entry Rule Summary:**  
- ✓ Directional hypothesis (relative strength) supported by p.65, p.73  
- ✗ 15% threshold: implementation_constraint (paper uses 10% deciles)  
- ✗ 3-day confirmation: implementation_constraint (paper has no intra-period confirmation)  
- ✗ **Formation period undefined in template** — paper uses 3-12 month trailing returns, template frozen rules do not specify lookback window

---

### 3.2 Exit Rules

| Frozen Rule ID | Current Rule Text | Classification | Source Locator | Faithful Summary | Why Source Supports/Does Not Support | Market-Scope Difference | Human Review Required |
|----------------|-------------------|----------------|----------------|------------------|--------------------------------------|-------------------------|-----------------------|
| **rank_exit_concept** | "Exit when rank drops below [X]%" | `implementation_constraint` | p.68 (mismatch reference) | Paper forms portfolios monthly and closes each cohort after its fixed K-month holding period; it does not use rank-triggered exits. | Paper does not specify rank-based exits; this is an A-share implementation choice rather than a source claim. | US monthly overlapping cohorts vs A-share weekly rank monitoring; T+1 adds exit latency. | ✓ Yes |
| **rank_40_pct_threshold** | "rank drops below 40%" | `implementation_constraint` | N/A | Paper rebalances at fixed horizons (3, 6, 9, 12 months), not at rank thresholds. | Paper does not specify intra-period rank exit thresholds. | A-share implementation choice for risk management. | ✓ Yes |
| **max_holding_15_days** | "max 15 days" | `implementation_constraint` | p.67: holding periods "from 3 to 12 months" | Paper holding periods: 3, 6, 9, 12 months (90-365 days). | **Severe mismatch:** Paper tests multi-month horizons. Template 15-day max is 5-20× shorter. | A-share volatility and liquidity constraints drive shorter holding. Paper's momentum horizon fundamentally different. | ✓ Yes — **Critical gap** |
| **stop_loss_8_pct** | "8% stop-loss" | `implementation_constraint` | N/A | No stop-loss mechanism in paper. | Paper does not employ stop-loss. Equal-weighted portfolios held to rebalancing date. | A-share 10% daily limit + volatility requires stop-loss not present in US 1965-1989 sample. | ✓ Yes |

**Exit Rule Summary:**  
- ✗ Rank-based exit is an implementation constraint; the paper instead uses fixed K-month exits for monthly overlapping cohorts.  
- ✗ 40% threshold: implementation_constraint  
- ✗ **15-day max hold: severe temporal mismatch** (paper 90-365 days)  
- ✗ 8% stop-loss: implementation_constraint (paper has no stop-loss)

---

### 3.3 Risk Rules

| Frozen Rule ID | Current Rule Text | Classification | Source Locator | Faithful Summary | Why Source Supports/Does Not Support | Market-Scope Difference | Human Review Required |
|----------------|-------------------|----------------|----------------|------------------|--------------------------------------|-------------------------|-----------------------|
| **market_regime_filter** | "Green/yellow market regime" | `implementation_constraint` | N/A | No market regime filtering in paper. | Paper uses all NYSE/AMEX stocks across full sample period (1965-1989) without regime filtering. | A-share state intervention (circuit breakers, trading halts, regulatory action) requires regime awareness not present in US market. | ✓ Yes |
| **min_volume_50M** | "min 50M avg daily volume" | `implementation_constraint` | p.67: "all stocks on the NYSE and AMEX" | Paper uses all listed stocks. No explicit liquidity filter stated. | Paper does not specify minimum volume thresholds. Likely includes small-cap stocks. | A-share market fragmentation and retail dominance create liquidity risk not modeled in paper. | ✓ Yes |

**Risk Rule Summary:**  
- ✗ Market regime filter: implementation_constraint (no regime filtering in paper)  
- ✗ 50M volume filter: implementation_constraint (paper uses all listed stocks)

---

### 3.4 Position Sizing Rules

| Frozen Rule ID | Current Rule Text | Classification | Source Locator | Faithful Summary | Why Source Supports/Does Not Support | Market-Scope Difference | Human Review Required |
|----------------|-------------------|----------------|----------------|------------------|--------------------------------------|-------------------------|-----------------------|
| **equal_weight_concept** | "Equal weight" | `source_claim` | p.73 Table II caption | "equally weighted portfolios" | Paper uses equal-weighted portfolio construction. Methodology match. | Implementation fidelity maintained. | ✓ Yes |
| **max_5_positions** | "max 5 positions" | `implementation_constraint` | p.73: decile portfolios = 10% of universe | Paper constructs decile portfolios (10% of ~3000 stocks ≈ 300 stocks per portfolio). | **Severe mismatch:** Paper uses 10% of universe (~300 stocks). Template uses max 5 positions. | Concentration vs diversification. Paper's equal-weighted decile is highly diversified; template's 5-position limit is concentrated. | ✓ Yes — **Critical gap** |
| **weekly_rebalance** | "weekly rebalance" | `implementation_constraint` | p.68 | At the beginning of each month, the paper forms a new J-month/K-month cohort; K active cohorts overlap, and reported equal-weight portfolios are rebalanced monthly. | Paper does not use weekly rebalancing. Template increases turnover and differs from the paper's monthly overlapping-cohort construction. | Higher turnover for A-share implementation. Paper's lower turnover reduces transaction costs. | ✓ Yes |

**Position Sizing Summary:**  
- ✓ Equal-weight concept supported by p.73  
- ✗ **Max 5 positions: severe diversification mismatch** (paper ~300 per decile)  
- ✗ Weekly rebalance: implementation_constraint (paper forms monthly overlapping cohorts, not weekly portfolios)

---

### 3.5 Market Fit & Universe

| Frozen Rule ID | Current Rule Text | Classification | Source Locator | Faithful Summary | Why Source Supports/Does Not Support | Market-Scope Difference | Human Review Required |
|----------------|-------------------|----------------|----------------|------------------|--------------------------------------|-------------------------|-----------------------|
| **market_sh_sz** | "SH/SZ A-shares" | `implementation_constraint` | p.67: "NYSE and AMEX for the period 1965 to 1989" | US equity markets only. | **No generalization claim to A-shares.** Paper makes no claim about Chinese equity markets. | Different market structure, regulatory regime, investor base, information efficiency, state intervention. | ✓ Yes — **Critical** |
| **sw2021_pit** | "SW2021 PIT industry control group" | `implementation_constraint` | N/A (paper has no industry classification) | Paper does not use industry classification. | Paper constructs portfolios purely on past return ranking, no industry control. | Template adds industry control not present in original research. | ✓ Yes |
| **point_in_time_membership** | Universe rule type | `implementation_constraint` | p.67: survivorship bias not explicitly addressed | Paper uses all listed stocks. Survivorship bias concerns raised in literature post-1993. | Paper does not explicitly state point-in-time membership methodology. | A-share delisting and ST mechanisms differ from US. Template adds survivorship bias protection. | ✓ Yes |
| **forbidden_limit_up** | "limit_up" | `implementation_constraint` | N/A | No daily price limits in US market. | US market has no 10% daily limit. | A-share 10% daily limit unique to Chinese market structure. | ✓ Yes |
| **forbidden_st_stock** | "st_stock" | `implementation_constraint` | N/A | No ST designation in US market. | US has different delisting criteria, no "Special Treatment" designation. | A-share regulatory mechanism. | ✓ Yes |
| **forbidden_delisting_risk** | "delisting_risk" | `implementation_constraint` | N/A | Different delisting criteria. | US delisting mechanisms differ from A-share. | Regulatory difference. | ✓ Yes |

**Market Fit Summary:**  
- ✗ **Entire market scope is implementation_constraint:** Paper makes no claim about A-shares, SH/SZ markets, SW2021 classification, T+1 settlement, price limits, or ST designation.

---

### 3.6 Critical Gaps Summary

**Temporal Mismatch:**  
- Paper: at each month start, rank on J = 3/6/9/12 prior months and hold each new cohort for K = 3/6/9/12 months; K cohorts overlap.  
- Template: Undefined formation + 15-day max hold  
- **Gap:** Template holding period 5-20× shorter than paper's tested horizons

**Diversification Mismatch:**  
- Paper: ~300 stocks per decile portfolio  
- Template: Max 5 positions  
- **Gap:** Template 60× more concentrated

**Market Scope Mismatch:**  
- Paper: US NYSE/AMEX 1965-1989  
- Template: SH/SZ A-shares 2020+, T+1, 10% limits, ST, state intervention  
- **Gap:** No claim in paper that momentum generalizes to A-share structure

**Unsupported Rules:** None. The 19 enumerated mapping rows classify as `source_claim` (2) or `implementation_constraint` (17).

---

### 3.7 Candidate Mapping Conclusion

**Source Claims Supported (2):**  
1. Relative strength directional hypothesis (p.65, p.73)  
2. Equal-weight portfolio construction (p.73)

**Implementation Constraints (17):**  
All parameters (15%, 3 days, 40%, 15 days, 8%, market regime, 50M volume, weekly, 5 positions), market scope (SH/SZ, SW2021, T+1, limits, ST), risk controls, and forbidden markets.

**Critical Mismatches Requiring AI Review and Owner Authorization:**  
1. Formation period undefined in template vs paper's 3-12 month specification  
2. Holding period 15 days vs paper's 90-365 days  
3. Diversification 5 positions vs paper's ~300 per portfolio  
4. Market generalization from US 1965-1989 to A-share 2020+

**Mapping Status:** `ai_technical_review_completed_with_revision_required` — 19 enumerated rules are traced to source locators or marked as implementation constraints. The recorded AI review requires a new candidate because the current template does not freeze the formation/lookback period.

---

## 4. AI Technical Review and Owner Authorization

**Status:** `ai_technical_review_completed_with_revision_required`. `human_review_input_unavailable` remains a factual absence but is no longer the governance gate under the owner-approved review model.

### 4.1 Recorded Review and Decision

| Required Field | Recorded Value | Requirement |
|----------------|----------------|-------------|
| **reviewer_id** | `ai_reviewer_openai_codex_gpt5` | AI technical reviewer; never represented as human |
| **reviewer_kind** | `ai_technical_reviewer` | Attributable review identity |
| **reviewed_at** | `2026-07-15` | Actual technical-review completion date |
| **review_due_date** | `not_applicable` | Revision-required review; a due date is required only for an approved version |
| **review_decision** | `revision_required` | Not approved; current version remains candidate |
| **owner_authorization** | `2026-07-15 owner-authorized AI-review governance model` | Authorizes the model, not approval of this revision-required template |

### 4.2 Per-Rule Review Outcome

The AI technical review accepts the two source-claim hypotheses and equal-weight concept, accepts the market-scope disclosure, and requires revision because the template does not freeze a formation/lookback period. It treats the 15-day hold and five-position cap only as hypotheses/implementation constraints requiring later PIT/IS/OOS/Gate evidence.

For a future candidate version, the AI technical reviewer must verify:
- Locator precision (p.65, p.68, p.73, p.90 as applicable)
- Claim fidelity and the directional-hypothesis versus parameter-level distinction

For each `implementation_constraint`, the AI technical reviewer must assess:
- **Necessity:** Is this constraint required for A-share implementation?
- **Validity impact:** Does this constraint materially alter research hypothesis?
- **Alternatives:** Are alternative parameters more faithful to source?
- **Critical gaps:** frozen formation period, 15-day hold vs 90-365 days, 5 positions vs ~300, market generalization

### 4.3 Market-Scope Difference Confirmation (RECORDED)

The AI technical review explicitly acknowledges:
- Original research: US NYSE/AMEX equities, 1965-1989, no daily limits, no T+1, no ST, continuous trading
- Template implementation: SH/SZ A-shares, 2020+, T+1 settlement, 10% daily limits, ST designation, state intervention risk
- **Delta disclosure:** These differences may invalidate source hypothesis; template is **not a replication** of Jegadeesh & Titman (1993) findings
- **Critical question:** Does momentum effect documented in US 1965-1989 generalize to A-share market structure with 5-20× shorter holding periods and 60× higher concentration?

---

## 5. Blocked Dependencies

### 5.1 Task 0 Step 5 (Unchanged)
**Blocker:** `no_validated_signal_visible_in_dom`  
**Root Cause:** 0 approved templates → `list_approved_templates()` returns empty → template_matcher returns `no_approved_template` → no signal generation  
**Upstream Chain:** `template_revision_required` → `ai_technical_review_completed_with_revision_required` → `source_locator_available` → browser chain blocked

### 5.2 Task 1-B Correction (This Task)
**Previous Blocker:** `source_locator_unavailable` ✗  
**Current Status:** `source_locator_available` ✓ + `ai_technical_review_completed_with_revision_required`  
**Remaining Blocker:** `template_revision_required` (formation/lookback is not frozen in the current version)

### 5.3 Downstream Blockers (Unchanged)
- **B6 Validation:** Blocked by 0 approved templates
- **OOS Authorization:** Blocked by no `formal_qualified` PIT manifest (availability_bounded_qualified semantic per main plan L163)
- **Gate Qualification:** Blocked by no B6 pass
- **Signal Generation:** Blocked by no Gate pass
- **Promotion:** Blocked by no Signal

---

## 6. Updated Status Summary

**Template:** `relative_strength_rotation_shsz_sw2021_v1`  
**Governance:** `candidate` (unchanged)  
**Approved Templates:** 0 (unchanged)  
**Task 0 Step 5:** BLOCKED (unchanged)  
**Global Status:** `validation_unavailable` (unchanged)

**Progress:**
- ✓ Source evidence available (DOI + verified PDF URI)
- ✓ Source locators verified (p.65, p.67, p.73, p.90)
- ✓ Candidate mapping draft ready (Section 3)
- ✗ Human review input unavailable
- ✗ Template governance review unavailable
- ✗ Template approval unavailable

**Unresolved Semantic Issue:** Main plan L163 specifies `formal_qualified` PIT as B6 hard precondition. Owner allowance of `availability_bounded_qualified` for `b6_coverage_bound` creates ambiguity. This preflight does not re-litigate that constraint; it remains out of scope for template governance.

---

## 7. Formal Review Checklist

**Current Readiness:** ⚠️ **Revision required — current template remains candidate**

| Checkpoint | Status | Notes |
|------------|--------|-------|
| **Source citation verified** | ✓ Pass | DOI 10.1111/j.1540-6261.1993.tb04702.x |
| **Source content retrieved** | ✓ Pass | https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf |
| **Page-level locators** | ✓ Pass | p.65, p.67, p.73, p.90 verified |
| **Verbatim source claims** | ✓ Pass | Abstract, Table II, conclusions extracted |
| **Source-to-rule mappings drafted** | ✓ Pass | Section 3 contains 19 enumerated rows: 2 source_claims + 17 implementation_constraints |
| **Market-scope difference documented** | ✓ Pass | Section 3.5, 3.6 disclose US 1965-1989 vs A-share 2020+ |
| **Critical gaps identified** | ✓ Pass | Formation period, holding period, diversification, market generalization flagged |
| **AI technical review recorded** | ✓ Pass | `ai_reviewer_openai_codex_gpt5`, 2026-07-15, `revision_required` |
| **Owner authorization recorded** | ✓ Pass | Authorizes the AI-review governance model, not approval of this revision-required version |

**Gate:** Template remains `candidate` because the recorded AI technical decision is `revision_required`. A future exact version/hash needs a new AI technical approval and owner authorization; neither current source evidence nor this review authorizes template approval.

---

## 8. Prohibitions Enforced

- ✓ No template status change (remains `candidate`)
- ✓ No approval granted
- ✓ No code/test/plan modifications
- ✓ No PIT artifact operations
- ✓ No Gate 0/B6/OOS/Signal operations
- ✓ No fabricated reviewer data
- ✓ No claim that project is "nearly complete" or "validation ready"
- ✓ No representation of academic findings as A-share trading advice
- ✓ No PDF download/storage (only URI + page references recorded)
- ✓ Single-source discipline (Jegadeesh & Titman 1993 only, no literature expansion)

---

## 9. Conclusions

### 9.1 Current Status
- **V2 Template:** `relative_strength_rotation_shsz_sw2021_v1`
- **Governance Status:** `candidate` (unchanged)
- **Production Approved Templates:** **0** (unchanged)
- **Task 0 Step 5 Browser Chain:** `BLOCKED` (unchanged)
- **Global Status:** `validation_unavailable` (unchanged)

### 9.2 This Task's Outcome (Corrected)
**Initial Preflight Status:** `source_locator_unavailable` (2026-07-15 first attempt)  
**Corrected Status:** `source_locator_available` + `mapping_draft_ready` (2026-07-15 correction)

**Achieved:**
- ✓ Formal citation verified
- ✓ Source content accessed (browser navigation to verified PDF)
- ✓ Page-level locators extracted (p.65, p.67, p.73, p.90)
- ✓ Frozen rules inventoried
- ✓ Source-to-rule candidate mapping drafted (Section 3)
- ✓ Market-scope differences documented
- ✓ Critical gaps identified (formation period, holding period, diversification, market generalization)
- ✓ AI technical review and owner-authorized governance model recorded

**Not Achieved:**
- ✓ AI technical review recorded: `revision_required`
- ✓ Owner authorization recorded for the AI-review governance model
- ✗ Template approval

### 9.3 Critical Findings

**Source Support Limited to Directional Hypothesis:**  
Jegadeesh & Titman (1993) supports:
1. Past relative strength predicts future returns (p.65, p.73)
2. Equal-weighted portfolio construction (p.73)

**All Other Rules Are Implementation Constraints:**  
- Parameters (15%, 3 days, 40%, 15 days, 8%, 50M volume, 5 positions, weekly)
- Market scope (SH/SZ, SW2021, T+1, limits, ST)
- Risk controls (market regime, liquidity)

**Severe Temporal & Diversification Mismatches:**  
- Paper: 90-365 day holding, ~300 stocks per portfolio
- Template: 15-day max hold, 5 positions max
- **Gap:** 5-20× shorter horizon, 60× higher concentration

**No Generalization Claim to A-Shares:**  
Paper makes no claim about Chinese equity markets, T+1 settlement, daily price limits, ST designation, or state intervention mechanisms.

### 9.4 Next Steps (Blocked by Required Revision)

**Immediate Blocker:** `template_revision_required` — the formation/lookback period is not frozen in the current template.

**Required to Proceed:**
1. Owner allocates a new candidate template/version identity; the current template/version/hash remains immutable and candidate.
2. The new candidate freezes a precise formation/lookback period and corrects the dossier's monthly formation and overlapping-holding description.
3. Repeat AI technical review and bind an explicit owner authorization to the new frozen content.
4. Only an `approved` decision for that exact new content can remove the template-governance blocker. Task 0 Step 5 remains blocked until the separate Gate 0, qualified PIT input, B6/OOS, Gate, Promotion, and Signal prerequisites have all passed.

**Estimated Timeline:** Unknown (contingent on owner allocation of a new candidate version and a frozen formation/lookback rule)

---

## 10. Evidence Traceability

**This Report:**
- Location: `docs/verification/TASK1_V2_TEMPLATE_SOURCE_DOSSIER_PREFLIGHT.md`
- Created: 2026-07-15 (initial preflight)
- Updated: 2026-07-15 (source locator correction)
- Purpose: Candidate mapping draft for V2 template governance review

**Related Artifacts:**
- Main Plan: `docs/superpowers/plans/2026-07-10-credible-manual-trading-decision-closure-plan.md`
- Task 0 Evidence: `docs/verification/CREDIBLE_RUN_20260715_100308/`
- Template Library: `backend/services/strategy_template_library.py` L371-392
- Contracts: `contracts/strategy.py` L19-82
- Governance Tests: `tests/test_template_governance_v2.py`
- Verified Source: https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf

**Audit Trail:**
- 2026-07-15 Initial attempt: web_extract via ddgs backend failed (`source_locator_unavailable`)
- 2026-07-15 Correction: browser_navigate to verified PDF URI → locators extracted (p.65, p.67, p.73, p.90)
- Status progression: `source_locator_unavailable` → `source_locator_available` + `mapping_draft_ready`
- Remaining blocker: `template_revision_required` → Task 0 Step 5 blocked

**Signature:**
- Report Status: `source_locator_available` + `mapping_draft_ready`
- Template Status: `candidate`
- Approved Count: 0
- Browser Chain: BLOCKED
- Global Status: `validation_unavailable`

**End of Report**
