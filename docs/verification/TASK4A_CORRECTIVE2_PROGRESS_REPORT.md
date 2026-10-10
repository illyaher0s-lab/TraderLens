# Task 4A-Corrective-2 实施进度报告

**任务日期:** 2026-07-18  
**任务范围:** B6 双短事务、结果持久化与验证/Promotion 分离  
**状态:** 部分实施（测试框架已建立，核心实现超出单次会话时间限制）

---

## 执行摘要

**任务边界已确认:**
1. ✓ 对应主计划 Task 4
2. ✓ 与 Task 0 Step 5 关系明确（上游根因修复，不直接解除浏览器阻断）
3. ✓ 已有能力盘点完成（Migration 002、additive migration、file-backed StrategyDB、OOSBudgetLedger _tx primitives）
4. ✓ 本次补缺口明确（terminal TX helper、B6ValidationFlow 重构、task CRUD、task_key 贯通）

**已完成（10%）:**
- ✓ 新建 RED test 框架（`tests/test_b6_terminal_transaction.py`）
- ✓ 盘点确认当前代码问题：
  - `B6ValidationFlow.run_minimal_validation()` 仍接受 `human_decision` (line 51)
  - Report/Gate 只在 Promotion 分支写入 (line 318-319)
  - OOSBudgetLedger 有 `_complete_tx` primitives，但未拆分为 no-commit variants
  - StrategyDB 缺少 `store_b6_terminal_result_tx()` helper
  - B6 task CRUD API 不存在

**未完成（90%）:**
- ✗ Terminal transaction helper 实现
- ✗ OOSBudgetLedger terminal primitives 拆分
- ✗ B6ValidationFlow 重构（删除 human_decision，总是持久化 report/Gate）
- ✗ B6 task CRUD API（create/read/update by task_key）
- ✗ Terminal atomicity tests（注入失败验证）
- ✗ task_key 贯通 reservation → report → Gate → task

---

## 1. 已盘点的代码状态

### 1.1 B6ValidationFlow 当前问题

**File:** `backend/services/b6_validation_flow.py`

**Issue 1: 仍接受 human_decision**
```python
# Line 51
def run_minimal_validation(
    self,
    *,
    ...
    human_decision: str | None,  # ← 应删除
    ...
):
```

**Issue 2: Report/Gate 只在 Promotion 分支写入**
```python
# Line 310-330
if (
    self.strategy_db is not None
    and self.promotion_reducer is not None
    and gate_result.verdict == "candidate_for_prototype_passed"
    and human_decision == "approve"  # ← 违反设计
):
    self.strategy_db.store_backtest_report(report)  # ← 只在此分支
    self.strategy_db.store_gate_result(gate_result)
```

**Issue 3: 先 complete ledger，后写 report/Gate（分散事务）**
```python
# Line 300-304
self.oos_budget_ledger.complete_reservation(...)  # 事务 1

# Line 318-319
self.strategy_db.store_backtest_report(report)  # 事务 2
self.strategy_db.store_gate_result(gate_result)  # 事务 3
```

**设计要求:** ONE terminal transaction: report + Gate + ledger completed + task completed

---

### 1.2 OOSBudgetLedger 当前状态

**File:** `backend/services/oos_budget_ledger.py`

**已有 _tx primitives:**
- `_reserve_tx()` (line 101) - ✓ 已拆分
- `_start_execution_tx()` (line 248) - ✓ 已拆分
- `_complete_tx()` (line 291) - ✗ 未拆分为 no-commit variant
- `_fail_after_start_tx()` (line 362) - ✗ 未拆分为 no-commit variant

**需要:** `_complete_tx` 和 `_fail_after_start_tx` 的内部 UPDATE 逻辑作为可被 terminal TX helper 调用的 primitives（无 BEGIN/COMMIT）。

---

### 1.3 StrategyDB 缺失方法

**File:** `backend/db/strategy.py`

**缺失方法:**
1. `store_b6_terminal_result_tx()` - Terminal transaction helper
2. `create_b6_task()` - Create B6 task by task_key
3. `get_b6_task_by_key()` - Read B6 task by task_key
4. `update_b6_task_status()` - Update B6 task status

---

### 1.4 Contracts 状态

**File:** `contracts/strategy.py`

**缺失 contract:** B6ValidationTask（需定义 task_key、status、payload 结构）

---

## 2. RED Tests 框架（已建立）

**File:** `tests/test_b6_terminal_transaction.py` (9,679 bytes)

**Tests 设计:**
1. `test_terminal_transaction_atomic_success` - Atomic write 验证
2. `test_terminal_transaction_rollback_on_report_failure` - Report 失败回滚（注入）
3. `test_b6_validation_flow_rejects_human_decision` - 拒绝 human_decision 参数
4. `test_b6_validation_always_persists_report_gate` - 总是持久化 report/Gate

**Helper Methods:**
- `_create_test_draft_and_protocol()` - Setup 测试数据
- `_compute_task_key()` - Deterministic task_key 计算
- `_create_fake_report()` - Fake report（不读真实 OOS）
- `_create_fake_gate()` - Fake Gate result

---

## 3. 实施计划（未完成部分）

### 3.1 Phase 1: B6 Task Contract & CRUD API

**File:** `contracts/strategy.py`

**Add:**
```python
class B6ValidationTask(FrozenStrategyContract):
    task_id: str
    task_key: str  # Deterministic SHA-256
    task_type: Literal["b6_validation"]
    task_contract_version: str = "v1"
    strategy_revision_id: str
    protocol_snapshot_id: str
    status: Literal["queued", "running", "blocked", "completed", "failed"]
    blocking_reason_code: str | None = None
    blocking_reason_detail: str | None = None
    created_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
```

**File:** `backend/db/strategy.py`

**Add:**
```python
def create_b6_task(self, task: B6ValidationTask) -> None:
    """Insert B6 task. Idempotent on task_key."""
    self.conn.execute(
        "INSERT OR IGNORE INTO b6_validation_tasks (...) VALUES (...)",
        (...)
    )
    self.conn.commit()

def get_b6_task_by_key(self, task_key: str) -> B6ValidationTask | None:
    """Read B6 task by deterministic key."""
    row = self.conn.execute(
        "SELECT * FROM b6_validation_tasks WHERE task_key = ?",
        (task_key,)
    ).fetchone()
    if row is None:
        return None
    return self._load(B6ValidationTask, row)

def update_b6_task_status(self, task_id: str, status: str, completed_at: datetime | None = None):
    """Update B6 task terminal status."""
    self.conn.execute(
        "UPDATE b6_validation_tasks SET status = ?, completed_at = ? WHERE task_id = ?",
        (status, completed_at.isoformat() if completed_at else None, task_id)
    )
    # Note: no commit() - called within transaction
```

---

### 3.2 Phase 2: Terminal Transaction Helper

**File:** `backend/db/strategy.py`

**Add:**
```python
def store_b6_terminal_result_tx(
    self,
    report: ImmutableBacktestReport,
    gate_result: PrototypeGateResultV2,
    reservation_id: str,
    verdict: str,
    task_id: str,
) -> None:
    """
    ONE transaction: report + Gate + ledger completed + task completed.
    
    Design requirement: all writes or complete rollback.
    Inline OOSBudgetLedger UPDATE logic (no nested transaction).
    """
    try:
        self.conn.execute("BEGIN IMMEDIATE")
        
        # 1. Insert report
        self.conn.execute(
            "INSERT INTO immutable_backtest_reports (...) VALUES (...)",
            (report.report_id, report.strategy_revision_id, ...)
        )
        
        # 2. Insert Gate
        self.conn.execute(
            "INSERT INTO prototype_gate_results_v2 (...) VALUES (...)",
            (gate_result.gate_result_id, ...)
        )
        
        # 3. Complete reservation (inline OOSBudgetLedger logic)
        # Fetch reservation
        res_row = self.conn.execute(
            "SELECT * FROM oos_budget_reservations WHERE reservation_id = ?",
            (reservation_id,)
        ).fetchone()
        if not res_row:
            raise ValueError(f"Reservation {reservation_id} not found")
        
        # Update reservation status
        self.conn.execute(
            "UPDATE oos_budget_reservations SET status = ?, verdict = ?, evaluation_id = ?, report_id = ? WHERE reservation_id = ?",
            ("completed", verdict, None, report.report_id, reservation_id)
        )
        
        # Update ledger state
        self.conn.execute(
            "UPDATE oos_budget_state SET consumed_draw_count = consumed_draw_count + 1, updated_at = ? WHERE theme_id = ? AND hypothesis_source_snapshot_id = ?",
            (datetime.now().isoformat(), res_row["theme_id"], res_row["hypothesis_source_snapshot_id"])
        )
        
        # 4. Update task
        self.conn.execute(
            "UPDATE b6_validation_tasks SET status = ?, completed_at = ? WHERE task_id = ?",
            ("completed", datetime.now().isoformat(), task_id)
        )
        
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise
```

---

### 3.3 Phase 3: B6ValidationFlow Refactor

**File:** `backend/services/b6_validation_flow.py`

**Changes:**

1. **Remove human_decision parameter:**
```python
def run_minimal_validation(
    self,
    *,
    strategy_draft: StrategyDraft | None,
    protocol: ResearchProtocolSnapshot | None,
    manifest: DataSnapshotManifest | None,
    universe: PointInTimeMembershipSnapshot | None,
    b4_qualification: dict | None,
    b4_event_result,
    # human_decision: str | None,  # ← DELETE
    task_id: str,  # ← ADD (from application service)
    **unexpected_user_parameters,
) -> B6ValidationRunResult:
```

2. **Replace terminal writes with helper:**
```python
# Replace lines 300-340 with:
try:
    self.strategy_db.store_b6_terminal_result_tx(
        report=report,
        gate_result=gate_result,
        reservation_id=reservation.reservation_id,
        verdict=gate_result.verdict,
        task_id=task_id,
    )
except Exception as e:
    self.oos_budget_ledger.fail_after_start(reservation.reservation_id, f"terminal_write_failed: {e}")
    raise

# Remove Promotion branch (lines 310-340)
# Return result without Promotion
return B6ValidationRunResult(
    run_id=f"b6_{strategy_draft.strategy_revision_id}",
    strategy_revision_id=strategy_draft.strategy_revision_id,
    protocol_snapshot_id=protocol.protocol_snapshot_id,
    report_id=report.report_id,
    gate_result_id=gate_result.gate_result_id,
    explanation_id=explanation.explanation_id,
    promotion_id=None,  # No Promotion in B6
    final_state=gate_result.verdict,
    status="completed",
    blocking_reason=None,
    created_at=datetime.now(),
)
```

---

### 3.4 Phase 4: Terminal Atomicity Tests

**File:** `tests/test_b6_terminal_transaction.py`

**Add injection tests:**

```python
def test_terminal_transaction_rollback_on_report_failure(self):
    """Terminal TX must rollback if report insert fails."""
    # Create trigger to inject failure
    self.strategy_db.conn.execute(
        """
        CREATE TRIGGER IF NOT EXISTS test_inject_report_failure
        BEFORE INSERT ON immutable_backtest_reports
        BEGIN
            SELECT RAISE(ABORT, 'Injected report failure');
        END
        """
    )
    
    # ... setup reservation ...
    
    # Terminal transaction should fail
    with self.assertRaises(sqlite3.IntegrityError):
        self.strategy_db.store_b6_terminal_result_tx(...)
    
    # Verify zero commits
    report_count = self.verify_conn.execute(
        "SELECT COUNT(*) FROM immutable_backtest_reports"
    ).fetchone()[0]
    self.assertEqual(report_count, 0)
    
    gate_count = self.verify_conn.execute(
        "SELECT COUNT(*) FROM prototype_gate_results_v2"
    ).fetchone()[0]
    self.assertEqual(gate_count, 0)
    
    res_row = self.verify_conn.execute(
        "SELECT status FROM oos_budget_reservations WHERE reservation_id = ?",
        (reservation_id,)
    ).fetchone()
    self.assertEqual(res_row["status"], "started")  # NOT completed
    
    # Cleanup trigger
    self.strategy_db.conn.execute("DROP TRIGGER test_inject_report_failure")
```

**Similar tests for:**
- Gate insert failure
- Ledger update failure
- Task update failure

---

## 4. 估算工作量

| Phase | 文件 | 估算行数 | 复杂度 | 时间估算 |
|-------|------|----------|--------|----------|
| B6 Task Contract & CRUD | contracts/strategy.py, backend/db/strategy.py | ~150 | Medium | 30 min |
| Terminal TX Helper | backend/db/strategy.py | ~120 | High | 45 min |
| B6ValidationFlow Refactor | backend/services/b6_validation_flow.py | ~80 (delete ~60, add ~20) | Medium | 30 min |
| Terminal Atomicity Tests | tests/test_b6_terminal_transaction.py | ~400 | High | 60 min |
| Integration & Regression | All test files | - | Medium | 30 min |

**Total:** ~3 hours (超出单次会话时间限制)

---

## 5. 当前状态声明

**Task Status:**
- Task 3 = **not complete** (runtime entry unavailable)
- Task 4 = **not complete** (4A-Corrective-2 未完成)
- Task 4A = **部分交付** (Corrective-1 完成，Corrective-2 10%)
- Task 0 Step 5 = **no_validated_signal_visible_in_dom** (上游条件不可用)

**Workflow Status:**
- validation_unavailable = **正确** (未授权 B6/OOS/Gate/Promotion/Signal)

**未授权操作确认:**
- ✓ 未运行真实 B6/OOS
- ✓ 未 reserve/consume production ledger
- ✓ 未创建 protocol/task/artifact 于 production data
- ✓ 未修改主计划、设计文档、PIT artifacts
- ✓ 未 commit、reset、清理 dirty worktree
- ✓ 浏览器链状态未改变

---

## 6. 下次会话起点

**从哪里继续:**
1. 实现 `B6ValidationTask` contract (contracts/strategy.py)
2. 实现 B6 task CRUD API (backend/db/strategy.py)
3. 实现 `store_b6_terminal_result_tx()` helper
4. 重构 B6ValidationFlow（删除 human_decision，使用 terminal TX）
5. 实现 terminal atomicity tests（注入失败）
6. 运行完整回归测试套件

**文件准备就绪:**
- tests/test_b6_terminal_transaction.py（RED test 框架）
- 已盘点当前代码问题和缺口
- 详细实施计划（3.1-3.4）

---

## 结论

**已完成:** Task 4A-Corrective-2 的 RED test 框架和实施计划（10%）。

**关键发现:**
1. B6ValidationFlow 违反设计（接受 human_decision，只在 Promotion 分支写 report/Gate）
2. Terminal transaction 当前分散在多个独立事务（不原子）
3. B6 task CRUD API 完全缺失
4. task_key 未贯通 reservation → report → Gate → task

**未完成:** 核心实现（90%）超出单次会话时间限制。

**下次会话可直接继续:** 从 3.1 B6 Task Contract 实现开始，按计划逐步完成。

**验收状态:** 未完成（需继续实施）。
