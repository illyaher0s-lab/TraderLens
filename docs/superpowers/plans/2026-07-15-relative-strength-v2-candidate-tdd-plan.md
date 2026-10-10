# Relative Strength V2 Candidate Definition and TDD Plan

> **Subordinate plan:** [`2026-07-10-credible-manual-trading-decision-closure-plan.md`](2026-07-10-credible-manual-trading-decision-closure-plan.md) remains the only main-chain anchor. This plan implements only Task 1 candidate definition work.

**Goal:** Define `relative_strength_rotation_shsz_sw2021_v2` as a deterministic, non-executable candidate with a new template hash and a new declared data-requirements hash.

**Architecture:** Add one new immutable library template and one pure requirements-definition/hash helper. The candidate configuration carries every owner-frozen ranking rule, including its shared hypothesis-family identifier. It does not read market partitions, create qualification or coverage artifacts, or execute a scorer; score execution belongs to later Task 3 after qualified inputs exist.

**Tech stack:** Existing Pydantic template contracts, `hashlib`/canonical JSON, pytest. No new dependency, database, API, page, data scan, or runtime workflow.

**Authorization boundary:** The owner authorized this definition and TDD plan only. The old V1 template/version/hash and its qualification, coverage, and successor artifacts remain byte-for-byte unchanged. The new template remains `candidate`; no B6/OOS/Gate/Promotion/Signal, OOS reserve/consume, data collection, data scan, qualification, or coverage rebuild is allowed. Any later approval requires AI technical approval plus explicit owner authorization for the same frozen content.

---

## Frozen candidate definition

| Field | Frozen value |
|---|---|
| `template_id` | `relative_strength_rotation_shsz_sw2021_v2` |
| `version` | `v2_shsz_sw2021_pit_12m` |
| `governance_status` | `candidate` |
| `hypothesis_family_id` | `relative_strength_rotation_shsz_sw2021` |
| universe | Formal SW2021 PIT membership, SH/SZ; whole eligible cross-section; no industry-neutral claim or industry-control algorithm |
| `as_of_date` | Latest fully closed day on which SH and SZ are both open |
| execution date | Next eligible execution day after `as_of_date` |
| lookback | `lookback_trading_days = 252` and `minimum_history_trading_days = 252`; no calendar-month conversion, shortening, fallback, or new-listing substitute |
| price | `adjusted_close = close * adj_factor`; both rows must be from the same PIT snapshot and no later than their own `as_of_date` |
| score | `adjusted_close(d) / adjusted_close(s) - 1`, where `s` is the 252nd preceding completed common trading day |
| unavailable | Missing either endpoint makes that security unavailable for that date; never fill, substitute raw return, or alter the window |
| rank | Descending score, `symbol` ascending tie-break; top count is `ceil(0.15 * N)` |
| confirmation | A security is in each independently computed top-15% set for `d`, preceding common day, and second-preceding common day; each day uses its own PIT membership and 252-day input window |
| legacy strategy rules | Keep the frozen exit/risk/position constraints only as implementation constraints; do not claim J&T supports them |

The new template's `strategy_config_payload` must serialize the above values explicitly. It must include `hypothesis_family_id` inside that payload so it is covered by the new candidate's `frozen_template_hash`; no V1 hash or artifact is modified. Later Task 4 must consume this identifier when enforcing the shared OOS budget.

The new pure `data_requirements` declaration must name at least `daily.close`, `adj_factor.adj_factor`, the common SH/SZ trading calendar, and formal SW2021 PIT membership, plus their as-of/PIT and unavailable semantics above. Its canonical JSON includes the exact template ID, version, frozen template hash, 252-day rule, rank rule, confirmation rule, membership scope, and required columns. It excludes wall-clock time, paths, temporary names, machine data, and qualification/coverage artifact IDs. It therefore differs from the V1 requirements hash without reading or modifying data.

## Acceptance criteria

- V1 template ID/version/hash and all protected V1 PIT artifacts are unchanged.
- V2 exists exactly once with the frozen fields above and a deterministic new `frozen_template_hash`.
- Candidate conversion is `candidate`; `list_approved_templates()` excludes it; B6 blocks it before any OOS reservation.
- New requirements JSON/hash is deterministic, differs from V1, and cannot reuse V1 qualification, coverage, or successor bindings.
- Tests exercise only in-memory values and manifest metadata/hash checks; no business parquet content, vendor client, database write, protocol, OOS, Gate, Promotion, or Signal call occurs.

## Task 1: Add RED tests for the immutable definition

**Files:**
- Create: `tests/test_relative_strength_v2_candidate.py`
- Read only: `backend/services/strategy_template_library.py`, `contracts/strategy.py`, `tests/test_template_governance_v2.py`, `tests/test_shsz_v2_qualification.py`

- [ ] Write tests that assert the V2 lookup initially returns `None`, then after implementation returns exactly the owner-assigned ID/version and `candidate` governance.
- [ ] Assert the config contains this exact shape:

```python
entry = template.strategy_config_payload["entry"]
assert entry == {
    "relative_strength_rank_pct_max": 15,
    "confirm_days": 3,
    "lookback_trading_days": 252,
    "minimum_history_trading_days": 252,
    "score": "close_times_adj_factor_ratio_minus_one",
    "rank_order": "momentum_desc_symbol_asc",
    "top_count": "ceil_15pct_of_eligible_universe",
}
assert template.strategy_config_payload["hypothesis_family_id"] == "relative_strength_rotation_shsz_sw2021"
assert template.strategy_config_payload["universe"] == {
    "membership": "formal_sw2021_pit",
    "markets": ("SH", "SZ"),
    "ranking_scope": "whole_eligible_cross_section",
    "industry_neutral": False,
}
```

- [ ] Add assertions for exact as-of, endpoint-unavailable, and three-day-confirmation semantics as canonical strings/dicts in the payload; require `market_fit` to say `SW2021 PIT membership universe` and not contain `industry control group`.
- [ ] Add a regression assertion that V1's ID/version/frozen hash equal their pre-task values and V1 keeps `minimum_history_trading_days == 0`.
- [ ] Run RED:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_relative_strength_v2_candidate.py -q
```

Expected: non-zero exit because the V2 candidate does not exist yet.

## Task 2: Define the pure V2 requirements hash before any data access

**Files:**
- Modify: `backend/services/strategy_template_library.py`
- Modify: `tests/test_relative_strength_v2_candidate.py`

- [ ] Add pure module-level helpers `get_template_data_requirements(template) -> dict` and `get_template_data_requirements_hash(template) -> str` for this candidate. Do not call `_load_v2_requirements_hash()`: that helper is explicitly V1-bound to the old successor and coverage manifests.
- [ ] Make `get_template_data_requirements_hash()` serialize the declaration with `sort_keys=True`, compact separators, and UTF-8, returning the full SHA-256 hash.
- [ ] Write RED tests proving:

```python
first = get_template_data_requirements_hash(v2)
second = get_template_data_requirements_hash(v2)
assert first == second
assert first != v1_frozen_definition.data_requirements_hash
assert "data/pit" not in json.dumps(get_template_data_requirements(v2))
```

- [ ] Run the focused RED test and confirm it fails because the helper is absent.
- [ ] Implement only the pure declaration/hash helper. Do not open parquet files or manifests, invoke a scanner, or write an artifact.
- [ ] Run GREEN:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_relative_strength_v2_candidate.py -q
```

Expected: all candidate-definition and requirements-hash tests pass.

## Task 3: Add the V2 library candidate and governance binding

**Files:**
- Modify: `backend/services/strategy_template_library.py`
- Modify: `tests/test_relative_strength_v2_candidate.py`
- Modify: `tests/test_template_governance_v2.py`

- [ ] Add exactly one `StrategyTemplate` using the frozen definition above. Its `validation_gate_profile` stays `standard`; this candidate must not claim `b6_coverage_bound` or bind V1 qualification/coverage/successor artifacts.
- [ ] Add a candidate governance-map record using the existing J&T DOI, the existing market-scope disclosure corrected for the monthly J/K overlapping-cohort method, and no approval evidence. It remains `candidate` because the owner-recorded AI review is `revision_required`.
- [ ] Make `convert_to_frozen_contract()` attach the new pure data-requirements hash for V2 only. Do not alter V1's `_load_v2_requirements_hash()` branch or V1 manifest bindings.
- [ ] Add RED tests that `convert_to_frozen_contract(v2, ...)` exposes the new hash, stays candidate, and produces the same governance hash for distinct `created_at` timestamps.
- [ ] Add GREEN tests that `list_approved_templates()` excludes V2 and an actual `B6ValidationFlow.run_minimal_validation()` call with V2 returns blocked before fake-ledger `reserve_oos_draw()` is called.
- [ ] Run separately:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_relative_strength_v2_candidate.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_template_governance_v2.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_b6_validation_flow.py -q
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_b2_template_library.py -q
```

Expected: each command exits 0. Report exact pass/fail counts and any warnings; do not describe failures as pre-existing without a task-start baseline.

## Task 4: Verify non-inheritance and protected artifacts

**Files:**
- Modify: `tests/test_relative_strength_v2_candidate.py`
- Read only: V1 qualification, coverage, successor manifests and protected hashes

- [ ] Capture SHA-256 before and after for the V1 qualification manifest, V1 coverage manifest, V1 successor manifest, and their referenced parquet files.
- [ ] Add tests that V2's requirements hash differs from V1's and monkeypatch `_load_v2_requirements_hash()` to raise if called while converting V2; V2 conversion must still succeed as a candidate.
- [ ] Assert that no V2 qualification, coverage, or successor directory is created and that the candidate conversion exposes no legacy artifact ID/hash field. Do not invent or persist a qualification artifact.
- [ ] Run the full focused matrix from Task 3 plus:

```powershell
.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_shsz_v2_qualification.py -q
```

- [ ] Verify protected hashes with a read-only command and report any difference as a structural failure. Do not retry by overwriting artifacts.

## Deferred work and explicit stops

- A pure scorer, PIT membership traversal, common-calendar resolution, `close * adj_factor` reads, unavailable-mask construction, T+1 fills, and ranking execution belong to Task 3 and require separately authorized qualified inputs.
- New qualification, new coverage, successor publication, market-guard qualification, B6/OOS, Gate, Promotion, Signal, and OOS-budget enforcement are not part of this plan.
- The new candidate receives no approval from this owner definition. It needs a later attributable AI approval and explicit owner authorization for its exact frozen hash; `revision_required` on V1 never transfers.
- Do not create a worktree, commit, reset, checkout, restore, or delete anything in the shared dirty worktree.
