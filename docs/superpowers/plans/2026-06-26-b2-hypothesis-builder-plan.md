# B2 Hypothesis Builder and Deterministic Validation Implementation Plan

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build B 模块阶段二的 Hypothesis Builder、Strategy Template Library、确定性 Validator 和定向 Repair Loop。B2 的目标不是跑回测，而是把 A 模块交付的 `hypothesis_draft` 映射为一个合法、冻结、可审计、不可由 LLM 偷改参数的 `StrategyDraft`。

**Architecture:** B2 在 B1 的 `contracts/strategy.py` 和 `StrategyDB` 之上增加薄控制层。LLM 只选择一个已注册 `strategy_template_id`，系统从模板库确定性生成 strategy config JSON，并通过 validator 校验。任何状态、hash、Gate、OOS、预算、回测报告、成交结果都不在 B2 实现。

**Tech Stack:** Python 3.11、Pydantic v2、SQLite、`unittest`

---

## 0. Scope and fixed decisions

本计划只实现 B2，不实现：

* point-in-time universe 数据构造；
* 历史成分、退市股覆盖、`ann_date` 对齐；
* data snapshot hash；
* OOS window 生成；
* OOS budget、缓存、预留、扣减；
* strategy_core 回测执行；
* Canary；
* Base/Stress cost 回测；
* Controls / benchmark 对照组；
* Prototype Gate 计算；
* API；
* UI；
* C 模块 Signal Board 接入。

固定决定：

1. B2 不修改 A 模块表，不修改 `ResearchDB`。
2. B2 不修改旧 `contracts/stable.py`、`contracts/draft.py`、`contracts/research.py`。
3. B2 不修改旧 `strategy_core/prototype_gate.py`。
4. B2 默认不修改 `contracts/strategy.py`，除非测试证明 B1 契约缺少必要字段；若必须修改，先停下说明原因。
5. B2 只生成 `StrategyDraft.status` 以外的内容。B1 的 `StrategyDraft` 仍不得有 status 字段。
6. B2 不写 `prototype_passed`，不写 Gate，不写报告，不写 lifecycle 之外的状态。
7. B2 不允许 LLM 决定参数。参数只来自代码里的 Strategy Template Library。
8. B2 不允许参数搜索、网格搜索、自动调参、参数扰动、生成多个策略变体后择优。
9. B2 采用 theme-level 单策略：一个 theme / hypothesis 只能生成一个 strategy revision。不得为每个 candidate 单独生成策略。
10. B2 不允许 Evidence 事件进入 entry、exit、risk、rebalance、fill、cost 规则。
11. B2 的 repair loop 最多 2 次，只能修复 validator 明确指出的字段错误，不允许盲重试。
12. `strategy_revision_id` 仍由调用方提供，B2 不自动生成。
13. B2 可以使用 deterministic fake LLM client 做测试；真实 LLM 接入只做边界包装，不作为验收依赖。
14. B2 每个任务后必须 checkpoint commit。
15. 并发上限：B2 单次 Hypothesis Builder run 最多 1 个 LLM 调用；repair loop 串行，总并发不超过 1。系统全局仍不得超过 2。

---

## 1. B2 output contract

B2 成功输出：

```text
HypothesisBuilderResult
  - status = success
  - strategy_revision_id
  - selected_template_id
  - template_selection_reason
  - unmapped_hypothesis_elements
  - strategy_config_json
  - validation_result = pass
  - repair_attempts = 0..2
  - created_strategy_draft
  - initial_lifecycle_state = draft
```

B2 失败输出：

```text
HypothesisBuilderResult
  - status = failed
  - failure_stage = template_selection | validation | repair_exhausted | storage
  - errors
  - raw_llm_output_snapshot
  - validation_errors
  - repair_attempts
  - no_strategy_draft_created
```

B2 不输出：

* buy / sell；
* target price；
* backtest metrics；
* P&L；
* Gate verdict；
* prototype_passed；
* OOS result；
* Signal Board action；
* human promotion decision。

---

## 2. Strategy templates

B2 首批只允许 4 个模板：

```text
theme_momentum_breakout_v1
relative_strength_rotation_v1
volume_breakout_followthrough_v1
trend_pullback_watch_v1
```

每个模板必须由确定性代码定义：

* `template_id`
* `version`
* `template_hash`
* `hypothesis_types`
* `core_entry_rule_id`
* `supported_universe_rule_types`
* `sample_split_rule_ids`
* `benchmark_rule_id`
* `strategy_config_payload`
* `forbidden_fields`
* `forbidden_evidence_terms`
* `default_cost_model`
* `default_fill_model`
* `default_risk_rules`

模板参数由系统固定，用户和 LLM 不得选择。

### 2.1 Fixed default parameter policy

B2 先使用保守固定参数，不做优化。

```yaml
theme_momentum_breakout_v1:
  hypothesis_types:
    - theme_momentum
    - bottleneck_breakout
  entry:
    relative_strength_rank_pct_max: 10
    breakout_lookback_days: 60
    volume_multiple_vs_20d: 1.5
  exit:
    max_holding_days: 10
    close_below_ma_days: 20
    stop_loss_pct: 8
  risk:
    market_regime_allowed:
      - green
      - yellow
    reject_market_regime:
      - red
    min_avg_amount_20d: 50000000
  rebalance:
    frequency: daily
    max_positions: 5

relative_strength_rotation_v1:
  hypothesis_types:
    - relative_strength
    - theme_rotation
  entry:
    relative_strength_rank_pct_max: 15
    confirm_days: 3
  exit:
    rank_exit_pct_min: 40
    max_holding_days: 15
    stop_loss_pct: 8
  risk:
    market_regime_allowed:
      - green
      - yellow
    min_avg_amount_20d: 50000000
  rebalance:
    frequency: weekly
    max_positions: 5

volume_breakout_followthrough_v1:
  hypothesis_types:
    - volume_breakout
    - followthrough
  entry:
    breakout_lookback_days: 40
    volume_multiple_vs_20d: 2.0
    followthrough_days: 2
  exit:
    max_holding_days: 8
    close_below_ma_days: 10
    stop_loss_pct: 7
  risk:
    min_avg_amount_20d: 80000000
    reject_limit_up_entry: true
  rebalance:
    frequency: daily
    max_positions: 4

trend_pullback_watch_v1:
  hypothesis_types:
    - trend_pullback
    - strong_trend_retest
  entry:
    trend_ma_days: 60
    pullback_ma_days: 20
    rebound_confirm_days: 2
  exit:
    max_holding_days: 12
    close_below_ma_days: 20
    stop_loss_pct: 7
  risk:
    min_avg_amount_20d: 50000000
    reject_market_regime:
      - red
  rebalance:
    frequency: daily
    max_positions: 5
```

这些参数不是最终盈利承诺，只是 B2 的模板默认值。后续能否用于实盘，必须经过 B3/B4/B5 的历史数据、时间游标、OOS、成本压力和 Gate 验证。

---

## 3. File map

### Create

* `backend/services/strategy_template_library.py`
* `backend/services/hypothesis_builder.py`
* `backend/services/strategy_config_validator.py`
* `backend/services/hypothesis_repair_loop.py`
* `backend/services/hypothesis_builder_types.py`
* `tests/b2_fixtures.py`
* `tests/test_b2_template_library.py`
* `tests/test_b2_template_selection_contract.py`
* `tests/test_b2_strategy_config_validator.py`
* `tests/test_b2_hypothesis_builder.py`
* `tests/test_b2_repair_loop.py`
* `tests/test_b2_b1_integration.py`
* `tests/test_b2_compatibility.py`

### Modify only if necessary

* `backend/db/strategy.py`

Allowed modification only:

* adding a public method that stores a B2-generated `StrategyTemplateDefinition`, `BacktestUniverseSpec`, and `StrategyDraft` using existing B1 append-only paths;
* adding read helpers needed by B2 tests.

Forbidden modification:

* no status update method;
* no direct prototype promotion method;
* no update/delete behavior;
* no bypass of `StrategyPromotionReducer`.

### Do not modify

* `contracts/stable.py`
* `contracts/draft.py`
* `contracts/research.py`
* `backend/db/research.py`
* `strategy_core/prototype_gate.py`
* B1 tests except adding compatibility assertions if needed.

---

## 4. Checkpoint commits

Before B2 starts, verify baseline:

```powershell
git status --short
git log --oneline -1
```

Expected: clean working tree with baseline B1 commit.

After each task:

```powershell
git status --short
.venv\Scripts\python.exe -m unittest <focused_test> -v
git add <exact files>
git commit -m "<message>"
```

Commit map:

| Task | Files                                                                                                  | Commit                                          |
| ---- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| 1    | `backend/services/strategy_template_library.py tests/b2_fixtures.py tests/test_b2_template_library.py` | `feat: add B2 strategy template library`        |
| 2    | `backend/services/hypothesis_builder_types.py tests/test_b2_template_selection_contract.py`            | `test: lock B2 LLM template selection boundary` |
| 3    | `backend/services/strategy_config_validator.py tests/test_b2_strategy_config_validator.py`             | `feat: add deterministic B2 strategy validator` |
| 4    | `backend/services/hypothesis_builder.py tests/test_b2_hypothesis_builder.py`                           | `feat: add B2 hypothesis builder`               |
| 5    | `backend/services/hypothesis_repair_loop.py tests/test_b2_repair_loop.py`                              | `feat: add bounded B2 repair loop`              |
| 6    | `backend/db/strategy.py tests/test_b2_b1_integration.py`                                               | `test: integrate B2 builder with B1 storage`    |
| 7    | `tests/test_b2_compatibility.py`                                                                       | `test: protect B2 compatibility boundaries`     |
| 8    | docs/status only if requested                                                                          | `docs: record B2 verification`                  |

If git is unavailable, stop. Do not continue B2 without git.

---

## Task 1: Strategy Template Library

**Files:**

* Create: `backend/services/strategy_template_library.py`
* Create: `tests/b2_fixtures.py`
* Create: `tests/test_b2_template_library.py`

### Step 1: Write failing tests

Tests must prove:

* exactly four templates exist;
* template IDs match allowed list;
* every template has non-empty version/hash;
* every template has deterministic payload;
* reloading the library gives the same hash;
* template lookup rejects unknown template IDs;
* no runtime template creation API exists;
* each template maps to a B1 `StrategyTemplateDefinition`.

Required test names:

```python
test_library_contains_exactly_four_templates
test_template_hash_is_stable
test_unknown_template_id_rejected
test_no_runtime_template_creation_method
test_templates_convert_to_b1_template_definition
test_each_template_has_core_entry_rule
```

### Step 2: Verify RED

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_template_library -v
```

Expected: import failure.

### Step 3: Implement

Implement:

```python
class StrategyTemplate:
    ...

class StrategyTemplateLibrary:
    def list_templates(self) -> tuple[StrategyTemplate, ...]: ...
    def get_template(self, template_id: str) -> StrategyTemplate: ...
    def to_b1_definition(self, template_id: str) -> StrategyTemplateDefinition: ...
```

Rules:

* templates are hard-coded constants;
* no `add_template`;
* no `update_template`;
* no mutation after construction;
* template hash is computed from canonical JSON;
* hash excludes created_at and runtime metadata;
* hash includes all strategy semantics.

### Step 4: Verify GREEN

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_template_library -v
```

### Step 5: Checkpoint

Commit exact files.

---

## Task 2: LLM template selection contract

**Files:**

* Create: `backend/services/hypothesis_builder_types.py`
* Create: `tests/test_b2_template_selection_contract.py`

### Step 1: Write failing tests

LLM output is allowed to contain only:

```text
strategy_template_id
template_selection_reason
unmapped_hypothesis_elements
```

Tests must prove:

* valid output parses;
* output with entry params is rejected;
* output with exit params is rejected;
* output with risk params is rejected;
* output with status is rejected;
* output with hash is rejected;
* output with Gate verdict is rejected;
* output with OOS start/end is rejected;
* output with multiple templates is rejected;
* unknown template ID is rejected by builder boundary.

Required test names:

```python
test_llm_selection_accepts_only_template_id_reason_and_unmapped_elements
test_llm_selection_rejects_entry_parameters
test_llm_selection_rejects_exit_parameters
test_llm_selection_rejects_risk_parameters
test_llm_selection_rejects_status_hash_gate_and_budget_fields
test_llm_selection_rejects_oos_dates
test_llm_selection_rejects_multiple_templates
```

### Step 2: Verify RED

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_template_selection_contract -v
```

### Step 3: Implement

Implement frozen Pydantic models:

```python
class HypothesisBuilderInput(BaseModel):
    theme_id: str
    hypothesis_id: str
    hypothesis_source_snapshot_id: str
    hypothesis_type: str
    hypothesis_text: str
    rule_candidates: dict
    evidence_summary: dict | None
    backtest_universe_spec: BacktestUniverseSpec
    strategy_revision_id: str

class LLMTemplateSelection(BaseModel):
    strategy_template_id: str
    template_selection_reason: str
    unmapped_hypothesis_elements: tuple[str, ...] = ()
```

Rules:

* `extra="forbid"`;
* frozen models;
* non-empty string validation;
* `strategy_revision_id` is required and not generated;
* `backtest_universe_spec` must be `BacktestUniverseSpec`.

### Step 4: Verify GREEN

Run focused tests.

### Step 5: Checkpoint

Commit exact files.

---

## Task 3: Deterministic strategy config validator

**Files:**

* Create: `backend/services/strategy_config_validator.py`
* Create: `tests/test_b2_strategy_config_validator.py`

### Step 1: Write failing tests

Validator must reject:

* unknown template ID;
* template hash mismatch;
* template version mismatch;
* any parameter different from registered template;
* missing entry;
* missing exit;
* missing risk;
* missing fill model;
* missing cost model;
* missing sample split rule;
* `ForwardWatchlistSnapshot`;
* plain symbol list universe;
* Evidence terms in entry/exit/risk;
* announcement keywords in entry/exit/risk;
* order/customer/certification terms in entry/exit/risk;
* unsupported fundamental triggers;
* multiple variants;
* parameter search fields;
* OOS start/end;
* status/hash/Gate/budget fields;
* user-supplied benchmark override;
* user-supplied cost override.

Validator must accept:

* exact config generated from template;
* exact config with only non-semantic display fields outside strategy_config_json excluded before validation.

Required test names:

```python
test_valid_template_config_passes
test_rejects_unknown_template
test_rejects_template_hash_mismatch
test_rejects_modified_template_parameter
test_rejects_missing_entry_exit_risk
test_rejects_forward_watchlist_universe
test_rejects_plain_symbol_list_universe
test_rejects_evidence_event_terms_in_trade_rules
test_rejects_parameter_search_and_variants
test_rejects_status_hash_gate_budget_fields
test_rejects_oos_dates
test_rejects_user_cost_or_benchmark_override
```

### Step 2: Verify RED

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_strategy_config_validator -v
```

### Step 3: Implement

Implement:

```python
class StrategyValidationError(BaseModel):
    code: str
    field_path: str
    message: str
    repairable: bool

class StrategyValidationResult(BaseModel):
    status: Literal["pass", "fail"]
    errors: tuple[StrategyValidationError, ...]

class StrategyConfigValidator:
    def validate(self, config: dict, template: StrategyTemplate) -> StrategyValidationResult: ...
```

Forbidden terms list:

```python
EVIDENCE_EVENT_TERMS = (
    "announcement",
    "announcements",
    "公告",
    "订单",
    "客户认证",
    "中标",
    "合同",
    "互动易",
    "问询函",
    "业绩预告",
    "减持",
    "pledge",
    "revenue_purity",
    "customer_certification",
)
```

Rules:

* exact template semantic payload match;
* no config mutation inside validator;
* validation returns structured errors, not free text only;
* no LLM call inside validator;
* no database write inside validator.

### Step 4: Verify GREEN

Run focused tests.

### Step 5: Checkpoint

Commit exact files.

---

## Task 4: Hypothesis Builder main service

**Files:**

* Create: `backend/services/hypothesis_builder.py`
* Create: `tests/test_b2_hypothesis_builder.py`

### Step 1: Write failing tests

Tests must prove:

* builder calls LLM once in normal path;
* LLM only selects template;
* system generates config from template;
* user does not provide parameters;
* builder creates frozen `StrategyDraft`;
* draft has no status;
* builder creates initial `StrategyLifecycleState(state="draft")`;
* builder does not write DB unless explicitly given a storage call;
* builder rejects candidate-level strategy creation;
* builder rejects multiple template selection;
* builder rejects forward watchlist input;
* builder preserves unmapped hypothesis elements as notes only;
* evidence summary is stored as background only, not trade rules;
* rerun with same input requires a new caller-provided `strategy_revision_id`.

Required test names:

```python
test_builder_normal_path_uses_one_llm_call
test_builder_generates_config_from_template_not_llm_params
test_builder_creates_frozen_strategy_draft_without_status
test_builder_creates_initial_draft_lifecycle_state
test_builder_rejects_candidate_level_strategy
test_builder_rejects_multiple_template_selection
test_builder_rejects_forward_watchlist_input
test_evidence_summary_cannot_enter_trade_rules
test_rerun_requires_new_strategy_revision_id
```

### Step 2: Verify RED

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_hypothesis_builder -v
```

### Step 3: Implement

Implement:

```python
class HypothesisBuilder:
    def __init__(
        self,
        template_library: StrategyTemplateLibrary,
        validator: StrategyConfigValidator,
        llm_client: TemplateSelectionClient,
    ): ...

    def build(self, input: HypothesisBuilderInput) -> HypothesisBuilderResult: ...
```

Rules:

* LLM client returns `LLMTemplateSelection`;
* builder checks template exists;
* builder generates config from template;
* builder validates generated config;
* builder converts config to canonical JSON string;
* builder creates `StrategyDraft`;
* builder creates initial `StrategyLifecycleState`;
* builder does not store unless called by integration service;
* if validation fails, return failure result, no draft;
* no status, no Gate, no report, no promotion.

### Step 4: Verify GREEN

Run focused tests.

### Step 5: Checkpoint

Commit exact files.

---

## Task 5: Bounded repair loop

**Files:**

* Create: `backend/services/hypothesis_repair_loop.py`
* Create: `tests/test_b2_repair_loop.py`

### Step 1: Write failing tests

Repair loop must prove:

* no repair when validation passes;
* repair called only with structured validation errors;
* max repairs = 2;
* each repair re-runs full deterministic validation;
* successful repair returns a draft;
* failed repair returns `repair_exhausted`;
* repair cannot modify template parameters;
* repair cannot introduce Evidence event rules;
* repair cannot write status/hash/Gate/budget;
* repair does not consume OOS budget;
* repair does not write DB until final validation passes;
* repeated same invalid output after 2 repairs stops.

Required test names:

```python
test_no_repair_when_validation_passes
test_repair_receives_structured_errors
test_repair_stops_after_two_attempts
test_repair_reruns_full_validator_each_time
test_successful_repair_returns_valid_draft
test_repair_exhausted_returns_failure_without_draft
test_repair_cannot_modify_template_parameters
test_repair_cannot_introduce_evidence_rules
test_repair_cannot_write_status_hash_gate_or_budget
```

### Step 2: Verify RED

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_repair_loop -v
```

### Step 3: Implement

Implement:

```python
class HypothesisRepairLoop:
    max_repairs = 2

    def run(self, input: HypothesisBuilderInput) -> HypothesisBuilderResult: ...
```

Rules:

* repair prompt receives only:

  * original allowed LLM selection fields;
  * validator errors;
  * allowed template IDs;
* repair output schema is still `LLMTemplateSelection`;
* no free-form strategy config from repair;
* no blind retry;
* no parallel LLM calls;
* store raw failed outputs for audit in result object.

### Step 4: Verify GREEN

Run focused tests.

### Step 5: Checkpoint

Commit exact files.

---

## Task 6: B1 storage integration

**Files:**

* Modify only if needed: `backend/db/strategy.py`
* Create: `tests/test_b2_b1_integration.py`

### Step 1: Write failing tests

Integration tests must prove:

* B2 stores template definition through B1 append-only table;
* B2 stores formal `BacktestUniverseSpec`;
* B2 stores `StrategyDraft`;
* B2 stores initial lifecycle `draft`;
* B2 cannot mutate draft after creation;
* B2 cannot overwrite existing revision;
* B2 cannot write `prototype_passed`;
* B2 cannot bypass reducer;
* B2 cannot update status because status does not exist;
* failed validation creates no draft row.

Required test names:

```python
test_b2_success_stores_strategy_draft_and_initial_lifecycle
test_b2_failed_validation_stores_nothing
test_b2_cannot_overwrite_existing_strategy_revision
test_b2_cannot_write_prototype_passed
test_b2_storage_uses_append_only_b1_paths
```

### Step 2: Verify RED

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_b1_integration -v
```

### Step 3: Implement minimal integration

Allowed:

```python
class HypothesisBuilderStorage:
    def save_successful_builder_result(self, result: HypothesisBuilderResult) -> None: ...
```

Rules:

* only saves success result;
* one SQLite transaction where practical;
* uses existing `StrategyDB` insert methods;
* no update/delete;
* duplicate revision fails loudly;
* failed result does not write partial records.

### Step 4: Verify GREEN

Run focused tests.

### Step 5: Checkpoint

Commit exact files.

---

## Task 7: Compatibility and boundary tests

**Files:**

* Create: `tests/test_b2_compatibility.py`

### Step 1: Write tests

Tests must prove:

* B2 did not modify A contracts;
* B2 did not modify old stable contracts behavior;
* B2 did not modify old prototype gate behavior;
* B2 did not require frontend changes;
* B2 does not import ResearchDB directly;
* B2 does not import old `UniverseConfig`;
* B2 does not add any public status update method to `StrategyDB`;
* B2 does not call strategy_core for backtest execution;
* B2 does not create OOS reports or Gate results.

Suggested checks:

```python
test_b2_does_not_import_research_db
test_b2_does_not_import_old_universe_config
test_b2_does_not_modify_old_prototype_gate
test_b2_strategy_db_has_no_status_update_method
test_b2_does_not_create_gate_or_report
test_b2_does_not_call_strategy_core_backtest
```

### Step 2: Run

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_compatibility -v
```

### Step 3: Checkpoint

Commit exact files.

---

## Task 8: Final verification

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b2_template_library -v
.venv\Scripts\python.exe -m unittest tests.test_b2_template_selection_contract -v
.venv\Scripts\python.exe -m unittest tests.test_b2_strategy_config_validator -v
.venv\Scripts\python.exe -m unittest tests.test_b2_hypothesis_builder -v
.venv\Scripts\python.exe -m unittest tests.test_b2_repair_loop -v
.venv\Scripts\python.exe -m unittest tests.test_b2_b1_integration -v
.venv\Scripts\python.exe -m unittest tests.test_b2_compatibility -v
.venv\Scripts\python.exe -m pytest tests/ -x --tb=short -q
node_modules\.bin\tsc.cmd -p frontend --noEmit
```

If TypeScript command fails in WSL path mode, use the already documented node direct form and record exact command:

```powershell
node node_modules\typescript\lib\tsc.js -p frontend --noEmit
```

---

## 9. Acceptance criteria

B2 can be accepted only if all are true:

1. Exactly four templates are registered.
2. Template hashes are deterministic.
3. No runtime template creation or mutation API exists.
4. LLM output schema allows only template ID, selection reason, unmapped elements.
5. LLM cannot output entry/exit/risk parameters.
6. LLM cannot output status, hash, Gate, budget, OOS date, report, or promotion.
7. Builder uses exactly one LLM call in normal path.
8. Repair loop uses at most two sequential repair attempts.
9. Validator rejects Evidence event terms in trading rules.
10. Validator rejects parameter search and multiple variants.
11. Validator rejects forward watchlist and symbol list as formal universe.
12. StrategyDraft is frozen and has no status.
13. Rerun requires a new caller-provided `strategy_revision_id`.
14. Failed validation stores no draft.
15. Successful build stores draft + initial lifecycle only.
16. No `prototype_passed` path exists outside reducer.
17. A module, old stable contracts, old prototype gate remain unaffected.
18. Full Python suite passes.
19. Frontend type check passes.
20. Git working tree is clean after final commit.

---

## 10. Evidence package for handoff

After B2 implementation, reply with:

```text
B2 implementation evidence:

1. Git
- git log --oneline -8
- git status --short

2. Files
- created files:
- modified files:
- forbidden files modified: yes/no

3. Focused tests
- test_b2_template_library:
- test_b2_template_selection_contract:
- test_b2_strategy_config_validator:
- test_b2_hypothesis_builder:
- test_b2_repair_loop:
- test_b2_b1_integration:
- test_b2_compatibility:

4. Full tests
- pytest:
- frontend typecheck:

5. Key boundary proof
- LLM only selects template:
- LLM cannot set parameters:
- Evidence events rejected:
- multiple variants rejected:
- forward watchlist rejected:
- failed validation stores nothing:
- reducer remains only prototype_passed path:

6. Recommendation
- enter B3: yes/no
- unresolved risks:
```

---

## 11. Stop conditions

Stop and report before continuing if any of these happen:

* B2 needs to modify B1 contracts materially;
* B2 needs to modify `strategy_core` to pass tests;
* B2 needs to change A module storage;
* B2 needs to create OOS/Gate/report code;
* B2 needs user to choose technical parameters;
* LLM output cannot be restricted to template selection;
* validator has to accept Evidence events in trading rules;
* repair loop requires more than 2 attempts;
* full tests fail outside expected new failing tests;
* git working tree is dirty in unexpected files.

---

## 12. Cost and concurrency note

B2 normal path uses 1 LLM call.

B2 repair path uses at most 3 total LLM calls: initial selection + 2 repairs.

All calls are sequential. No parallel LLM calls are needed. This stays below the project concurrency cap of 2 and avoids multi-agent agreement illusion.

Most B2 logic is deterministic Python. LLM is only a classifier from hypothesis text to registered template ID.
