# B1 Contracts and Immutable Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build B 模块阶段一的类型边界、追加式存储和唯一人工晋升路径，同时保持 A 模块与现有 `strategy_core` 契约不变。

**Architecture:** 新增独立的 `contracts/strategy.py` 与 `StrategyDB`，不修改 `contracts/stable.py` 或 `ResearchDB`。策略内容、协议、报告、Gate、确认和晋升均以 append-only 记录保存；策略当前状态由追加式 `StrategyLifecycleState` 记录推导，不修改冻结的 `StrategyDraft`。`StrategyPromotionReducer` 在单个 SQLite 事务中消费人工确认、写晋升记录并追加新的生命周期状态。

**Tech Stack:** Python 3.11、Pydantic v2、SQLite、`unittest`

---

## 0. Scope and fixed decisions

本计划只实现 B1，不实现：

- 策略模板具体内容；
- Hypothesis Builder 或 LLM 调用；
- point-in-time universe 数据构造；
- OOS 窗口生成；
- OOS budget 预留、扣减或缓存算法；
- 回测、Canary 或 Gate 计算；
- API 和 C 模块。

固定决定：

1. 不修改 `contracts/stable.py`、`contracts/draft.py`、`contracts/research.py`。
2. 不修改 `backend/db/research.py` 和 A 模块表。
3. 新契约放在 `contracts/strategy.py`，暂不从 `contracts/__init__.py` 顶层重导出，调用方必须显式导入版本化 B 契约。
4. `BacktestUniverseSpec` 与旧 `UniverseConfig` 无继承、无包含、无转换关系。
5. `strategy_revision_id` 是调用方提供的非空 opaque ID；B1 不负责生成。
6. `StrategyDraft` 永久冻结且永远不修改状态。
7. 生命周期使用 append-only `StrategyLifecycleState`；初始状态为 `draft`，晋升时追加 `prototype_passed` 状态。
8. Gate 使用独立 `PrototypeGateResultV2`；旧 `PrototypeGateResult` 保持原样。
9. 所有 B1 内容表通过 SQLite trigger 拒绝 `UPDATE` 和 `DELETE`。
10. `StrategyPromotionReducer` 是应用层唯一晋升入口；数据库 trigger 还要求 `prototype_passed` lifecycle 记录必须有匹配的 promotion 和 confirmation consumption。

## 1. File map

### Create

- `contracts/strategy.py` — B1 版本化冻结契约。
- `backend/db/strategy.py` — 独立 StrategyDB、append-only schema 和读取/写入方法。
- `backend/services/strategy_promotion_reducer.py` — 人工同步晋升的唯一服务入口。
- `tests/b1_fixtures.py` — B1 测试对象工厂，减少测试重复。
- `tests/test_b1_contracts.py` — 契约、冻结性和类型边界。
- `tests/test_b1_strategy_db.py` — schema、round-trip、append-only trigger。
- `tests/test_b1_universe_admission.py` — 正式回测 universe admission 边界。
- `tests/test_b1_promotion_reducer.py` — 原子晋升、幂等和拒绝路径。
- `tests/test_b1_compatibility.py` — A 模块与 stable contracts 无回归。

### Do not modify

- `contracts/stable.py`
- `contracts/draft.py`
- `contracts/research.py`
- `backend/db/research.py`
- `strategy_core/prototype_gate.py`

### Checkpoint commits

After each task, first run:

```powershell
git rev-parse --is-inside-work-tree
```

If it returns `true`, create these commits:

| Task | Files | Commit |
|---|---|---|
| 1 | `contracts/strategy.py tests/b1_fixtures.py tests/test_b1_contracts.py` | `git commit -m "feat: add frozen B1 strategy contracts"` |
| 2 | `contracts/strategy.py tests/test_b1_universe_admission.py` | `git commit -m "test: enforce formal backtest universe boundary"` |
| 3 | `backend/db/strategy.py tests/test_b1_strategy_db.py` | `git commit -m "feat: add append-only strategy database"` |
| 4 | `backend/db/strategy.py tests/test_b1_strategy_db.py` | `git commit -m "feat: add typed strategy database reads"` |
| 5 | `backend/db/strategy.py tests/test_b1_strategy_db.py` | `git commit -m "test: lock prototype promotion storage path"` |
| 6 | `backend/db/strategy.py backend/services/strategy_promotion_reducer.py tests/test_b1_promotion_reducer.py` | `git commit -m "feat: add atomic strategy promotion reducer"` |
| 7 | `tests/test_b1_compatibility.py` | `git commit -m "test: protect A module and stable contract compatibility"` |
| 8 | no new files | no commit; record verification output |

Run `git add` with exactly the files listed before each commit. If Git metadata is unavailable, do not initialize a repository; record a named checkpoint with the same task number and test output.

---

## Task 1: Define frozen B1 contracts

**Files:**

- Create: `contracts/strategy.py`
- Create: `tests/b1_fixtures.py`
- Create: `tests/test_b1_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Create `tests/test_b1_contracts.py`:

```python
import unittest
from datetime import date, datetime

from pydantic import ValidationError

from tests.b1_fixtures import (
    make_backtest_universe,
    make_forward_watchlist,
    make_gate_result,
    make_protocol_snapshot,
    make_strategy_draft,
    make_template_definition,
)


class TestB1FrozenContracts(unittest.TestCase):
    def test_template_definition_is_frozen(self):
        template = make_template_definition()
        with self.assertRaises(ValidationError):
            template.version = "v2"

    def test_strategy_draft_is_frozen_and_stays_draft_content(self):
        draft = make_strategy_draft()
        self.assertFalse(hasattr(draft, "status"))
        with self.assertRaises(ValidationError):
            draft.strategy_template_id = "another_template"

    def test_protocol_requires_all_three_hashes(self):
        data = make_protocol_snapshot().model_dump()
        data["strategy_config_hash"] = ""
        with self.assertRaisesRegex(ValidationError, "strategy_config_hash"):
            type(make_protocol_snapshot()).model_validate(data)

    def test_gate_v2_rejects_prototype_passed_verdict(self):
        data = make_gate_result().model_dump()
        data["verdict"] = "prototype_passed"
        with self.assertRaises(ValidationError):
            type(make_gate_result()).model_validate(data)

    def test_universe_types_are_not_convertible(self):
        watchlist = make_forward_watchlist()
        with self.assertRaises(ValidationError):
            type(make_backtest_universe()).model_validate(watchlist.model_dump())

    def test_revision_id_is_required_but_not_generated(self):
        data = make_strategy_draft().model_dump()
        data["strategy_revision_id"] = ""
        with self.assertRaisesRegex(ValidationError, "strategy_revision_id"):
            type(make_strategy_draft()).model_validate(data)


if __name__ == "__main__":
    unittest.main()
```

Create `tests/b1_fixtures.py`:

```python
from datetime import date, datetime

from contracts.strategy import (
    BacktestUniverseSpec,
    ForwardWatchlistSnapshot,
    HumanPromotionConfirmation,
    ImmutableBacktestReport,
    OOSEvaluationLedger,
    PrototypeGateResultV2,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    StrategyTemplateDefinition,
)


NOW = datetime(2026, 6, 26, 9, 0, 0)


def make_template_definition() -> StrategyTemplateDefinition:
    return StrategyTemplateDefinition(
        template_id="theme_momentum_breakout_v1",
        version="v1",
        template_hash="template_hash_001",
        hypothesis_types=("theme_momentum",),
        core_entry_rule_id="breakout_entry",
        supported_universe_rule_types=("sector_plus_tags",),
        sample_split_rule_ids=("fixed_ratio_70_30",),
        benchmark_rule_id="theme_then_industry_then_equal_weight",
        created_at=NOW,
        frozen=True,
    )


def make_backtest_universe() -> BacktestUniverseSpec:
    return BacktestUniverseSpec(
        universe_spec_id="universe_001",
        universe_rule_type="sector_plus_tags",
        sector="electrical_equipment",
        chain_layer_tags=("battery",),
        membership_source="tushare_point_in_time",
        membership_effective_from=date(2020, 1, 1),
        membership_effective_to=date(2025, 12, 31),
        snapshot_date=date(2025, 12, 31),
        include_delisted=True,
        membership_snapshot_ids=("membership_001",),
        quality_status="ok",
        gaps=(),
        frozen=True,
    )


def make_forward_watchlist() -> ForwardWatchlistSnapshot:
    return ForwardWatchlistSnapshot(
        watchlist_snapshot_id="watchlist_001",
        theme_id="theme_001",
        confirmed_candidate_ids=("confirmed_001",),
        symbols=("300750.SZ",),
        snapshot_date=date(2026, 6, 25),
        created_at=NOW,
        forward_only=True,
        frozen=True,
    )


def make_strategy_draft() -> StrategyDraft:
    return StrategyDraft(
        strategy_revision_id="strategy_revision_001",
        theme_id="theme_001",
        hypothesis_id="hypothesis_001",
        strategy_template_id="theme_momentum_breakout_v1",
        strategy_template_version="v1",
        strategy_template_hash="template_hash_001",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        backtest_universe_spec_id="universe_001",
        strategy_config_json='{"entry":"breakout","exit":"time_exit"}',
        sample_split_rule_id="fixed_ratio_70_30",
        created_at=NOW,
        frozen=True,
    )


def make_lifecycle_state(
    state: str = "draft",
    state_version: int = 1,
    source_record_id: str = "strategy_revision_001",
) -> StrategyLifecycleState:
    return StrategyLifecycleState(
        lifecycle_state_id=f"lifecycle_{state_version}",
        strategy_revision_id="strategy_revision_001",
        state_version=state_version,
        state=state,
        source_record_id=source_record_id,
        recorded_at=NOW,
        recorded_by="system",
        frozen=True,
    )


def make_protocol_snapshot() -> ResearchProtocolSnapshot:
    return ResearchProtocolSnapshot(
        protocol_snapshot_id="protocol_001",
        theme_id="theme_001",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        strategy_revision_id="strategy_revision_001",
        sample_split_rule_id="fixed_ratio_70_30",
        oos_window_rule_id="latest_252_trading_days",
        oos_window_rule_params_json='{"length":252}',
        oos_window_start=date(2025, 1, 2),
        oos_window_end=date(2025, 12, 31),
        shared_oos_window_id="oos_window_001",
        backtest_universe_spec_id="universe_001",
        data_snapshot_id="data_snapshot_001",
        kill_criteria_snapshot_id="kill_snapshot_001",
        prototype_gate_thresholds_json='{"min_oos_trades":20}',
        strategy_config_hash="strategy_hash_001",
        data_snapshot_hash="data_hash_001",
        gate_criteria_hash="gate_hash_001",
        frozen_at=NOW,
        frozen_by="system",
        frozen=True,
    )


def make_ledger() -> OOSEvaluationLedger:
    return OOSEvaluationLedger(
        ledger_snapshot_id="ledger_001",
        theme_id="theme_001",
        hypothesis_source_snapshot_id="hypothesis_snapshot_001",
        ledger_version=1,
        oos_evaluation_count=0,
        oos_budget_limit=3,
        next_oos_draw_index=1,
        budget_status="available",
        completed_evaluation_ids=(),
        active_reservation_ids=(),
        report_ids=(),
        recorded_at=NOW,
        frozen=True,
    )


def make_report() -> ImmutableBacktestReport:
    return ImmutableBacktestReport(
        report_id="report_001",
        theme_id="theme_001",
        strategy_revision_id="strategy_revision_001",
        protocol_snapshot_id="protocol_001",
        strategy_config_hash="strategy_hash_001",
        data_snapshot_hash="data_hash_001",
        gate_criteria_hash="gate_hash_001",
        evaluation_mode="out_of_sample",
        oos_draw_index=1,
        shared_oos_window_id="oos_window_001",
        multiple_comparison_flag=False,
        report_payload_json='{"data_quality_status":"ok"}',
        integrity_status="valid",
        generated_at=NOW,
        report_hash="report_hash_001",
        frozen=True,
    )


def make_gate_result(
    verdict: str = "candidate_for_prototype_passed",
) -> PrototypeGateResultV2:
    return PrototypeGateResultV2(
        gate_result_id="gate_001",
        report_id="report_001",
        strategy_revision_id="strategy_revision_001",
        protocol_snapshot_id="protocol_001",
        verdict=verdict,
        checks_json='{"all_checks":"pass"}',
        blocking_issues=(),
        warnings=(),
        strategy_config_hash="strategy_hash_001",
        data_snapshot_hash="data_hash_001",
        gate_criteria_hash="gate_hash_001",
        oos_draw_index=1,
        shared_oos_window_id="oos_window_001",
        multiple_comparison_flag=False,
        generated_at=NOW,
        gate_result_hash="gate_result_hash_001",
        frozen=True,
    )


def make_confirmation() -> HumanPromotionConfirmation:
    return HumanPromotionConfirmation(
        human_confirmation_id="human_confirmation_001",
        strategy_revision_id="strategy_revision_001",
        gate_result_id="gate_001",
        decision="approve",
        confirmed_by="owner_001",
        confirmed_at=NOW,
        frozen=True,
    )
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_contracts -v
```

Expected: import failure for `contracts.strategy`.

- [ ] **Step 3: Implement frozen contracts**

Create `contracts/strategy.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FrozenStrategyContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_non_empty(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value


class StrategyTemplateDefinition(FrozenStrategyContract):
    template_id: str
    version: str
    template_hash: str
    hypothesis_types: tuple[str, ...]
    core_entry_rule_id: str
    supported_universe_rule_types: tuple[
        Literal["sector_plus_tags", "point_in_time_membership"], ...
    ]
    sample_split_rule_ids: tuple[str, ...]
    benchmark_rule_id: str
    created_at: datetime
    frozen: Literal[True] = True


class BacktestUniverseSpec(FrozenStrategyContract):
    universe_spec_id: str
    universe_rule_type: Literal["sector_plus_tags", "point_in_time_membership"]
    sector: str | None = None
    chain_layer_tags: tuple[str, ...] = ()
    membership_source: str
    membership_effective_from: date
    membership_effective_to: date
    snapshot_date: date
    include_delisted: Literal[True] = True
    membership_snapshot_ids: tuple[str, ...]
    quality_status: Literal["ok", "degraded", "insufficient"]
    gaps: tuple[str, ...] = ()
    frozen: Literal[True] = True

    @model_validator(mode="after")
    def validate_membership_window(self) -> "BacktestUniverseSpec":
        if self.membership_effective_from > self.membership_effective_to:
            raise ValueError("membership_effective_from cannot exceed membership_effective_to")
        if not self.membership_snapshot_ids and self.quality_status != "insufficient":
            raise ValueError("membership_snapshot_ids required unless quality is insufficient")
        return self


class ForwardWatchlistSnapshot(FrozenStrategyContract):
    watchlist_snapshot_id: str
    theme_id: str
    confirmed_candidate_ids: tuple[str, ...]
    symbols: tuple[str, ...]
    snapshot_date: date
    created_at: datetime
    forward_only: Literal[True] = True
    frozen: Literal[True] = True


class StrategyDraft(FrozenStrategyContract):
    strategy_revision_id: str
    theme_id: str
    hypothesis_id: str
    strategy_template_id: str
    strategy_template_version: str
    strategy_template_hash: str
    hypothesis_source_snapshot_id: str
    backtest_universe_spec_id: str
    strategy_config_json: str
    sample_split_rule_id: str
    created_at: datetime
    frozen: Literal[True] = True

    @field_validator("strategy_revision_id")
    @classmethod
    def revision_id_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "strategy_revision_id")


class StrategyLifecycleState(FrozenStrategyContract):
    lifecycle_state_id: str
    strategy_revision_id: str
    state_version: int = Field(ge=1)
    state: Literal["draft", "prototype_passed"]
    source_record_id: str
    recorded_at: datetime
    recorded_by: str
    frozen: Literal[True] = True


class ResearchProtocolSnapshot(FrozenStrategyContract):
    protocol_snapshot_id: str
    theme_id: str
    hypothesis_source_snapshot_id: str
    strategy_revision_id: str
    sample_split_rule_id: str
    oos_window_rule_id: str
    oos_window_rule_params_json: str
    oos_window_start: date
    oos_window_end: date
    shared_oos_window_id: str
    backtest_universe_spec_id: str
    data_snapshot_id: str
    kill_criteria_snapshot_id: str
    prototype_gate_thresholds_json: str
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    frozen_at: datetime
    frozen_by: str
    frozen: Literal[True] = True

    @model_validator(mode="after")
    def validate_protocol(self) -> "ResearchProtocolSnapshot":
        for name in (
            "strategy_config_hash",
            "data_snapshot_hash",
            "gate_criteria_hash",
        ):
            _require_non_empty(getattr(self, name), name)
        if self.oos_window_start > self.oos_window_end:
            raise ValueError("oos_window_start cannot exceed oos_window_end")
        return self


class OOSEvaluationLedger(FrozenStrategyContract):
    ledger_snapshot_id: str
    theme_id: str
    hypothesis_source_snapshot_id: str
    ledger_version: int = Field(ge=1)
    oos_evaluation_count: int = Field(ge=0, le=3)
    oos_budget_limit: Literal[3] = 3
    next_oos_draw_index: int = Field(ge=1, le=3)
    budget_status: Literal["available", "reserved", "oos_budget_exhausted"]
    completed_evaluation_ids: tuple[str, ...] = ()
    active_reservation_ids: tuple[str, ...] = ()
    report_ids: tuple[str, ...] = ()
    recorded_at: datetime
    frozen: Literal[True] = True


class ImmutableBacktestReport(FrozenStrategyContract):
    report_id: str
    theme_id: str
    strategy_revision_id: str
    protocol_snapshot_id: str
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    evaluation_mode: Literal[
        "in_sample", "out_of_sample", "prototype_sanity_check_only"
    ]
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    multiple_comparison_flag: bool = False
    report_payload_json: str
    integrity_status: Literal["valid", "invalid"]
    generated_at: datetime
    report_hash: str
    frozen: Literal[True] = True


class PrototypeGateResultV2(FrozenStrategyContract):
    gate_result_id: str
    report_id: str
    strategy_revision_id: str
    protocol_snapshot_id: str
    verdict: Literal[
        "rejected",
        "needs_review",
        "candidate_for_prototype_passed",
    ]
    checks_json: str
    blocking_issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    strategy_config_hash: str
    data_snapshot_hash: str
    gate_criteria_hash: str
    oos_draw_index: int | None = Field(default=None, ge=1, le=3)
    shared_oos_window_id: str | None = None
    multiple_comparison_flag: bool = False
    generated_at: datetime
    gate_result_hash: str
    frozen: Literal[True] = True


class HumanPromotionConfirmation(FrozenStrategyContract):
    human_confirmation_id: str
    strategy_revision_id: str
    gate_result_id: str
    decision: Literal["approve", "reject"]
    confirmed_by: str
    confirmed_at: datetime
    frozen: Literal[True] = True


class HumanConfirmationConsumption(FrozenStrategyContract):
    consumption_id: str
    human_confirmation_id: str
    strategy_revision_id: str
    gate_result_id: str
    promotion_id: str
    consumed_at: datetime
    consumed_by: str
    frozen: Literal[True] = True


class StrategyPromotionRecord(FrozenStrategyContract):
    promotion_id: str
    strategy_revision_id: str
    gate_result_id: str
    report_id: str
    protocol_snapshot_id: str
    human_confirmation_id: str
    previous_state: Literal["draft"]
    new_state: Literal["prototype_passed"]
    promoted_by: str
    promoted_at: datetime
    frozen: Literal[True] = True
```

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_contracts -v
```

Expected: all tests pass.

- [ ] **Step 5: Checkpoint**

Record:

- contracts are deeply represented with primitive values, tuples and canonical JSON strings;
- no B1 contract contains old `UniverseConfig`;
- no B1 contract can be assigned after construction;
- old stable contracts remain untouched.

---

## Task 2: Add the real universe admission boundary

**Files:**

- Modify: `contracts/strategy.py`
- Create: `tests/test_b1_universe_admission.py`

- [ ] **Step 1: Write failing business-boundary tests**

Create `tests/test_b1_universe_admission.py`:

```python
import unittest

from tests.b1_fixtures import make_backtest_universe, make_forward_watchlist


class TestBacktestUniverseAdmission(unittest.TestCase):
    def test_formal_backtest_accepts_backtest_universe(self):
        from contracts.strategy import admit_formal_backtest_universe

        admitted = admit_formal_backtest_universe(make_backtest_universe())
        self.assertEqual(admitted.universe_spec_id, "universe_001")

    def test_formal_backtest_rejects_forward_watchlist(self):
        from contracts.strategy import admit_formal_backtest_universe

        with self.assertRaisesRegex(TypeError, "BacktestUniverseSpec"):
            admit_formal_backtest_universe(make_forward_watchlist())

    def test_formal_backtest_rejects_plain_symbol_list(self):
        from contracts.strategy import admit_formal_backtest_universe

        with self.assertRaisesRegex(TypeError, "BacktestUniverseSpec"):
            admit_formal_backtest_universe(["300750.SZ"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_universe_admission -v
```

Expected: import failure for `admit_formal_backtest_universe`.

- [ ] **Step 3: Add the minimal admission function**

Append to `contracts/strategy.py`:

```python
def admit_formal_backtest_universe(
    universe: BacktestUniverseSpec,
) -> BacktestUniverseSpec:
    if not isinstance(universe, BacktestUniverseSpec):
        raise TypeError("formal backtest requires BacktestUniverseSpec")
    return universe
```

This is the B1 boundary function. B3/B4 backtest entry points must call it instead of accepting arbitrary symbol collections.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_universe_admission -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Checkpoint**

Confirm that the test fails on the actual admission call, not merely on class names or missing conversion helpers.

---

## Task 3: Create independent StrategyDB schema with append-only enforcement

**Files:**

- Create: `backend/db/strategy.py`
- Create: `tests/test_b1_strategy_db.py`

- [ ] **Step 1: Write failing schema and trigger tests**

Create the first part of `tests/test_b1_strategy_db.py`:

```python
import sqlite3
import unittest

from backend.db.strategy import StrategyDB
from tests.b1_fixtures import (
    make_backtest_universe,
    make_confirmation,
    make_gate_result,
    make_ledger,
    make_lifecycle_state,
    make_protocol_snapshot,
    make_report,
    make_strategy_draft,
    make_template_definition,
)


class TestStrategyDBSchema(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")

    def tearDown(self):
        self.db.close()

    def test_schema_is_separate_from_research_db(self):
        tables = self.db.list_table_names()
        self.assertIn("strategy_drafts", tables)
        self.assertNotIn("research_candidates", tables)

    def test_immutable_table_rejects_update(self):
        self.db.store_strategy_template(make_template_definition())
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "UPDATE strategy_template_definitions SET version = ? WHERE template_id = ?",
                ("v2", "theme_momentum_breakout_v1"),
            )

    def test_immutable_table_rejects_delete(self):
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.conn.execute(
                "DELETE FROM strategy_drafts WHERE strategy_revision_id = ?",
                ("strategy_revision_001",),
            )

    def test_duplicate_primary_key_does_not_overwrite(self):
        report = make_report()
        self.db.store_backtest_report(report)
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.store_backtest_report(report)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_strategy_db.TestStrategyDBSchema -v
```

Expected: import failure for `backend.db.strategy`.

- [ ] **Step 3: Implement schema and immutable triggers**

Create `backend/db/strategy.py` with:

```python
from __future__ import annotations

import sqlite3
from datetime import datetime

from contracts.strategy import (
    BacktestUniverseSpec,
    ForwardWatchlistSnapshot,
    HumanPromotionConfirmation,
    ImmutableBacktestReport,
    OOSEvaluationLedger,
    PrototypeGateResultV2,
    ResearchProtocolSnapshot,
    StrategyDraft,
    StrategyLifecycleState,
    StrategyPromotionRecord,
    StrategyTemplateDefinition,
)


IMMUTABLE_TABLES = (
    "strategy_template_definitions",
    "backtest_universe_specs",
    "forward_watchlist_snapshots",
    "strategy_drafts",
    "strategy_lifecycle_states",
    "research_protocol_snapshots",
    "oos_evaluation_ledgers",
    "immutable_backtest_reports",
    "prototype_gate_results_v2",
    "human_promotion_confirmations",
    "human_confirmation_consumptions",
    "strategy_promotions",
)


class StrategyDB:
    def __init__(self, db_path: str = "data/strategy.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_tables()

    def close(self) -> None:
        self.conn.close()

    def _create_tables(self) -> None:
        cursor = self.conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS strategy_template_definitions (
                template_id TEXT NOT NULL,
                version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                template_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (template_id, version)
            );

            CREATE TABLE IF NOT EXISTS backtest_universe_specs (
                universe_spec_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS forward_watchlist_snapshots (
                watchlist_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS strategy_drafts (
                strategy_revision_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                hypothesis_id TEXT NOT NULL,
                backtest_universe_spec_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (backtest_universe_spec_id)
                    REFERENCES backtest_universe_specs(universe_spec_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_lifecycle_states (
                lifecycle_state_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                state_version INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('draft', 'prototype_passed')),
                source_record_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (strategy_revision_id, state_version),
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );

            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_strategy_one_prototype_passed
            ON strategy_lifecycle_states(strategy_revision_id)
            WHERE state = 'prototype_passed';

            CREATE TABLE IF NOT EXISTS research_protocol_snapshots (
                protocol_snapshot_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                strategy_config_hash TEXT NOT NULL,
                data_snapshot_hash TEXT NOT NULL,
                gate_criteria_hash TEXT NOT NULL,
                frozen_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id)
            );

            CREATE TABLE IF NOT EXISTS oos_evaluation_ledgers (
                ledger_snapshot_id TEXT PRIMARY KEY,
                theme_id TEXT NOT NULL,
                ledger_version INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                UNIQUE (theme_id, ledger_version)
            );

            CREATE TABLE IF NOT EXISTS immutable_backtest_reports (
                report_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                report_hash TEXT NOT NULL UNIQUE,
                integrity_status TEXT NOT NULL CHECK (integrity_status IN ('valid', 'invalid')),
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS prototype_gate_results_v2 (
                gate_result_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                verdict TEXT NOT NULL CHECK (
                    verdict IN (
                        'rejected',
                        'needs_review',
                        'candidate_for_prototype_passed'
                    )
                ),
                payload_json TEXT NOT NULL,
                gate_result_hash TEXT NOT NULL UNIQUE,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (report_id)
                    REFERENCES immutable_backtest_reports(report_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS human_promotion_confirmations (
                human_confirmation_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL,
                gate_result_id TEXT NOT NULL,
                decision TEXT NOT NULL CHECK (decision IN ('approve', 'reject')),
                payload_json TEXT NOT NULL,
                confirmed_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (gate_result_id)
                    REFERENCES prototype_gate_results_v2(gate_result_id)
            );

            CREATE TABLE IF NOT EXISTS strategy_promotions (
                promotion_id TEXT PRIMARY KEY,
                strategy_revision_id TEXT NOT NULL UNIQUE,
                gate_result_id TEXT NOT NULL,
                report_id TEXT NOT NULL,
                protocol_snapshot_id TEXT NOT NULL,
                human_confirmation_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                promoted_at TEXT NOT NULL,
                FOREIGN KEY (strategy_revision_id)
                    REFERENCES strategy_drafts(strategy_revision_id),
                FOREIGN KEY (gate_result_id)
                    REFERENCES prototype_gate_results_v2(gate_result_id),
                FOREIGN KEY (report_id)
                    REFERENCES immutable_backtest_reports(report_id),
                FOREIGN KEY (protocol_snapshot_id)
                    REFERENCES research_protocol_snapshots(protocol_snapshot_id),
                FOREIGN KEY (human_confirmation_id)
                    REFERENCES human_promotion_confirmations(human_confirmation_id)
            );

            CREATE TABLE IF NOT EXISTS human_confirmation_consumptions (
                consumption_id TEXT PRIMARY KEY,
                human_confirmation_id TEXT NOT NULL UNIQUE,
                strategy_revision_id TEXT NOT NULL,
                gate_result_id TEXT NOT NULL,
                promotion_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                consumed_at TEXT NOT NULL,
                FOREIGN KEY (human_confirmation_id)
                    REFERENCES human_promotion_confirmations(human_confirmation_id),
                FOREIGN KEY (promotion_id)
                    REFERENCES strategy_promotions(promotion_id)
            );

            CREATE TRIGGER IF NOT EXISTS
                guard_prototype_passed_lifecycle_insert
            BEFORE INSERT ON strategy_lifecycle_states
            WHEN NEW.state = 'prototype_passed'
            BEGIN
                SELECT CASE WHEN NOT EXISTS (
                    SELECT 1
                    FROM strategy_promotions p
                    JOIN human_confirmation_consumptions c
                      ON c.promotion_id = p.promotion_id
                    WHERE p.strategy_revision_id = NEW.strategy_revision_id
                      AND p.promotion_id = NEW.source_record_id
                ) THEN RAISE(
                    ABORT,
                    'prototype_passed requires promotion and consumed confirmation'
                ) END;
            END;
            """
        )
        for table_name in IMMUTABLE_TABLES:
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_update
                BEFORE UPDATE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
            cursor.execute(
                f"""
                CREATE TRIGGER IF NOT EXISTS prevent_{table_name}_delete
                BEFORE DELETE ON {table_name}
                BEGIN
                    SELECT RAISE(ABORT, '{table_name} is append-only');
                END
                """
            )
        self.conn.commit()

    def list_table_names(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row["name"] for row in rows}

    @staticmethod
    def _json(model) -> str:
        return model.model_dump_json()

    def store_strategy_template(self, item: StrategyTemplateDefinition) -> None:
        self.conn.execute(
            """
            INSERT INTO strategy_template_definitions
            (template_id, version, payload_json, template_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.template_id,
                item.version,
                self._json(item),
                item.template_hash,
                item.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_backtest_universe(self, item: BacktestUniverseSpec) -> None:
        self.conn.execute(
            """
            INSERT INTO backtest_universe_specs
            (universe_spec_id, payload_json, created_at)
            VALUES (?, ?, ?)
            """,
            (
                item.universe_spec_id,
                self._json(item),
                datetime.now().isoformat(),
            ),
        )
        self.conn.commit()

    def store_forward_watchlist(self, item: ForwardWatchlistSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO forward_watchlist_snapshots
            (watchlist_snapshot_id, theme_id, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                item.watchlist_snapshot_id,
                item.theme_id,
                self._json(item),
                item.created_at.isoformat(),
            ),
        )
        self.conn.commit()

    def create_strategy_draft(
        self,
        draft: StrategyDraft,
        initial_state: StrategyLifecycleState,
    ) -> None:
        if initial_state.strategy_revision_id != draft.strategy_revision_id:
            raise ValueError("initial lifecycle state must match draft")
        if initial_state.state != "draft" or initial_state.state_version != 1:
            raise ValueError("initial lifecycle state must be draft version 1")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """
                INSERT INTO strategy_drafts
                (strategy_revision_id, theme_id, hypothesis_id,
                 backtest_universe_spec_id, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    draft.strategy_revision_id,
                    draft.theme_id,
                    draft.hypothesis_id,
                    draft.backtest_universe_spec_id,
                    self._json(draft),
                    draft.created_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    initial_state.lifecycle_state_id,
                    initial_state.strategy_revision_id,
                    initial_state.state_version,
                    initial_state.state,
                    initial_state.source_record_id,
                    self._json(initial_state),
                    initial_state.recorded_at.isoformat(),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def store_protocol_snapshot(self, item: ResearchProtocolSnapshot) -> None:
        self.conn.execute(
            """
            INSERT INTO research_protocol_snapshots
            (protocol_snapshot_id, strategy_revision_id, payload_json,
             strategy_config_hash, data_snapshot_hash, gate_criteria_hash, frozen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.protocol_snapshot_id,
                item.strategy_revision_id,
                self._json(item),
                item.strategy_config_hash,
                item.data_snapshot_hash,
                item.gate_criteria_hash,
                item.frozen_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_oos_ledger(self, item: OOSEvaluationLedger) -> None:
        self.conn.execute(
            """
            INSERT INTO oos_evaluation_ledgers
            (ledger_snapshot_id, theme_id, ledger_version, payload_json, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                item.ledger_snapshot_id,
                item.theme_id,
                item.ledger_version,
                self._json(item),
                item.recorded_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_backtest_report(self, item: ImmutableBacktestReport) -> None:
        self.conn.execute(
            """
            INSERT INTO immutable_backtest_reports
            (report_id, strategy_revision_id, protocol_snapshot_id, payload_json,
             report_hash, integrity_status, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.report_id,
                item.strategy_revision_id,
                item.protocol_snapshot_id,
                self._json(item),
                item.report_hash,
                item.integrity_status,
                item.generated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_gate_result(self, item: PrototypeGateResultV2) -> None:
        self.conn.execute(
            """
            INSERT INTO prototype_gate_results_v2
            (gate_result_id, strategy_revision_id, report_id,
             protocol_snapshot_id, verdict, payload_json,
             gate_result_hash, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.gate_result_id,
                item.strategy_revision_id,
                item.report_id,
                item.protocol_snapshot_id,
                item.verdict,
                self._json(item),
                item.gate_result_hash,
                item.generated_at.isoformat(),
            ),
        )
        self.conn.commit()

    def store_human_confirmation(self, item: HumanPromotionConfirmation) -> None:
        self.conn.execute(
            """
            INSERT INTO human_promotion_confirmations
            (human_confirmation_id, strategy_revision_id, gate_result_id,
             decision, payload_json, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item.human_confirmation_id,
                item.strategy_revision_id,
                item.gate_result_id,
                item.decision,
                self._json(item),
                item.confirmed_at.isoformat(),
            ),
        )
        self.conn.commit()
```

Do not add a generic `update_status` method.

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_strategy_db.TestStrategyDBSchema -v
```

Expected: schema and append-only tests pass.

- [ ] **Step 5: Checkpoint**

Confirm:

- no A table exists in StrategyDB;
- every B1 content table has update/delete triggers;
- lifecycle is append-only rather than mutable;
- no generic status update method exists.

---

## Task 4: Add typed round-trip reads and verify atomic draft creation

**Files:**

- Modify: `backend/db/strategy.py`
- Modify: `tests/test_b1_strategy_db.py`

- [ ] **Step 1: Add failing round-trip tests**

Append to `tests/test_b1_strategy_db.py`:

```python
class TestStrategyDBRoundTrip(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.db.store_strategy_template(make_template_definition())
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        self.db.store_protocol_snapshot(make_protocol_snapshot())
        self.db.store_oos_ledger(make_ledger())
        self.db.store_backtest_report(make_report())
        self.db.store_gate_result(make_gate_result())
        self.db.store_human_confirmation(make_confirmation())

    def tearDown(self):
        self.db.close()

    def test_reads_return_typed_frozen_contracts(self):
        self.assertEqual(
            self.db.get_strategy_draft("strategy_revision_001"),
            make_strategy_draft(),
        )
        self.assertEqual(
            self.db.get_protocol_snapshot("protocol_001"),
            make_protocol_snapshot(),
        )
        self.assertEqual(
            self.db.get_backtest_report("report_001"),
            make_report(),
        )
        self.assertEqual(
            self.db.get_gate_result("gate_001"),
            make_gate_result(),
        )

    def test_latest_lifecycle_state_is_draft(self):
        state = self.db.get_latest_lifecycle_state("strategy_revision_001")
        self.assertIsNotNone(state)
        self.assertEqual(state.state, "draft")
        self.assertEqual(state.state_version, 1)

    def test_create_draft_with_initial_state_is_atomic(self):
        second = make_strategy_draft().model_copy(
            update={"strategy_revision_id": "strategy_revision_002"}
        )
        initial = make_lifecycle_state().model_copy(
            update={
                "lifecycle_state_id": "lifecycle_002",
                "strategy_revision_id": "strategy_revision_002",
            }
        )
        self.db.create_strategy_draft(second, initial)
        self.assertIsNotNone(
            self.db.get_strategy_draft("strategy_revision_002")
        )
        self.assertEqual(
            self.db.get_latest_lifecycle_state("strategy_revision_002").state,
            "draft",
        )
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_strategy_db.TestStrategyDBRoundTrip -v
```

Expected: failures because typed read methods are not implemented yet.

- [ ] **Step 3: Implement typed reads and atomic create**

Add to `StrategyDB`:

```python
    @staticmethod
    def _load(model_type, row):
        if row is None:
            return None
        return model_type.model_validate_json(row["payload_json"])

    def get_strategy_draft(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_drafts
            WHERE strategy_revision_id = ?
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyDraft, row)

    def get_protocol_snapshot(self, protocol_snapshot_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM research_protocol_snapshots
            WHERE protocol_snapshot_id = ?
            """,
            (protocol_snapshot_id,),
        ).fetchone()
        return self._load(ResearchProtocolSnapshot, row)

    def get_backtest_report(self, report_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM immutable_backtest_reports
            WHERE report_id = ?
            """,
            (report_id,),
        ).fetchone()
        return self._load(ImmutableBacktestReport, row)

    def get_gate_result(self, gate_result_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM prototype_gate_results_v2
            WHERE gate_result_id = ?
            """,
            (gate_result_id,),
        ).fetchone()
        return self._load(PrototypeGateResultV2, row)

    def get_human_confirmation(self, human_confirmation_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM human_promotion_confirmations
            WHERE human_confirmation_id = ?
            """,
            (human_confirmation_id,),
        ).fetchone()
        return self._load(HumanPromotionConfirmation, row)

    def get_latest_lifecycle_state(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json
            FROM strategy_lifecycle_states
            WHERE strategy_revision_id = ?
            ORDER BY state_version DESC
            LIMIT 1
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyLifecycleState, row)

```

- [ ] **Step 4: Verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_strategy_db.TestStrategyDBRoundTrip -v
```

Expected: all round-trip tests pass.

- [ ] **Step 5: Checkpoint**

Verify no read method returns a mutable dict and initial lifecycle creation cannot leave a draft without a state row.

---

## Task 5: Add database-level promotion guards

**Files:**

- Modify: `backend/db/strategy.py`
- Modify: `tests/test_b1_strategy_db.py`

- [ ] **Step 1: Write failing direct-write rejection tests**

Append:

```python
class TestPromotionStorageGuards(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.db.store_strategy_template(make_template_definition())
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )

    def tearDown(self):
        self.db.close()

    def test_direct_prototype_passed_state_without_promotion_fails(self):
        promoted_state = make_lifecycle_state(
            state="prototype_passed",
            state_version=2,
            source_record_id="missing_promotion",
        )
        with self.assertRaisesRegex(
            sqlite3.IntegrityError,
            "requires promotion",
        ):
            self.db.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    promoted_state.lifecycle_state_id,
                    promoted_state.strategy_revision_id,
                    promoted_state.state_version,
                    promoted_state.state,
                    promoted_state.source_record_id,
                    promoted_state.model_dump_json(),
                    promoted_state.recorded_at.isoformat(),
                ),
            )

    def test_strategy_db_has_no_public_status_update_method(self):
        self.assertFalse(hasattr(self.db, "update_strategy_status"))
        self.assertFalse(hasattr(self.db, "update_strategy_draft_status"))
```

- [ ] **Step 2: Run and verify the guard**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_strategy_db.TestPromotionStorageGuards -v
```

Expected: tests pass if Task 3 trigger is correct. If the direct insert succeeds, stop and repair `guard_prototype_passed_lifecycle_insert` before continuing.

- [ ] **Step 3: Add private transaction helpers only**

Add to `StrategyDB`:

```python
    def _get_promotion_by_strategy(self, strategy_revision_id: str):
        row = self.conn.execute(
            """
            SELECT payload_json FROM strategy_promotions
            WHERE strategy_revision_id = ?
            """,
            (strategy_revision_id,),
        ).fetchone()
        return self._load(StrategyPromotionRecord, row)

    def _confirmation_is_consumed(self, human_confirmation_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1 FROM human_confirmation_consumptions
            WHERE human_confirmation_id = ?
            """,
            (human_confirmation_id,),
        ).fetchone()
        return row is not None
```

Do not add a public method that can insert promotion or `prototype_passed`.

- [ ] **Step 4: Re-run guard tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_strategy_db.TestPromotionStorageGuards -v
```

Expected: both tests pass.

- [ ] **Step 5: Checkpoint**

Confirm database trigger, not a Python comment, prevents direct state promotion.

---

## Task 6: Implement StrategyPromotionReducer as one transaction

**Files:**

- Create: `backend/services/strategy_promotion_reducer.py`
- Create: `tests/test_b1_promotion_reducer.py`
- Modify: `backend/db/strategy.py`

- [ ] **Step 1: Write failing reducer tests**

Create `tests/test_b1_promotion_reducer.py`:

```python
import sqlite3
import unittest
from datetime import datetime

from backend.db.strategy import StrategyDB
from backend.services.strategy_promotion_reducer import StrategyPromotionReducer
from contracts.strategy import HumanPromotionConfirmation
from tests.b1_fixtures import (
    make_backtest_universe,
    make_confirmation,
    make_gate_result,
    make_lifecycle_state,
    make_protocol_snapshot,
    make_report,
    make_strategy_draft,
    make_template_definition,
)


class TestStrategyPromotionReducer(unittest.TestCase):
    def setUp(self):
        self.db = StrategyDB(":memory:")
        self.db.store_strategy_template(make_template_definition())
        self.db.store_backtest_universe(make_backtest_universe())
        self.db.create_strategy_draft(
            make_strategy_draft(),
            make_lifecycle_state(),
        )
        self.db.store_protocol_snapshot(make_protocol_snapshot())
        self.db.store_backtest_report(make_report())
        self.db.store_gate_result(make_gate_result())
        self.db.store_human_confirmation(make_confirmation())
        self.reducer = StrategyPromotionReducer(self.db)

    def tearDown(self):
        self.db.close()

    def test_valid_human_confirmation_promotes_atomically(self):
        promotion = self.reducer.promote_to_prototype_passed(
            strategy_revision_id="strategy_revision_001",
            gate_result_id="gate_001",
            human_confirmation_id="human_confirmation_001",
            promoted_by="owner_001",
        )
        self.assertEqual(promotion.new_state, "prototype_passed")
        self.assertEqual(
            self.db.get_latest_lifecycle_state(
                "strategy_revision_001"
            ).state,
            "prototype_passed",
        )

    def test_same_request_is_idempotent(self):
        first = self.reducer.promote_to_prototype_passed(
            "strategy_revision_001",
            "gate_001",
            "human_confirmation_001",
            "owner_001",
        )
        second = self.reducer.promote_to_prototype_passed(
            "strategy_revision_001",
            "gate_001",
            "human_confirmation_001",
            "owner_001",
        )
        self.assertEqual(first.promotion_id, second.promotion_id)

    def test_different_gate_after_promotion_is_rejected(self):
        self.reducer.promote_to_prototype_passed(
            "strategy_revision_001",
            "gate_001",
            "human_confirmation_001",
            "owner_001",
        )
        with self.assertRaisesRegex(ValueError, "different gate"):
            self.reducer.promote_to_prototype_passed(
                "strategy_revision_001",
                "gate_other",
                "human_confirmation_other",
                "owner_001",
            )

    def test_rejected_gate_cannot_promote(self):
        rejected = make_gate_result(verdict="rejected").model_copy(
            update={
                "gate_result_id": "gate_rejected",
                "gate_result_hash": "gate_hash_rejected",
            }
        )
        self.db.store_gate_result(rejected)
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id="human_confirmation_rejected",
            strategy_revision_id="strategy_revision_001",
            gate_result_id="gate_rejected",
            decision="approve",
            confirmed_by="owner_001",
            confirmed_at=datetime(2026, 6, 26, 10, 0, 0),
            frozen=True,
        )
        self.db.store_human_confirmation(confirmation)
        with self.assertRaisesRegex(ValueError, "candidate_for_prototype_passed"):
            self.reducer.promote_to_prototype_passed(
                "strategy_revision_001",
                "gate_rejected",
                "human_confirmation_rejected",
                "owner_001",
            )

    def test_hash_mismatch_rolls_back_all_writes(self):
        bad_gate = make_gate_result().model_copy(
            update={
                "gate_result_id": "gate_bad_hash",
                "gate_result_hash": "gate_result_hash_bad",
                "data_snapshot_hash": "different_data_hash",
            }
        )
        self.db.store_gate_result(bad_gate)
        confirmation = HumanPromotionConfirmation(
            human_confirmation_id="human_confirmation_bad_hash",
            strategy_revision_id="strategy_revision_001",
            gate_result_id="gate_bad_hash",
            decision="approve",
            confirmed_by="owner_001",
            confirmed_at=datetime(2026, 6, 26, 10, 0, 0),
            frozen=True,
        )
        self.db.store_human_confirmation(confirmation)
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.reducer.promote_to_prototype_passed(
                "strategy_revision_001",
                "gate_bad_hash",
                "human_confirmation_bad_hash",
                "owner_001",
            )
        self.assertEqual(
            self.db.get_latest_lifecycle_state(
                "strategy_revision_001"
            ).state,
            "draft",
        )
        self.assertFalse(
            self.db._confirmation_is_consumed(
                "human_confirmation_bad_hash"
            )
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_promotion_reducer -v
```

Expected: import failure for reducer.

- [ ] **Step 3: Add the atomic DB operation**

Add imports to `backend/db/strategy.py`:

```python
from contracts.strategy import (
    HumanConfirmationConsumption,
    StrategyPromotionRecord,
)
```

Add this method to `StrategyDB`:

```python
    def _commit_validated_promotion(
        self,
        promotion: StrategyPromotionRecord,
        consumption: HumanConfirmationConsumption,
        lifecycle_state: StrategyLifecycleState,
    ) -> None:
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            self.conn.execute(
                """
                INSERT INTO strategy_promotions
                (promotion_id, strategy_revision_id, gate_result_id, report_id,
                 protocol_snapshot_id, human_confirmation_id, payload_json,
                 promoted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    promotion.promotion_id,
                    promotion.strategy_revision_id,
                    promotion.gate_result_id,
                    promotion.report_id,
                    promotion.protocol_snapshot_id,
                    promotion.human_confirmation_id,
                    self._json(promotion),
                    promotion.promoted_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO human_confirmation_consumptions
                (consumption_id, human_confirmation_id, strategy_revision_id,
                 gate_result_id, promotion_id, payload_json, consumed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    consumption.consumption_id,
                    consumption.human_confirmation_id,
                    consumption.strategy_revision_id,
                    consumption.gate_result_id,
                    consumption.promotion_id,
                    self._json(consumption),
                    consumption.consumed_at.isoformat(),
                ),
            )
            self.conn.execute(
                """
                INSERT INTO strategy_lifecycle_states
                (lifecycle_state_id, strategy_revision_id, state_version,
                 state, source_record_id, payload_json, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lifecycle_state.lifecycle_state_id,
                    lifecycle_state.strategy_revision_id,
                    lifecycle_state.state_version,
                    lifecycle_state.state,
                    lifecycle_state.source_record_id,
                    self._json(lifecycle_state),
                    lifecycle_state.recorded_at.isoformat(),
                ),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
```

- [ ] **Step 4: Implement reducer**

Create `backend/services/strategy_promotion_reducer.py`:

```python
from __future__ import annotations

import hashlib
from datetime import datetime

from backend.db.strategy import StrategyDB
from contracts.strategy import (
    HumanConfirmationConsumption,
    StrategyLifecycleState,
    StrategyPromotionRecord,
)


def _stable_id(prefix: str, *parts: str) -> str:
    payload = "|".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


class StrategyPromotionReducer:
    def __init__(self, db: StrategyDB):
        self.db = db

    def promote_to_prototype_passed(
        self,
        strategy_revision_id: str,
        gate_result_id: str,
        human_confirmation_id: str,
        promoted_by: str,
    ) -> StrategyPromotionRecord:
        existing = self.db._get_promotion_by_strategy(strategy_revision_id)
        if existing is not None:
            if (
                existing.gate_result_id == gate_result_id
                and existing.human_confirmation_id == human_confirmation_id
            ):
                return existing
            raise ValueError("strategy already promoted by a different gate")

        draft = self.db.get_strategy_draft(strategy_revision_id)
        if draft is None:
            raise ValueError("strategy draft not found")

        current_state = self.db.get_latest_lifecycle_state(strategy_revision_id)
        if current_state is None or current_state.state != "draft":
            raise ValueError("strategy lifecycle state must be draft")

        gate = self.db.get_gate_result(gate_result_id)
        if gate is None:
            raise ValueError("gate result not found")
        if gate.strategy_revision_id != strategy_revision_id:
            raise ValueError("gate result belongs to another strategy")
        if gate.verdict != "candidate_for_prototype_passed":
            raise ValueError(
                "gate verdict must be candidate_for_prototype_passed"
            )

        report = self.db.get_backtest_report(gate.report_id)
        if report is None:
            raise ValueError("backtest report not found")
        if report.integrity_status != "valid":
            raise ValueError("backtest report integrity is invalid")

        protocol = self.db.get_protocol_snapshot(gate.protocol_snapshot_id)
        if protocol is None:
            raise ValueError("research protocol snapshot not found")

        expected_hashes = (
            protocol.strategy_config_hash,
            protocol.data_snapshot_hash,
            protocol.gate_criteria_hash,
        )
        if (
            gate.strategy_config_hash,
            gate.data_snapshot_hash,
            gate.gate_criteria_hash,
        ) != expected_hashes:
            raise ValueError("gate/protocol hash mismatch")
        if (
            report.strategy_config_hash,
            report.data_snapshot_hash,
            report.gate_criteria_hash,
        ) != expected_hashes:
            raise ValueError("report/protocol hash mismatch")

        confirmation = self.db.get_human_confirmation(human_confirmation_id)
        if confirmation is None:
            raise ValueError("human confirmation not found")
        if confirmation.decision != "approve":
            raise ValueError("human confirmation must approve promotion")
        if confirmation.strategy_revision_id != strategy_revision_id:
            raise ValueError("human confirmation belongs to another strategy")
        if confirmation.gate_result_id != gate_result_id:
            raise ValueError("human confirmation belongs to another gate")
        if self.db._confirmation_is_consumed(human_confirmation_id):
            raise ValueError("human confirmation already consumed")

        now = datetime.now()
        promotion_id = _stable_id(
            "promotion",
            strategy_revision_id,
            gate_result_id,
            human_confirmation_id,
        )
        promotion = StrategyPromotionRecord(
            promotion_id=promotion_id,
            strategy_revision_id=strategy_revision_id,
            gate_result_id=gate_result_id,
            report_id=report.report_id,
            protocol_snapshot_id=protocol.protocol_snapshot_id,
            human_confirmation_id=human_confirmation_id,
            previous_state="draft",
            new_state="prototype_passed",
            promoted_by=promoted_by,
            promoted_at=now,
            frozen=True,
        )
        consumption = HumanConfirmationConsumption(
            consumption_id=_stable_id(
                "confirmation_consumption",
                human_confirmation_id,
                promotion_id,
            ),
            human_confirmation_id=human_confirmation_id,
            strategy_revision_id=strategy_revision_id,
            gate_result_id=gate_result_id,
            promotion_id=promotion_id,
            consumed_at=now,
            consumed_by=promoted_by,
            frozen=True,
        )
        lifecycle_state = StrategyLifecycleState(
            lifecycle_state_id=_stable_id(
                "lifecycle",
                strategy_revision_id,
                "2",
                promotion_id,
            ),
            strategy_revision_id=strategy_revision_id,
            state_version=2,
            state="prototype_passed",
            source_record_id=promotion_id,
            recorded_at=now,
            recorded_by=promoted_by,
            frozen=True,
        )
        self.db._commit_validated_promotion(
            promotion,
            consumption,
            lifecycle_state,
        )
        return promotion
```

- [ ] **Step 5: Verify GREEN**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_promotion_reducer -v
```

Expected: all reducer tests pass.

- [ ] **Step 6: Checkpoint**

Confirm:

- validation happens before transaction writes;
- promotion, confirmation consumption and lifecycle state commit together;
- rollback leaves strategy in draft and confirmation unconsumed;
- exact replay returns the original promotion;
- different Gate cannot replace the first promotion.

---

## Task 7: Prove compatibility and forbidden paths

**Files:**

- Create: `tests/test_b1_compatibility.py`

- [ ] **Step 1: Write compatibility tests**

Create:

```python
import unittest

from backend.db.research import ResearchDB
from contracts.stable import PrototypeGateResult
from contracts.strategy import PrototypeGateResultV2
from strategy_core.prototype_gate import evaluate_prototype_gate


class TestB1Compatibility(unittest.TestCase):
    def test_old_gate_contract_remains_distinct(self):
        self.assertIsNot(PrototypeGateResult, PrototypeGateResultV2)
        self.assertTrue(callable(evaluate_prototype_gate))

    def test_research_db_schema_is_not_modified_by_strategy_db(self):
        db = ResearchDB(":memory:")
        table_names = {
            row["name"]
            for row in db.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertNotIn("strategy_drafts", table_names)
        self.assertNotIn("strategy_promotions", table_names)

    def test_stable_contract_has_no_b1_verdict_field(self):
        self.assertNotIn(
            "verdict",
            PrototypeGateResult.model_fields,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run focused compatibility tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_b1_compatibility -v
```

Expected: 3 tests pass without production changes.

- [ ] **Step 3: Run existing A and Gate regressions**

Run:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_research_db tests.test_research_action_reducer tests.test_prototype_gate tests.test_contract_serialization -v
```

Expected: all tests pass. Any failure is a B1 regression and must be fixed without changing A contracts or old Gate semantics.

- [ ] **Step 4: Checkpoint**

Record exact focused test counts and confirm `contracts/stable.py` and `backend/db/research.py` remain unchanged.

---

## Task 8: Full B1 verification and handoff

**Files:**

- Verify only; no production file should be added in this task.

- [ ] **Step 1: Run all B1 tests**

Run:

```powershell
.venv\Scripts\python.exe -m unittest `
  tests.test_b1_contracts `
  tests.test_b1_universe_admission `
  tests.test_b1_strategy_db `
  tests.test_b1_promotion_reducer `
  tests.test_b1_compatibility -v
```

Expected: all B1 tests pass.

- [ ] **Step 2: Run full Python suite**

Run:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests
```

Expected: full suite passes. Report every skipped test by exact name and reason.

- [ ] **Step 3: Verify forbidden changes**

Run:

```powershell
git diff -- contracts/stable.py contracts/draft.py contracts/research.py backend/db/research.py strategy_core/prototype_gate.py
```

Expected: no B1 changes in these files. If the workspace is not a valid Git worktree, compare file hashes captured before implementation and state that Git verification was unavailable.

- [ ] **Step 4: Verify no public status mutation API**

Run:

```powershell
rg -n "update_strategy_status|update_strategy_draft_status|status.*prototype_passed" backend contracts
```

Expected:

- no StrategyDB public update method;
- `prototype_passed` writes appear only in the B1 reducer contracts, transaction path and tests;
- no Gate or backtest code writes lifecycle state.

- [ ] **Step 5: Final checkpoint**

Hand off only:

1. exact files created or modified;
2. exact B1 and full-suite results;
3. append-only trigger evidence;
4. reducer transaction and rollback evidence;
5. confirmation that A and stable contracts were untouched;
6. skipped tests and remaining issues.

Do not claim B2 readiness unless every B1 exit criterion below passes.

---

## B1 exit criteria

- `BacktestUniverseSpec` is the only type admitted by the formal backtest boundary.
- `ForwardWatchlistSnapshot`, symbol lists and old `UniverseConfig` are rejected.
- `StrategyDraft` has no mutable lifecycle status.
- All content contracts use frozen Pydantic models.
- All B1 stored records reject SQL `UPDATE` and `DELETE`.
- Lifecycle is represented by append-only versioned states.
- Old `PrototypeGateResult` and `strategy_core.prototype_gate` are unchanged.
- `PrototypeGateResultV2.verdict` has exactly three allowed values.
- Direct insertion of `prototype_passed` lifecycle state without promotion and consumed confirmation fails in SQLite.
- Human confirmation is bound to one strategy and one Gate, and can be consumed once.
- Promotion record, confirmation consumption and lifecycle state are committed atomically.
- Exact replay is idempotent; a different Gate cannot replace an existing promotion.
- A module tests and full Python suite remain green.

## Self-review checklist

- Spec coverage: all B1 objects and hard boundaries map to Tasks 1–7.
- Scope: no template content, OOS algorithm, backtest or Gate calculation is implemented.
- Type consistency: names and method signatures are identical across fixtures, tests, DB and reducer.
- Compatibility: stable contracts and ResearchDB are not modified.
- No placeholders: implementation steps contain executable code and exact commands.
- No hidden mutable state: draft content and lifecycle state are separate append-only records.
