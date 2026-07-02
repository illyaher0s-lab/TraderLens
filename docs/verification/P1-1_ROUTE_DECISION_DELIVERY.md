# P1-1 Route Decision 单一裁决源收口 - 交付报告

**Commit:** 7ac0c6c  
**状态:** 部分完成（架构重构 70%，handlers 待修复）

---

## 根因

**双重裁决源污染（4层）:**

1. **第1层（核心污染源）- Line 1059-1067:** `workflow_kind_map` 强制映射
   ```python
   workflow_kind_map = {
       "execution_feedback": WorkflowKind.FRIEND_STOCK,  # 覆盖！
       "position_followup": WorkflowKind.FRIEND_STOCK,   # 覆盖！
       "theme_research": WorkflowKind.FRIEND_STOCK,      # 覆盖！
   }
   workflow_kind = workflow_kind_map.get(route_decision.workflow_kind, WorkflowKind.UNKNOWN)
   session.workflow_kind = workflow_kind  # 污染 session
   ```

2. **第2层 - Line 1270:** 业务判断读取 `session.workflow_kind`
   ```python
   if session.workflow_kind == WorkflowKind.FRIEND_STOCK:
   ```

3. **第3层 - Line 1272, 1294:** 嵌套判断 `route_decision.workflow_kind`
   ```python
   if route_decision.workflow_kind == "execution_feedback":
   elif route_decision.workflow_kind == "position_followup":
   ```

4. **第4层 - Line 1259:** 响应覆盖
   ```python
   workflow_type = session.workflow_kind.value  # 返回 "friend_stock"，不是 "execution_feedback"
   ```

**结果:** `execution_feedback` 和 `position_followup` 的 `response.workflow_type` 被覆盖为 `friend_stock`，违反单一裁决源铁则。

---

## 实现为

### 已完成 ✅

1. **创建独立 handler 模块（backend/api/workbench_handlers.py, 449 lines）**
   - `handle_friend_stock()`
   - `handle_strategy_idea()`
   - `handle_execution_feedback()`
   - `handle_position_followup()`
   - `handle_theme_research_deferred()`
   - `handle_clarification()`

2. **删除旧业务逻辑（backend/api/research.py）**
   - 删除 401 行（Line 1351-1751）
   - 删除所有 `if session.workflow_kind ==` 分支判断
   - 文件从 2309 行减少到 1908 行

3. **重构 workbench_message 端点**
   - 添加 handler 导入（Line 38-47）
   - 修改 session 创建逻辑，添加注释说明 `workflow_kind_for_db` 仅用于 DB 持久化（Line 1066-1115）
   - 添加单一裁决源 dispatch 逻辑（Line 1277-1350）:
     ```python
     workflow_kind = route_decision.workflow_kind  # ONLY 裁决源
     
     if workflow_kind == "friend_stock":
         handler_result = handle_friend_stock(...)
     elif workflow_kind == "strategy_idea":
         handler_result = handle_strategy_idea(...)
     elif workflow_kind == "execution_feedback":
         handler_result = handle_execution_feedback(...)
     elif workflow_kind == "position_followup":
         handler_result = handle_position_followup(...)
     # ...
     
     workflow_type = workflow_kind  # 铁则：response.workflow_type == route_decision.workflow_kind
     ```

4. **备份原始文件**
   - `backend/api/research.py.backup_before_refactor`

### 未完成 ❌

1. **Handler 初始化参数错误**
   - `FriendStockFlowService.__init__()` 不接受 `db_conn` 参数
   - 需要改为 `validator`, `serenity_runner`, `market_data_provider`
   - 影响 `handle_friend_stock()` 和相关 handlers

2. **验证脚本未完全通过**
   - 前 2/9 测试通过：
     - ✅ "已买入100股成交价12.34" → `execution_feedback` (正确！)
     - ✅ "今天要不要继续拿" → `position_followup` (正确！)
   - 第 3 个测试失败（"帮我看603002"）due to handler 初始化错误

3. **Handler 非空壳证明**
   - execution_feedback: 需贴落库的 execution log 记录 id
   - position_followup: 需贴查到的 open_position id

---

## 证据为

### 旧覆盖点清单（已删除）

| 文件 | 原行号 | 代码 | 状态 |
|------|--------|------|------|
| backend/api/research.py | 1059-1067 | `workflow_kind_map = {...}` | ✅ 已删除 |
| backend/api/research.py | 1270 | `if session.workflow_kind == WorkflowKind.FRIEND_STOCK:` | ✅ 已删除 |
| backend/api/research.py | 1272 | `if ... route_decision.workflow_kind == "execution_feedback":` | ✅ 已删除 |
| backend/api/research.py | 1294 | `elif ... route_decision.workflow_kind == "position_followup":` | ✅ 已删除 |
| backend/api/research.py | 1625 | `elif session.workflow_kind == WorkflowKind.STRATEGY_IDEA:` | ✅ 已删除 |
| backend/api/research.py | 1741 | `elif session.workflow_kind == WorkflowKind.UNKNOWN:` | ✅ 已删除 |
| backend/api/research.py | 1259 | `workflow_type = session.workflow_kind.value` | ✅ 已替换为 `workflow_type = workflow_kind` |

**删除证明:**
```bash
cd /mnt/d/Codex/TraderLens
grep -n "if session.workflow_kind ==" backend/api/research.py
# 输出: (空) — 所有 session.workflow_kind 业务判断已删除
```

### 部分验证结果（2/9 通过）

```
Input                               | route_decision       | response.workflow_type    | Match | Expected             | Pass
--------------------------------------------------------------------------------------------------------------------------------------------
已买入100股成交价12.34                     | execution_feedback   | execution_feedback        | YES   | execution_feedback   | PASS
今天要不要继续拿                            | position_followup    | position_followup         | YES   | position_followup    | PASS
帮我看603002                            | ERROR: TypeError (handler 初始化参数错误)
```

**铁则验证:**
- ✅ `response.workflow_type == route_decision.workflow_kind`（前 2 个测试）
- ✅ 无 `session.workflow_kind` 覆盖

---

## 测试为

**命令:**
```bash
cd /mnt/d/Codex/TraderLens
.venv\Scripts\python.exe scripts\verify_p1_1_route_decision.py
```

**Exit code:** 1（失败，due to handler 初始化错误）

**语法检查:**
```bash
.venv\Scripts\python.exe -m py_compile backend/api/research.py          # ✅ 通过
.venv\Scripts\python.exe -m py_compile backend/api/workbench_handlers.py # ✅ 通过
```

---

## Commit Hash

**7ac0c6c** - refactor(P1-1): Route Decision single-source architecture (partial)

---

## 剩余工作（约 30% 工作量）

1. **修复 handler 初始化**（15%）
   - 修改 `handle_friend_stock()` 中 `FriendStockFlowService` 初始化
   - 从 `db_conn` 改为 `validator`, `serenity_runner`, `market_data_provider`
   - 类似修复其他 handlers

2. **完成验证脚本**（10%）
   - 运行完整 9 条输入测试
   - 贴原始 3 列表（route_decision | response.workflow_type | 是否相等）
   - 确保 exit code = 0

3. **Handler 非空壳证明**（5%）
   - execution_feedback: 贴 DB 记录 id
   - position_followup: 贴 open_position id

---

## 总结

**完成度:** 70%

**核心成果:**
- ✅ 删除 401 行旧逻辑（双重裁决源污染）
- ✅ 建立单一裁决源架构（`route_decision.workflow_kind` → handlers）
- ✅ 验证铁则：`execution_feedback` 和 `position_followup` 不再被覆盖为 `friend_stock`

**阻塞点:**
- ❌ Handler 初始化参数不匹配

**下一步:**
修复 `FriendStockFlowService` 和其他 service 的初始化参数，完成验证脚本。
