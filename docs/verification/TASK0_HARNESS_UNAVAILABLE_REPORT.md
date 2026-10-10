# Task 0 主链浏览器验收 — Harness 不可用报告

**Report Date:** 2026-07-14  
**Status:** `task0_harness_unavailable`  
**Authorization:** 只读审计，不修改，不执行

---

## 执行结果

**停止原因:** 现有harness (`scripts/verify_credible_manual_trade_closure.py`) 覆盖范围不符合主链要求。

**任务约束明确声明:**
> "核对现有 harness 是否真的覆盖这一条唯一链路：自然语言朋友荐股 → ResearchCase → 用户产业链假设与事实/反证 → continue → confirmed_candidate_pool → **已独立验证策略的 signal** → **Market Guard** → **Action Plan** → **用户确认买入** → **Observation Pool** → **Daily Signal** → **用户确认卖出** → **P&L** → **Discipline Review**。"

> "若 harness 缺失、只跑到 candidate pool、使用 fake/synthetic 业务结果、直接插库、API-only 替代浏览器、或无法在单 worker runtime 启动，则立即停止并报告 task0_harness_unavailable；**不得修 harness、不得补任何下游模块。**"

---

## 现有Harness分析

### 文件
`scripts/verify_credible_manual_trade_closure.py` (429 lines)

### 实际覆盖范围

**已覆盖（lines 141-320）:**
1. ✓ 朋友推荐 → ResearchCase (lines 141-186)
2. ✓ 用户产业链假设（待验证）持久化 (lines 207-232)
3. ✓ 真实研究（LLM + Tushare）→ 事实/反证/数据缺口 (lines 234-270)
4. ✓ 用户显式 continue → confirmed_candidate_pool (lines 282-320)

**缺失（无代码实现）:**
5. ✗ **已独立验证策略的 signal** — 无检索、无匹配、无signal生成
6. ✗ **Market Guard** — 无guard check、无regime detection、无block_new_entry
7. ✗ **Action Plan** — 无plan创建、无资金分配、无风险计算
8. ✗ **用户确认买入** — 无buy confirmation、无execution log
9. ✗ **Observation Pool** — 无position tracking、无daily observation
10. ✗ **Daily Signal** — 无exit signal生成
11. ✗ **用户确认卖出** — 无sell confirmation、无exit execution
12. ✗ **P&L** — 无return calculation、无realized P&L
13. ✗ **Discipline Review** — 无review、无attribution、无反思

### Harness终点

**Last step (line 320):**
```python
print("[4] Explicit continue -> forward-only confirmed_candidate_pool created via deterministic reducer")
print("    forward_only=True, is_buy_signal=False, is_backtest_universe=False")
```

**Success条件 (lines 354-376):**
```python
"## Chain verified\n"
"1. 朋友推荐 → ResearchCase\n"
"2. 用户产业链假设（待验证）原样持久化\n"
"3. 真实研究（LLM + Tushare）生成可追溯事实/反证/数据缺口\n"
"4. 用户显式 continue → 前向唯一 confirmed_candidate_pool（非买入信号、非回测 universe）\n"
```

**明确标记 (line 378):**
```python
print("✅ Task 2 完整验收通过（真实 LLM + Tushare，前向唯一候选池）")
```

### 覆盖率

**主链步骤:** 13  
**已覆盖:** 4  
**覆盖率:** 30.8%  

**缺失业务环节:**
- 策略验证与signal生成 (steps 5)
- Market Guard与Action Plan (steps 6-7)
- 买入确认与execution (step 8)
- Observation Pool (step 9)
- Daily Signal与卖出确认 (steps 10-11)
- P&L与Discipline Review (steps 12-13)

---

## 现有Acceptance报告分析

### 文件
`docs/verification/CREDIBLE_PRODUCT_ACCEPTANCE.md`

### 内容

```markdown
# Credible Product Acceptance — Task 0 (extended)

**Run ID:** `CREDIBLE_RUN_20260711_103419`
**Status:** ✅ PASS

## Chain verified
1. 朋友推荐 → ResearchCase (`case_d2ca7ac4c219`)
2. 用户产业链假设（待验证）原样持久化
3. 真实研究（LLM + Tushare）生成可追溯事实/反证/数据缺口
4. 用户显式 continue → 前向唯一 confirmed_candidate_pool（非买入信号、非回测 universe）

## Real LLM calls: 2 (range [1,3] OK)
## Tushare source IDs: ['financials:600519.SH:0', ...]
## Timings (s): {...}
## Total wall: 95.95s | user-wait excluded: 6.0s | productive: 89.95s

## Evidence
- `credible_1_workbench.html`
- `credible_2_research_detail.html`
- `credible_3_hypothesis.html`
- `credible_4_research.html`
- `credible_5_pool.html`
- `credible_success.json`
- `credible_backend_stdout.log`
```

**状态声明:** ✅ PASS  
**覆盖范围:** 只到confirmed_candidate_pool  
**后续步骤:** 无

---

## 主计划Task 0要求对比

### 主计划 (docs/superpowers/plans/...plan.md, lines 137-156)

**Task 0: Write and run the one failing browser acceptance chain**

**Acceptance (line 155):**
> "the initial run fails loudly at its actual first missing product step; **it does not split into friend/strategy/execution scripts** or label a partial path as E2E."

**链路要求 (lines 144-149):**
```text
朋友推荐 XX
→ ResearchCase → user chain hypothesis + facts/counter-evidence → approval
→ confirmed_candidate_pool → separately validated strategy signal
→ Market Guard → Action Plan → confirm buy → Observation Pool
→ Daily Signal → confirm sell → P&L → Discipline Review
```

**明确要求 (line 151):**
> "It creates no synthetic market rows, template results, signals, executions, or reviews. **Missing Gate 0 input fails with the exact first missing business step.**"

### 现有Harness行为

**实际行为:**
- ✓ 真实浏览器 (Playwright)
- ✓ 真实LLM (2 calls, telemetry verified)
- ✓ 真实Tushare (source IDs recorded)
- ✓ 单worker backend (--workers 1)
- ✓ 无direct DB insert
- ✓ 无synthetic market/template/signal/execution/review

**违反要求:**
- ✗ **只跑到candidate pool** (30.8%覆盖)
- ✗ **标记为"✅ PASS"** (应为first failure)
- ✗ **未尝试signal/guard/plan/execution/observation/P&L/review步骤**
- ✗ **未记录first missing business step**

**主计划期望:**
> "fails loudly at its actual first missing product step"

**现有harness实际:**
> "✅ Task 2 完整验收通过"

---

## 判定依据

### 主计划明确停止条件 (任务约束)

> "若 harness 缺失、**只跑到 candidate pool**、使用 fake/synthetic 业务结果、直接插库、API-only 替代浏览器、或无法在单 worker runtime 启动，则立即停止并报告 task0_harness_unavailable"

**现状匹配:** ✓ "只跑到 candidate pool"

### 修复禁止 (任务约束)

> "不得修 harness、不得补任何下游模块。"

**执行:** ✓ 未修改任何文件

---

## 结论

**状态:** `task0_harness_unavailable`

**原因:** 现有harness只覆盖主链前30.8%步骤（到confirmed_candidate_pool），缺失：
- 策略验证与signal生成
- Market Guard
- Action Plan
- 买入确认与execution
- Observation Pool
- Daily Signal
- 卖出确认
- P&L
- Discipline Review

**主链验收状态:** 无法完成  
**First product blocker:** 无法确定（harness未到达任何下游业务阻断点）

**当前validation状态:** `validation_unavailable` (unchanged)

---

## 建议

**修复harness需独立任务:**
1. 扩展`verify_credible_manual_trade_closure.py`以覆盖完整13步主链
2. 从confirmed_candidate_pool继续到signal → guard → plan → buy → observe → sell → P&L → review
3. 在第一个真实业务阻断点停止（不跳过、不模拟、不synthetic）
4. 记录唯一`first_product_blocker`及证据
5. 重新运行并生成完整验收报告

**当前任务明确禁止修复。**

---

**Report end.**
