# TraderLens MVP v0.1 实现计划

**目标**：构建 Goal-driven ReAct Agent Harness，验证架构可行性

**预计时间**：5-8 天

---

## Phase 1: Agent 核心（1-2 天）

### 目标
验证 LangGraph 主图 + 5 个节点的循环逻辑和人工中断

### 任务清单
- [ ] `src/agent/state.py` - AgentState 类型定义
- [ ] `src/agent/config.py` - 硬限制配置（MAX_STEPS、MUST_REVIEW_TOOLS）
- [ ] `src/agent/context_builder.py` - 整理上下文
- [ ] `src/agent/reasoner.py` - LLM 推理（先用硬编码返回）
- [ ] `src/agent/executor.py` - 工具执行器（工具返回 mock 数据）
- [ ] `src/agent/quality_gate.py` - 6 个安全检查
- [ ] `src/agent/human_review.py` - 人工确认节点
- [ ] `src/agent/harness.py` - LangGraph 主图编译
- [ ] 最简端到端 demo（硬编码工具，验证循环）

### 验收标准
- ✅ LangGraph 主图可以运行
- ✅ Agent 循环 3-5 步后完成
- ✅ decision_history 正确记录每一步
- ✅ 人工确认点可以中断和恢复
- ✅ 硬限制生效（最大步数、重复调用检测）

### Checkpoint 文档
`docs/checkpoints/phase1-checkpoint.md`
- 完成状态
- 发现的问题
- 解决方案
- 下一步优化点

---

## Phase 2: 工具层（2-3 天）

### 目标
实现 8 个工具，包装核心模块，统一输出格式

### 任务清单
- [ ] `src/tools/market_regime_tool.py` - 评估市场环境
- [ ] `src/tools/sector_strength_tool.py` - 分析板块强度
- [ ] `src/tools/fundamentals_tool.py` - 基本面分析
- [ ] `src/tools/technicals_tool.py` - 技术面分析
- [ ] `src/tools/backtest_tool.py` - 策略回测
- [ ] `src/tools/trade_plan_tool.py` - 生成交易计划
- [ ] `src/tools/watchlist_tool.py` - 加入观察池
- [ ] `src/tools/research_memory_tool.py` - 检索历史记录（占位）
- [ ] 错误处理：所有工具捕获异常，返回 error 状态
- [ ] 日志记录：每个工具记录调用参数和结果
- [ ] 统一输出格式验证

### 验收标准
- ✅ 8 个工具可以独立运行（单元测试）
- ✅ 所有工具返回统一格式（tool、status、message、data、data_ref、timestamp）
- ✅ 错误情况不抛异常，返回 error 状态
- ✅ 日志记录完整（INFO 级别记录调用，DEBUG 级别记录详细数据）
- ✅ Mock 底层模块的单元测试通过

### Checkpoint 文档
`docs/checkpoints/phase2-checkpoint.md`

---

## Phase 3: Streamlit UI（1-2 天）

### 目标
Tab 1 投研分析界面，展示决策链，人工确认

### 任务清单
- [ ] `src/ui/app.py` - 主入口，Tab 导航
- [ ] `src/ui/pages/research.py` - Tab 1 投研分析
  - [ ] 用户输入：goal、stock_code、strategy_profile
  - [ ] 启动按钮：调用 Agent Harness
  - [ ] 实时展示：decision_history（简单文本列表）
  - [ ] 人工确认：展示 next_action，批准/拒绝按钮
  - [ ] 最终结果：交易计划 + 观察池建议
- [ ] Tab 2-5 占位页面（"功能开发中..."）
- [ ] SQLite 初始化脚本（research_history 表）

### 验收标准
- ✅ 用户可以输入 goal 并启动 Agent
- ✅ 决策链实时更新（每一步显示 thought + action + result）
- ✅ 人工确认界面正常工作（中断 → 确认 → 继续）
- ✅ 最终结果保存到 SQLite
- ✅ UI 无崩溃，错误信息友好展示

### Checkpoint 文档
`docs/checkpoints/phase3-checkpoint.md`

---

## Phase 4: 集成测试（1 天）

### 目标
端到端测试，修复 bug，优化 prompt

### 任务清单
- [ ] 端到端测试用例：
  - [ ] 正常流程：用户输入 → Agent 执行 → 人工确认 → 保存结果
  - [ ] 错误场景：API 失败、超过最大步数、重复调用工具
  - [ ] 中断恢复：人工确认拒绝、LangGraph checkpoint 恢复
- [ ] Bug 修复：根据测试发现的问题修复
- [ ] Prompt 优化：
  - [ ] AgentReasoner 的 prompt 优化（让 LLM 更好地选择工具）
  - [ ] 工具描述优化（让 LLM 理解工具用途）
- [ ] 性能优化：缓存、并发、日志级别调整

### 验收标准
- ✅ 端到端测试全部通过
- ✅ 人工确认点正常工作（中断、恢复、拒绝）
- ✅ 错误场景正确处理（不崩溃，返回友好提示）
- ✅ Agent 可以完成完整投研流程（5-7 步）
- ✅ 决策链记录完整且可读

### Checkpoint 文档
`docs/checkpoints/phase4-checkpoint.md`

---

## 最终交付物

### 代码
- ✅ `src/agent/` - 5 个节点 + harness + config
- ✅ `src/tools/` - 8 个工具（1 个占位）
- ✅ `src/core/` - 核心模块（DataFetcher、JudgmentEngine、BacktestEngine）
- ✅ `src/ui/` - Streamlit UI（Tab 1 完整，Tab 2-5 占位）
- ✅ `tests/` - 单元测试 + 集成测试

### 文档
- ✅ `README.md` - 项目简介
- ✅ `AGENTS.md` - 开发规范
- ✅ `PROJECT_STRUCTURE.md` - 文件结构说明
- ✅ `docs/specs/2026-06-08-traderlens-agent-design.md` - 设计文档
- ✅ `docs/checkpoints/phase1-4-checkpoint.md` - 实现记录

### 验收标准
1. 用户输入："分析平安银行能不能进观察池"
2. Agent 自主调用 5-7 个工具
3. 决策链完整记录到 SQLite
4. 人工确认后保存到观察池
5. UI 流畅无崩溃

---

## 风险与应对

| 风险 | 应对方案 |
|------|---------|
| LangChain Agent 推理不稳定 | Phase 1 先用硬编码，Phase 2-3 再接 LLM |
| 工具输出格式不一致 | Phase 2 严格验证统一格式 |
| Streamlit 中断恢复逻辑复杂 | 使用 LangGraph checkpoint，简化 UI 逻辑 |
| 数据源 API 不稳定 | 错误处理 + 缓存 + 重试机制 |

---

## 下一步

**Phase 1 开始**：实现 AgentState + 5 个节点 + 最简 demo

**问题**：你准备好开始 Phase 1 了吗？需要我先帮你实现哪个文件？

建议顺序：
1. `src/agent/state.py` - 定义 AgentState
2. `src/agent/config.py` - 硬限制配置
3. `src/agent/context_builder.py` - 最简单的节点
4. `src/agent/quality_gate.py` - 安全检查
5. `src/agent/executor.py` - 工具执行器（硬编码返回）
6. `src/agent/reasoner.py` - LLM 推理（硬编码决策）
7. `src/agent/human_review.py` - 人工确认
8. `src/agent/harness.py` - LangGraph 主图
9. 最简 demo 脚本

---

**最后更新**: 2026-06-08
