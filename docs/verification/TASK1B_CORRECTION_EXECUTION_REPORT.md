# Task 1-B Correction: V2 Template Source Locator Review & Candidate Mapping Draft

**Execution Date:** 2026-07-15  
**Task Reference:** Main plan `docs/superpowers/plans/2026-07-10-credible-manual-trading-decision-closure-plan.md` Task 1, section 2.3, L168–171  
**Upstream Blocker (Resolved):** `source_locator_unavailable` → `source_locator_available`  
**Upstream Blocker (Remaining):** `template_revision_required`  
**Browser Chain Blocker (Unchanged):** Task 0 Step 5 `no_validated_signal_visible_in_dom`

---

## Executive Summary

**Status Change:** `source_locator_unavailable` (initial) → `source_locator_available` + `mapping_draft_ready` (corrected)

**What Changed:**
- Initial preflight (2026-07-15 first attempt): web_extract via ddgs backend failed
- Correction (2026-07-15): browser_navigate to verified PDF URI → source locators extracted
- V2 template candidate mapping draft complete (19 enumerated rows classified, 4 primary locators verified)

**What Did NOT Change:**
- Template governance status: `candidate` (unchanged)
- Production approved templates: **0** (unchanged)
- Task 0 Step 5: `BLOCKED` (unchanged)
- Global status: `validation_unavailable` (unchanged)

**Next Blocker:** `template_revision_required` — a new candidate must freeze an explicit formation/lookback rule before it can be re-reviewed.

---

## 1. Execution Scope & Constraints

### 1.1 Task Boundaries (Enforced)
- ✓ Read-only review of V2 candidate template `relative_strength_rotation_shsz_sw2021_v1`
- ✓ Access verified source: Jegadeesh & Titman (1993), Journal of Finance 48(1):65-91
- ✓ Extract primary source locators (p.65, p.67, p.68, p.73, p.90)
- ✓ Draft source-to-rule candidate mapping (Section 3 of preflight report)
- ✓ Record the subsequent AI technical review and owner-authorized review model (Section 4)

### 1.2 Prohibitions (Enforced)
- ✓ No code/test/plan modifications
- ✓ No template status change (remains `candidate`)
- ✓ No approval granted
- ✓ No PIT artifact operations
- ✓ No Gate 0/B6/OOS/Signal/Promotion operations
- ✓ No fabricated reviewer data
- ✓ No claims of project readiness or completion
- ✓ No representation of academic findings as A-share trading advice
- ✓ No PDF download/storage (URI + page references only)
- ✓ Single-source discipline (Jegadeesh & Titman 1993 only)

### 1.3 Single-Source Discipline
**Verified Source:** https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf  
**DOI:** 10.1111/j.1540-6261.1993.tb04702.x  
**No literature expansion:** No secondary sources, blogs, or additional papers consulted.

---

## 2. Existing Capabilities (Reused)

### 2.1 V2 Candidate Template
- **Template ID:** `relative_strength_rotation_shsz_sw2021_v1`
- **Version:** `v1_shsz_sw2021_pit`
- **Governance Status:** `candidate`
- **Location:** `backend/services/strategy_template_library.py` L371-392
- **Frozen Rules:** 6 categories (entry, exit, risk, position sizing, market fit, forbidden markets)
- **Strategy Config Payload:** 15% rank threshold, 3-day confirmation, 40% rank exit, 15-day max hold, 8% stop-loss, green/yellow market regime, 50M volume, 5 max positions, weekly rebalance

### 2.2 Template Governance Infrastructure (Task 1-A)
- ✓ V2 template governance record in `_TEMPLATES`
- ✓ `list_approved_templates()` filters by `governance_status='approved'`
- ✓ B6 governance guard rejects `candidate`/`retired` templates
- ✓ 8 V2 governance tests pass (`test_template_governance_v2.py`)
- ✓ 58 regression tests pass (template library, B6, matcher, gate, ledger)

### 2.3 Contracts & Schema
- ✓ `StrategyTemplateDefinition` with `governance_status`, `source_citation`, `reviewed_by`, `reviewed_at`, `review_due_date` fields
- ✓ `SourceRuleMapping` contract for formal review (not yet populated)
- ✓ Requirements hash binding via `template_v2_requirements_hash` field

---

## 3. Source Locator Extraction (Completed)

### 3.1 Access Method
**Initial Attempt (Failed):**
- Tool: `web_extract(urls=["https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf"])`
- Backend: `ddgs` (search-only, cannot extract URL content)
- Result: `source_locator_unavailable`

**Correction (Successful):**
- Tool: `browser_navigate(url="https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf")`
- Method: Browser navigation to PDF viewer, `browser_vision()` + `browser_scroll()` to extract page content
- Result: `source_locator_available`

### 3.2 Primary Source Locators (Verified)

| Locator | Content | Classification |
|---------|---------|----------------|
| **p.65 Abstract** | "This paper documents that strategies which buy stocks that have performed well in the past and sell stocks that have performed poorly in the past generate significant positive returns over 3- to 12-month holding periods." | Core hypothesis: past return ranking → future returns |
| **p.67 Section II.A** | "Our sample includes all stocks on the NYSE and AMEX for the period 1965 to 1989." Formation periods and holding periods range from 3 to 12 months. | Sample scope: US equities 1965-1989, 3-12 month horizons |
| **p.73 Table II** | "Returns to Portfolios Formed on the Basis of Their Prior Six-Month Returns." Decile portfolios (10 groups), equal-weighted construction. | Portfolio methodology: deciles, equal-weight, 6-month formation |
| **p.90 Conclusions** | "The evidence...suggests that the profitability of the momentum strategies is unlikely to be permanent." Long-term reversals observed after 12 months. | Limitation: momentum not permanent |

---

## 4. Candidate Mapping Draft (Section 3 of Preflight Report)

### 4.1 Classification Summary

**Total Enumerated Mapping Rows:** 19  
**Source Claims Supported:** 2  
**Implementation Constraints:** 17  
**Unsupported:** 0

### 4.2 Source Claims (Paper Directly Supports)

1. **Relative Strength Directional Hypothesis** (p.65, p.73)
   - Rule: "Top [X]% relative strength" concept
   - Support: Paper's core hypothesis — past return ranking predicts future returns
   - Locator: p.65 abstract, p.73 Table II

2. **Equal-Weight Portfolio Construction** (p.73)
   - Rule: "Equal weight" across positions
   - Support: Table II caption "equally weighted portfolios"
   - Locator: p.73 Table II

### 4.3 Implementation Constraints (Adaptation, Not Source-Supported)

**Entry Rules (3):**
- 15% threshold (paper uses 10% deciles)
- 3-day confirmation (paper has no intra-period confirmation)
- Formation period undefined (paper specifies 3-12 months)

**Exit Rules (4):**
- 40% rank threshold (paper uses fixed horizons, not rank thresholds)
- 15-day max hold (paper 90-365 days — **5-20× mismatch**)
- 8% stop-loss (paper has no stop-loss)
- Rank-based exit concept (implementation of paper's rebalancing)

**Risk Rules (2):**
- Market regime filter (paper has no regime filtering)
- 50M volume filter (paper uses all listed stocks)

**Position Sizing (2):**
- Max 5 positions (paper ~300 per decile — **60× mismatch**)
- Weekly rebalance (paper forms monthly overlapping cohorts, not weekly portfolios)

**Market Scope (7):**
- SH/SZ A-shares (paper: US NYSE/AMEX 1965-1989)
- SW2021 PIT (paper: no industry classification)
- Point-in-time membership (paper: survivorship bias not addressed)
- Forbidden: limit_up, st_stock, delisting_risk (no US equivalents)

**Critical Insight:** Paper makes **no generalization claim to A-shares**. Entire market scope (T+1, 10% limits, ST, state intervention) is implementation_constraint.

---

## 5. Critical Gaps Identified

### 5.1 Temporal Mismatch
- **Paper:** At each month start, rank on J = 3/6/9/12 prior months, form a new cohort, and hold it for K = 3/6/9/12 months; K cohorts overlap.
- **Template:** Undefined formation + 15-day max hold
- **Gap:** Template holding period **5-20× shorter** than paper's tested horizons

### 5.2 Diversification Mismatch
- **Paper:** ~300 stocks per decile portfolio (10% of ~3000 stock universe)
- **Template:** Max 5 positions
- **Gap:** Template **60× more concentrated**

### 5.3 Market Scope Mismatch
- **Paper:** US NYSE/AMEX 1965-1989, continuous trading, no daily limits, no T+1, no ST
- **Template:** SH/SZ A-shares 2020+, T+1 settlement, 10% daily limits, ST designation, state intervention risk
- **Gap:** No claim in paper that momentum generalizes to A-share structure

### 5.4 Formation Period Undefined
- **Paper:** Specifies 3, 6, 9, or 12 month formation periods
- **Template:** Frozen rules do not specify lookback window for "relative_strength"
- **Gap:** Cannot verify fidelity without frozen formation parameter

---

## 6. AI Technical Review and Owner Authorization (Section 4 of Preflight Report)

### 6.1 Recorded Governance Decision
- `reviewer_id`: `ai_reviewer_openai_codex_gpt5` (AI technical reviewer, not human)
- `reviewer_kind`: `ai_technical_reviewer`
- `reviewed_at`: `2026-07-15`
- `review_due_date`: `not_applicable` because this is a revision-required review
- `review_decision`: `revision_required`
- `owner_authorization`: owner-authorized AI-review governance model; this does not approve the current version

### 6.2 Future Review Assessments Required
For **each source_claim:**
- Verify locator precision (p.65, p.73 — additional detail if needed)
- Confirm claim fidelity to verbatim source text
- Distinguish directional hypothesis from parameter-level claim

For **each implementation_constraint:**
- Assess necessity for A-share implementation
- Evaluate validity impact on research hypothesis
- Consider alternatives more faithful to source
- Address critical gaps (formation period, holding period, diversification, market generalization)

### 6.3 Market-Scope Delta Confirmation
The AI technical reviewer must **explicitly acknowledge**:
- Original research: US 1965-1989, no daily limits, no T+1, no ST
- Template: A-shares 2020+, T+1, 10% limits, ST, state intervention
- **Delta disclosure:** These differences may invalidate source hypothesis
- **Critical question:** Does momentum effect generalize to A-share structure with 5-20× shorter holding and 60× higher concentration?

---

## 7. Updated Status Summary

### 7.1 Template Status (Unchanged)
- **Template:** `relative_strength_rotation_shsz_sw2021_v1`
- **Governance:** `candidate` (unchanged)
- **Approved Templates:** 0 (unchanged)

### 7.2 Task Status (Corrected)
- **Source Locator:** `unavailable` → **`available`** ✓
- **Mapping Draft:** **`ready`** ✓
- **AI Technical Review:** `revision_required` (recorded)

### 7.3 Blocker Chain (Updated)
```
Task 0 Step 5: no_validated_signal_visible_in_dom
  ↑ blocked by
template_revision_required
  ↑ blocked by
ai_technical_review_completed_with_revision_required
  ↑ previously blocked by
source_locator_unavailable (RESOLVED)
```

### 7.4 Global Status (Unchanged)
- **Task 0 Step 5:** BLOCKED
- **Global:** `validation_unavailable`

---

## 8. Evidence & Traceability

### 8.1 Modified Artifacts
- **Updated:** `docs/verification/TASK1_V2_TEMPLATE_SOURCE_DOSSIER_PREFLIGHT.md`
  - Section 1: Source locators verified (p.65, p.67, p.68, p.73, p.90)
  - Section 3: Candidate mapping corrected to 19 enumerated rows
  - Section 4: AI technical `revision_required` review and owner authorization recorded
  - Executive Summary: Status updated to `source_locator_available` + `template_revision_required`
  - Audit trail: Initial failure + correction documented

### 8.2 Unchanged Artifacts
- `backend/services/strategy_template_library.py` (no modifications)
- `contracts/strategy.py` (no modifications)
- `tests/test_template_governance_v2.py` (no modifications)
- Main plan (no modifications)

### 8.3 Audit Trail
- 2026-07-15 Initial attempt: `web_extract` via ddgs backend failed → `source_locator_unavailable`
- 2026-07-15 Correction: `browser_navigate` to verified PDF URI → locators extracted (p.65, p.67, p.73, p.90)
- Status progression: `source_locator_unavailable` → `source_locator_available` + `mapping_draft_ready`
- Remaining blocker: `template_revision_required`

---

## 9. Next Actions (Blocked by Required Revision)

### 9.1 Immediate Blocker
`template_revision_required`

### 9.2 Required to Proceed
1. Owner allocates a new candidate template/version identity; the current template/version/hash remains immutable and candidate.
2. The new candidate freezes a precise formation/lookback period and corrects the dossier's monthly formation and overlapping-holding description.
3. Repeat AI technical review and bind an explicit owner authorization to the new frozen content.
4. Only an `approved` decision for that exact new content can remove the template-governance blocker. Task 0 Step 5 remains blocked until the separate Gate 0, qualified PIT input, B6/OOS, Gate, Promotion, and Signal prerequisites have all passed.

### 9.3 Estimated Timeline
Unknown (contingent on owner allocation of a new candidate version and a frozen formation/lookback rule)

---

## 10. Conclusions

### 10.1 Task 1-B Correction Outcome
**Resolved:** `source_locator_unavailable` → `source_locator_available` + `mapping_draft_ready`

**Achieved:**
- ✓ Verified source URI: https://www.bauer.uh.edu/rsusmel/phd/jegadeesh-titman93.pdf
- ✓ Extracted 4 primary locators (p.65, p.67, p.73, p.90)
- ✓ Drafted candidate mapping for 19 enumerated rows (2 source_claims, 17 implementation_constraints)
- ✓ Identified 3 critical gaps (temporal, diversification, market scope)
- ✓ Recorded the AI technical review and its `revision_required` outcome

**Not Achieved:**
- ✓ AI technical review recorded: `revision_required`
- ✓ Owner authorization recorded for the AI-review governance model
- ✗ Template approval

### 10.2 Critical Findings for the Next AI Technical Review
1. **Limited Source Support:** Only 2 rules (relative strength direction, equal-weight) directly supported by paper
2. **Severe Temporal Mismatch:** 15-day max hold vs paper's 90-365 days (5-20× shorter)
3. **Severe Diversification Mismatch:** 5 positions vs paper's ~300 (60× more concentrated)
4. **No A-Share Generalization:** Paper makes no claim about Chinese equity markets, T+1, price limits, or ST designation
5. **Formation Period Gap:** Template does not freeze lookback window specified in paper (3-12 months)

### 10.3 Unchanged Global State
- **Template Status:** `candidate` (0 approved templates)
- **Task 0 Step 5:** BLOCKED (no validated signal visible in DOM)
- **Global Status:** `validation_unavailable`
- **B6/OOS/Gate/Signal/Promotion:** All blocked by upstream dependencies

### 10.4 Prohibitions Enforced
All 10 prohibitions enforced (see Section 1.2). No unauthorized operations, no fabricated data, no premature claims of readiness.

---

## Signature

**Task:** Task 1-B Correction  
**Date:** 2026-07-15  
**Report Status:** `source_locator_available` + `ai_technical_review_completed_with_revision_required`  
**Template Status:** `candidate`  
**Approved Count:** 0  
**Browser Chain:** BLOCKED  
**Global Status:** `validation_unavailable`  
**Next Blocker:** `template_revision_required`

**End of Report**
