# Phase 2B-5 Checkpoint: research_memory_tool

**完成时间**: 2026-06-09

---

## 目标

实现 `search_research_memory` — 历史研究记录检索工具（MVP 占位实现）。

---

## 完成的工作

### 1. 历史记录检索工具 (`src/tools/research_memory_tool.py`)

**职责**: 检索历史研究记录（MVP 占位，返回空结果）

**核心功能**:
- 接受查询关键词和数量限制
- 返回统一格式的工具输出
- MVP 阶段返回空列表（found_count=0, records=[]）
- 生成唯一 ref_id 用于追踪

**输入参数**:
- `query`: 检索关键词（如 "平安银行"、"银行板块"）
- `limit`: 最大返回数量（默认 5）

**输出格式**（统一工具返回）:
```python
{
    "tool": "search_research_memory",
    "status": "success",
    "result": {
        "query": "平安银行",
        "limit": 5,
        "found_count": 0,
        "records": []  # 空列表，后续接入 RAG
    },
    "summary": "未找到相关历史记录: 平安银行",
    "signals": ["no_history"],
    "data_refs": {
        "ref_id": "memory_search_20260609_120000_abc123de",
        "source": "placeholder",
        "is_stale": false,
        "last_updated": "2026-06-09T12:00:00"
    },
    "error": null,
    "created_at": "2026-06-09T12:00:00"
}
```

**设计说明**:
- **占位实现**: MVP 阶段只返回空结果，不抛异常
- **结构化输出**: 符合统一工具返回格式，可以安全放入 observations
- **可扩展性**: Phase 3+ 只需替换 `result["records"]`，其他字段保持不变
- **唯一 ref_id**: 使用时间戳 + UUID，便于日志追踪

### 2. 集成到 Agent (`src/agent/executor.py`)

**修改内容**:
- 在 `_execute_tool()` 中添加 `search_research_memory` 分支
- 移除旧的 `research_memory_tool` mock 实现

**调用示例**:
```python
tool_input = {
    "query": "平安银行",
    "limit": 5
}
result = _execute_tool("search_research_memory", tool_input, state)
```

---

## 验收标准

✅ **1. 独立测试 research_memory_tool**
- 能正常接受查询参数
- 返回统一格式的工具输出
- found_count 为 0，records 为空列表

✅ **2. 不同查询都能正常返回**
- 测试多种查询（"平安银行"、"银行板块"、""）
- 每次调用都返回 success 状态
- 生成唯一 ref_id

✅ **3. Agent 集成正常**
- 可以通过 executor 调用
- 返回值可以安全放入 observations
- 不会导致 Agent 崩溃

✅ **4. 输出格式一致性**
- 包含所有必需字段（tool, status, result, summary, signals, data_refs, error, created_at）
- data_refs 包含 ref_id, source, is_stale, last_updated
- 与其他工具格式一致

---

## 测试结果

### 测试 1: 独立测试 research_memory_tool
```
✓ 检索完成
  - 状态: success
  - 查询: 平安银行
  - 找到记录数: 0
  - 记录列表: []
  - Summary: 未找到相关历史记录: 平安银行
  - Signals: ['no_history']
  - Ref ID: memory_search_20260608_192506_465ca7a2
  - Source: placeholder
```

### 测试 2: 不同查询测试
```
查询: '平安银行' - 状态: success, 找到: 0 条
查询: '银行板块' - 状态: success, 找到: 0 条
查询: '趋势策略' - 状态: success, 找到: 0 条
查询: '' - 状态: success, 找到: 0 条
```

### 测试 3: Agent 集成测试
```
✓ Agent 集成测试
  - 工具名称: search_research_memory
  - 状态: success
  - 可以安全放入 observations: True
```

### 测试 4: 输出格式一致性
```
验证输出字段:
  ✓ tool: str
  ✓ status: str
  ✓ result: dict
  ✓ summary: str
  ✓ signals: list
  ✓ data_refs: dict
  ✓ error: NoneType
  ✓ created_at: str

验证 data_refs 字段:
  ✓ ref_id: memory_search_20260608_192506_bd6d5d48
  ✓ source: placeholder
  ✓ is_stale: False
  ✓ last_updated: 2026-06-08T19:25:06.694719
```

---

## 关键设计决策

### 1. 占位实现而非抛异常

**选择**: 返回空结果（found_count=0, records=[]）而不是抛异常

**理由**:
- Agent 可以继续运行，不会因为"未找到历史记录"而崩溃
- 占位实现仍然提供有用信息（"未找到相关历史记录"）
- 便于调试和测试（不需要捕获异常）

### 2. 生成唯一 ref_id

**选择**: 使用时间戳 + UUID 生成唯一 ref_id

**理由**:
- 便于日志追踪（每次检索都有唯一标识）
- 便于后续审计（哪些查询被执行过）
- Phase 3+ 可以用 ref_id 关联缓存或数据库记录

### 3. 返回结构化 result

**选择**: result 包含 query, limit, found_count, records 四个字段

**理由**:
- 保留查询参数（query, limit）便于调试
- found_count 可以区分"未找到"和"找到但为空"
- records 是数组，便于后续扩展（每条记录包含 stock_code, date, summary 等）

### 4. 信号设计为单一 "no_history"

**选择**: 只返回一个信号 ["no_history"]

**理由**:
- MVP 阶段只有一种情况（未找到记录）
- Phase 3+ 可以扩展为多种信号（has_history, stale_history, partial_match 等）
- 保持简单，避免过度设计

---

## 后续扩展方向（Phase 3+）

### 1. 接入 SQLite research_history 表

**实现**:
```python
# 查询历史记录
conn = sqlite3.connect("traderlens.db")
cursor = conn.execute("""
    SELECT run_id, stock_code, goal, result_summary, created_at
    FROM research_history
    WHERE stock_code LIKE ? OR goal LIKE ?
    ORDER BY created_at DESC
    LIMIT ?
""", (f"%{query}%", f"%{query}%", limit))

records = [
    {
        "run_id": row[0],
        "stock_code": row[1],
        "goal": row[2],
        "summary": row[3],
        "date": row[4]
    }
    for row in cursor.fetchall()
]
```

### 2. 接入向量检索（Embedding + FAISS）

**实现**:
```python
# 1. 将 query 转换为 embedding
query_embedding = embedding_model.encode(query)

# 2. 在 FAISS 索引中检索最相似的记录
distances, indices = faiss_index.search(query_embedding, limit)

# 3. 从数据库中拉取完整记录
records = [get_record_by_id(idx) for idx in indices]
```

### 3. 增强信号生成

**扩展信号**:
- `has_history`: 找到历史记录
- `recent_history`: 找到近期记录（< 7 天）
- `stale_history`: 找到过期记录（> 30 天）
- `partial_match`: 部分匹配（相似度 < 0.8）
- `exact_match`: 完全匹配（相似度 > 0.95）

### 4. 支持多种检索模式

**模式**:
- `by_stock`: 按股票代码检索（如 "000001"）
- `by_sector`: 按板块检索（如 "银行板块"）
- `by_strategy`: 按策略检索（如 "趋势策略"）
- `by_date`: 按时间范围检索（如 "近 7 天"）

---

## 发现的问题

### 1. 无问题

所有测试一次通过，占位实现符合预期。

---

## 下一步

### Phase 3: Streamlit UI

**目标**: 实现 Tab 1 投研分析界面

**任务清单**:
1. `src/ui/app.py` - 主入口，Tab 导航
2. `src/ui/pages/research.py` - Tab 1 投研分析页面
   - 用户输入：goal, stock_code, strategy_profile
   - 启动按钮：调用 Agent Harness
   - 实时展示：decision_history（简单文本列表）
   - 人工确认：展示 next_action，批准/拒绝按钮
   - 最终结果：交易计划 + 观察池建议
3. Tab 2-5 占位页面（"功能开发中..."）
4. SQLite 初始化脚本（research_history 表）

**验收标准**:
1. 用户可以输入 goal 并启动 Agent
2. 决策链实时更新（每一步显示 thought + action + result）
3. 人工确认界面正常工作（中断 → 确认 → 继续）
4. 最终结果保存到 SQLite
5. UI 无崩溃，错误信息友好展示

---

## 技术债务

1. **向量检索优化**（Phase 3+）:
   - 使用 Sentence-Transformers 生成 embedding
   - 使用 FAISS 构建向量索引
   - 支持语义检索（如 "银行股" 匹配到 "平安银行"）

2. **缓存优化**（Phase 3+）:
   - 缓存常见查询结果（如 "平安银行" 的历史记录）
   - 使用 LRU 缓存避免重复查询数据库
   - 定期清理过期缓存

3. **检索质量优化**（Phase 3+）:
   - 支持模糊匹配（如 "平安" 匹配到 "平安银行"）
   - 支持同义词（如 "趋势" 匹配到 "动量"）
   - 支持多关键词组合（如 "平安银行 AND 趋势策略"）

4. **结果排序优化**（Phase 3+）:
   - 按时间排序（最新优先）
   - 按相似度排序（最相关优先）
   - 按重要性排序（观察池加入 > 普通分析）

---

## 文件清单

### 新增文件

- `src/tools/research_memory_tool.py` - 历史记录检索工具（占位实现）
- `test_phase2b5.py` - Phase 2B-5 验收测试
- `docs/checkpoints/phase2b5-checkpoint.md` - 本文档

### 修改文件

- `src/agent/executor.py` - 集成 `search_research_memory`，移除旧 mock

---

## Phase 2 完成状态

- Phase 1: ✅ 完成（Agent 循环、interrupt、安全检查）
- Phase 2A: ✅ 完成（3 个核心工具 + 真实逻辑）
- Phase 2A+: ✅ 完成（缓存、mock 模式、data_refs）
- Phase 2B-1: ✅ 完成（watchlist_tool + 人工确认流程）
- Phase 2B-2: ✅ 完成（backtest_tool + 回测引擎）
- Phase 2B-3: ✅ 完成（sector_strength_tool + 板块分析）
- Phase 2B-4: ✅ 完成（fundamentals_tool + JudgmentEngine）
- **Phase 2B-5: ✅ 完成（research_memory_tool 占位实现）**

**Phase 2 工具层全部完成！**

---

## Phase 2 工具总览

| 工具 | 状态 | 说明 |
|------|------|------|
| `market_regime_tool` | ✅ 真实 | 市场环境评估（指数技术分析） |
| `technicals_tool` | ✅ 真实 | 技术面分析（MA, RSI, 成交量） |
| `trade_plan_tool` | ✅ 真实 | 生成交易计划（入场/止损/止盈） |
| `watchlist_tool` | ✅ 真实 | 加入观察池（需人工确认） |
| `backtest_tool` | ✅ 真实 | 策略回测（逐日模拟） |
| `sector_strength_tool` | ✅ 真实 | 板块强度分析（板块表现 + 个股排名） |
| `analyze_stock_fundamentals` | ✅ 真实 | 基本面分析（JudgmentEngine 评分） |
| `search_research_memory` | ✅ 占位 | 历史记录检索（MVP 返回空） |

**8 个工具全部实现，7 个真实 + 1 个占位！**

---

**最后更新**: 2026-06-09
