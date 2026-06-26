# Serenity 双阶段重构实施方案

**创建日期**: 2026-06-25  
**目标**: 将 Serenity 从多轮 LLM 工具调用改为双阶段 LLM + 确定性执行器  
**当前基线**: 768 tests OK (skipped=2), 0 frontend errors

---

## 一、重构目标与约束

### 1.1 核心目标
- **单次 run 最多 2 次 LLM 调用**（Planner + Synthesizer）
- **最大并发数 = 2**（包括 LLM 和数据工具）
- **所有门禁由确定性代码完成**
- **保留已完成的 verification trust chain 和 run_context**

### 1.2 硬约束
```python
MAX_LLM_CALLS_PER_RUN = 2
MAX_CONCURRENCY = 2
```

- 禁止七个工具各触发一次 LLM 往返
- 数据查询、ticker 核验、来源审计、shortlist 门禁必须确定性
- 不继续开发 Criteria Reviewer、市场扫描、UI
- 不修改 B/C 模块和 strategy_core

### 1.3 接口兼容性
- `SerenityAgentRunner` 继续实现 `SerenityRunner` 接口
- 返回现有 `SerenityOutput`
- 不修改 `EvidenceItem`、`EvidenceOutput`、`ConfirmedCandidate`
- 不直接写数据库
- 候选通过 `ProposedAction → reducer → DB` 路径

---

## 二、架构设计

### 2.1 双阶段流程

```
┌─────────────────────────────────────────────────────────────┐
│ LLM 调用 1: Research Planner                                 │
│ 输入: 主题、背景、研究模式、人工候选                          │
│ 输出: ResearchPlan (keywords, seed_symbols, sectors, etc.)   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 确定性执行器 (Deterministic Executor)                         │
│ - 并发查询数据 (max_concurrency=2)                           │
│ - 保存真实 ResearchSource                                    │
│ - 发现玩家                                                    │
│ - 批量 verify_ticker (max_concurrency=2)                     │
│ - 来源质量检查                                               │
│ - red-team gaps                                              │
│ - 建立 VerifiedResearchCandidate                             │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ LLM 调用 2: Research Synthesizer                             │
│ 输入: 已验证和脱敏的研究包                                    │
│ 输出: ResearchSynthesis (demand_driver, layers, etc.)        │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ 确定性门禁 (Deterministic Gate)                              │
│ - 验证所有 source IDs                                        │
│ - 验证候选身份                                               │
│ - 验证来源质量                                               │
│ - 验证 red-team                                              │
│ - 生成 candidate_shortlist                                   │
│ - 输出 SerenityOutput                                        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 为什么仍是 Goal-Driven

**固定的是安全外壳，不是研究内容。**

Research Planner 根据主题动态决定：
- 使用哪些关键词
- 查询哪些 seed symbols
- 查询哪些行业
- 查询时间范围
- 需要证伪哪些问题

**不同主题应产生不同的 ResearchPlan**，因此仍是 goal-driven。

---

## 三、数据结构设计

### 3.1 ResearchPlan（Planner 输出）

```python
@dataclass
class ResearchPlan:
    """Research Planner 的结构化输出"""
    keywords: list[str]  # 最多 20 个
    seed_symbols: list[str]  # 最多 10 个
    sectors_to_check: list[str]  # 最多 5 个
    start_date: str | None  # YYYYMMDD
    end_date: str | None  # YYYYMMDD
    falsification_questions: list[str]  # 最多 10 个
```

**验证规则：**
- 必须通过 Pydantic 严格校验
- 无效 JSON 或 schema → 明确失败
- seed_symbols 不是已验证玩家，只是检索起点
- 未产生真实来源的 seed 不得进入候选

### 3.2 VerifiedResearchCandidate

```python
@dataclass
class VerifiedResearchCandidate:
    """已完成身份核验的研究候选"""
    symbol: str
    company_name: str  # 来自 verification record
    verification_id: str
    exchange: str
    listing_status: str
    confidence: str  # high/medium
    supporting_source_ids: list[str]  # 必须非空
    red_team_findings: list[str]
    unresolved_gaps: list[str]
```

**约束：**
- confidence 不能为 low
- listing_status 不能为 unknown
- supporting_source_ids 至少一个非 weak

### 3.3 SerenityRunContext

```python
@dataclass
class SerenityRunContext:
    """单次 run 的确定性运行上下文"""
    sources_by_id: dict[str, ResearchSource]
    verified_candidates_by_symbol: dict[str, VerifiedResearchCandidate]
    completed_checks: set[str]  # {"source_audit", "red_team"}
```

**规则：**
- 每次 run() 创建新 context
- 禁止跨 run 共享
- 不写数据库
- source ID 只能索引真实对象
- 禁止通过 source ID 临时重建假对象

### 3.4 ResearchSynthesis（Synthesizer 输出）

```python
@dataclass
class ResearchSynthesis:
    """Research Synthesizer 的结构化输出"""
    demand_driver: str
    value_chain_layers: list[dict]
    suspected_bottleneck_layers: list[dict]
    hypothesis_draft: list[dict]
    candidate_rationales: dict[str, str]  # symbol → rationale
    evidence_gaps: list[str]
```

**约束：**
- 每个 bottleneck 和 hypothesis 必须携带 supporting_source_ids
- 输出后确定性代码验证所有 ID
- 不存在的 ID → 直接拒绝

---

## 四、实施步骤

### Step 2: 完成最小 SerenityRunContext

**目标：** 删除假来源重建，建立真实运行上下文

**修改文件：**
- `backend/services/serenity_agent.py`

**具体任务：**
1. 在 `backend/services/serenity_agent.py` 中添加 `SerenityRunContext` dataclass
2. 确认 `_reconstruct_sources` 已删除（第二优先级已完成）
3. 确认 `run_context` 在 `_run_agent` 中已建立（第二优先级已完成）
4. 添加 `VerifiedResearchCandidate` dataclass

**验证：**
- 运行 `tests.test_serenity_e2e_context` 确认 context 正常工作

### Step 3: 实现 Research Planner

**目标：** 第一次 LLM 调用，生成结构化研究计划

**新增文件：**
- `backend/services/serenity_planner.py`

**具体实现：**

```python
# backend/services/serenity_planner.py

from dataclasses import dataclass
from pydantic import BaseModel, Field

class ResearchPlanSchema(BaseModel):
    """Pydantic schema for Research Planner output"""
    keywords: list[str] = Field(max_length=20)
    seed_symbols: list[str] = Field(max_length=10)
    sectors_to_check: list[str] = Field(max_length=5)
    start_date: str | None = None
    end_date: str | None = None
    falsification_questions: list[str] = Field(max_length=10)

@dataclass
class ResearchPlan:
    keywords: list[str]
    seed_symbols: list[str]
    sectors_to_check: list[str]
    start_date: str | None
    end_date: str | None
    falsification_questions: list[str]

class ResearchPlanner:
    """Generate structured research plan from theme"""
    
    SYSTEM_PROMPT = """You are a Research Planner. Generate a structured research plan.
    
OUTPUT SCHEMA:
{
  "keywords": ["关键词1", "关键词2"],
  "seed_symbols": ["300750.SZ", "600519.SH"],
  "sectors_to_check": ["电气设备", "食品饮料"],
  "start_date": "20230101",
  "end_date": "20260624",
  "falsification_questions": ["问题1", "问题2"]
}

RULES:
- keywords: 最多 20 个
- seed_symbols: 最多 10 个（这些是检索起点，不是已验证玩家）
- sectors_to_check: 最多 5 个
- falsification_questions: 最多 10 个
- 日期格式必须是 YYYYMMDD
- 不要输出 buy/sell/target/stop/position
"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def plan(self, theme: ThemeInput, manual_candidates: list[CandidateStock]) -> ResearchPlan:
        """Generate research plan from theme"""
        
        prompt = f"""研究主题: {theme.theme_name}
背景: {theme.background}
研究模式: {theme.research_mode}
已有人工候选: {', '.join(c.symbol for c in manual_candidates)}

请生成研究计划。"""
        
        response = self.llm_client.create_message(
            messages=[{"role": "user", "content": prompt}],
            system=self.SYSTEM_PROMPT,
            max_tokens=1024,
        )
        
        # Extract and validate JSON
        text = self._extract_text(response)
        plan_dict = self._parse_json(text)
        
        # Pydantic validation
        schema = ResearchPlanSchema(**plan_dict)
        
        return ResearchPlan(
            keywords=schema.keywords,
            seed_symbols=schema.seed_symbols,
            sectors_to_check=schema.sectors_to_check,
            start_date=schema.start_date,
            end_date=schema.end_date,
            falsification_questions=schema.falsification_questions,
        )
```

**修改 `serenity_agent.py`：**
- 在 `_run_agent` 开头调用 `ResearchPlanner.plan()`
- 记录 LLM 调用 1/2

**测试：**
新增 `tests/test_serenity_planner.py`：
- `test_planner_produces_valid_schema`
- `test_planner_malformed_json_fails`
- `test_different_themes_produce_different_plans`

### Step 4: 实现确定性数据检索和 ticker 核验

**目标：** 根据 ResearchPlan 并发执行数据查询（max_concurrency=2）

**新增文件：**
- `backend/services/serenity_executor.py`

**具体实现：**

```python
# backend/services/serenity_executor.py

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

MAX_RESEARCH_CONCURRENCY = 2

class DeterministicExecutor:
    """Execute research plan with deterministic data retrieval"""
    
    def __init__(self, data_tools, validator, db):
        self.data_tools = data_tools
        self.validator = validator
        self.db = db
        self.executor = ThreadPoolExecutor(max_workers=MAX_RESEARCH_CONCURRENCY)
    
    def execute(
        self, 
        plan: ResearchPlan, 
        context: SerenityRunContext,
        audit: SerenityAgentAudit,
    ) -> None:
        """Execute research plan and populate context"""
        
        # Step 1: 并发数据检索（max_concurrency=2）
        self._retrieve_data(plan, context, audit)
        
        # Step 2: 发现玩家
        self._discover_players(context)
        
        # Step 3: 批量 verify_ticker（max_concurrency=2）
        self._verify_tickers(context, audit)
        
        # Step 4: 来源审计
        self._audit_sources(context, audit)
        
        # Step 5: red-team
        self._red_team(context, audit)
    
    def _retrieve_data(self, plan, context, audit):
        """并发检索数据，最大并发 2"""
        tasks = []
        
        # 为每个 seed symbol 创建检索任务
        for symbol in plan.seed_symbols[:10]:
            tasks.append(("financials", symbol))
            tasks.append(("announcements", symbol, plan.keywords))
            tasks.append(("sector", symbol))
        
        # 使用 ThreadPoolExecutor 限制并发
        for i in range(0, len(tasks), MAX_RESEARCH_CONCURRENCY):
            batch = tasks[i:i+MAX_RESEARCH_CONCURRENCY]
            futures = []
            
            for task in batch:
                if task[0] == "financials":
                    future = self.executor.submit(
                        self.data_tools.get_financials, task[1]
                    )
                elif task[0] == "announcements":
                    future = self.executor.submit(
                        self.data_tools.get_announcements, 
                        task[1], keywords=task[2]
                    )
                elif task[0] == "sector":
                    future = self.executor.submit(
                        self.data_tools.get_sector_and_peers, task[1]
                    )
                futures.append((task, future))
            
            # 等待批次完成
            for task, future in futures:
                try:
                    result = future.result(timeout=30)
                    self._save_sources(result, context, audit)
                except Exception as exc:
                    audit.errors.append(f"Data retrieval failed: {task} - {exc}")
    
    def _save_sources(self, result: DataToolResult, context, audit):
        """保存真实 ResearchSource 到 context"""
        # 实现逻辑：从 DataToolResult 创建 ResearchSource
        pass
    
    def _verify_tickers(self, context, audit):
        """批量 verify_ticker，最大并发 2"""
        symbols = self._extract_symbols_from_sources(context)
        
        for i in range(0, len(symbols), MAX_RESEARCH_CONCURRENCY):
            batch = symbols[i:i+MAX_RESEARCH_CONCURRENCY]
            futures = []
            
            for symbol in batch:
                future = self.executor.submit(
                    self.validator.verify_ticker, symbol
                )
                futures.append((symbol, future))
            
            for symbol, future in futures:
                try:
                    verification = future.result(timeout=10)
                    self._create_verified_candidate(symbol, verification, context, audit)
                except Exception as exc:
                    audit.errors.append(f"verify_ticker failed: {symbol} - {exc}")
```

**测试：**
新增 `tests/test_serenity_executor.py`：
- `test_max_concurrency_is_2`
- `test_single_tool_failure_does_not_cancel_others`
- `test_real_sources_saved_to_context`
- `test_seed_without_real_source_rejected`

### Step 5: 实现来源审计和 red-team

**目标：** 确定性代码完成来源质量检查和 red-team gaps

**在 `serenity_executor.py` 中实现：**

```python
def _audit_sources(self, context, audit):
    """确定性来源审计"""
    
    # 全局检查
    has_first_hand = any(
        s.source_quality == "first_hand" 
        for s in context.sources_by_id.values()
    )
    if not has_first_hand:
        audit.errors.append("source_audit: no first_hand sources")
    
    # 候选级检查
    for symbol, candidate in context.verified_candidates_by_symbol.items():
        # 检查来源是否存在
        missing_sources = [
            sid for sid in candidate.supporting_source_ids
            if sid not in context.sources_by_id
        ]
        if missing_sources:
            audit.errors.append(
                f"source_audit: {symbol} references non-existent sources: {missing_sources}"
            )
            # 移除该候选
            del context.verified_candidates_by_symbol[symbol]
            continue
        
        # 检查是否全部为 weak
        sources = [context.sources_by_id[sid] for sid in candidate.supporting_source_ids]
        all_weak = all(s.source_quality == "weak" for s in sources)
        if all_weak:
            candidate.unresolved_gaps.append("all_sources_weak")
        
        # 检查是否过期
        # ... 实现过期检查
    
    context.completed_checks.add("source_audit")

def _red_team(self, context, audit):
    """确定性 red-team gaps"""
    
    # 全局 gaps
    if len(context.verified_candidates_by_symbol) < 3:
        audit.errors.append("red_team: insufficient player coverage")
    
    # 候选级 red-team
    for symbol, candidate in context.verified_candidates_by_symbol.items():
        sources = [context.sources_by_id[sid] for sid in candidate.supporting_source_ids]
        
        # 数据缺口
        has_financials = any("financials:" in s.source_record_id for s in sources)
        if not has_financials:
            candidate.red_team_findings.append("no_financial_data")
        
        has_announcements = any("announcements:" in s.source_record_id for s in sources)
        if not has_announcements:
            candidate.red_team_findings.append("no_announcement_data")
        
        # 行业缺失
        has_sector = any("sector:" in s.source_record_id for s in sources)
        if not has_sector:
            candidate.red_team_findings.append("no_sector_data")
    
    # 默认警告（不作为硬阻断）
    audit.errors.append("red_team: private_players_not_checked")
    audit.errors.append("red_team: subsidiaries_not_checked")
    audit.errors.append("red_team: acquired_or_delisted_not_checked")
    
    context.completed_checks.add("red_team")
```

**测试：**
- `test_audit_detects_all_weak_sources`
- `test_audit_detects_missing_source_ids`
- `test_red_team_detects_data_gaps`
- `test_audit_and_red_team_mark_completed`

### Step 6: 实现 Research Synthesizer

**目标：** 第二次 LLM 调用，整合研究结果

**新增文件：**
- `backend/services/serenity_synthesizer.py`

**具体实现：**

```python
# backend/services/serenity_synthesizer.py

class ResearchSynthesizer:
    """Synthesize research findings into structured output"""
    
    SYSTEM_PROMPT = """You are a Research Synthesizer. Produce structured research synthesis.

OUTPUT SCHEMA:
{
  "demand_driver": "需求驱动因素",
  "value_chain_layers": [
    {"layer": "上游", "description": "..."}
  ],
  "suspected_bottleneck_layers": [
    {"layer": "中游", "reason": "...", "supporting_source_ids": ["financials:300750.SZ:0"]}
  ],
  "hypothesis_draft": [
    {"hypothesis": "...", "rationale": "...", "confidence": "medium"}
  ],
  "candidate_rationales": {
    "300750.SZ": "产业链核心环节"
  },
  "evidence_gaps": ["需要验证产能扩张计划"]
}

RULES:
- 每个 bottleneck 和 hypothesis 必须携带 supporting_source_ids
- candidate_rationales 的 key 必须是已验证的 symbol
- 不要创造公司名、ticker、财务数字
- 不要输出 buy/sell/target/stop/position
"""
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
    
    def synthesize(
        self,
        theme: ThemeInput,
        context: SerenityRunContext,
        audit: SerenityAgentAudit,
    ) -> ResearchSynthesis:
        """Synthesize research findings"""
        
        # 构建压缩后的研究包
        research_pack = self._build_research_pack(theme, context)
        
        response = self.llm_client.create_message(
            messages=[{"role": "user", "content": research_pack}],
            system=self.SYSTEM_PROMPT,
            max_tokens=2048,
        )
        
        text = self._extract_text(response)
        synthesis_dict = self._parse_json(text)
        
        # 验证所有 source IDs 存在
        self._validate_source_ids(synthesis_dict, context, audit)
        
        return ResearchSynthesis(**synthesis_dict)
    
    def _build_research_pack(self, theme, context):
        """构建压缩的研究包（不发送原始数据）"""
        pack = {
            "theme": theme.theme_name,
            "background": theme.background,
            "verified_candidates": [],
            "source_summary": [],
            "audit_gaps": [],
            "red_team_gaps": [],
        }
        
        # 只发送已验证候选的摘要
        for symbol, candidate in context.verified_candidates_by_symbol.items():
            pack["verified_candidates"].append({
                "symbol": symbol,
                "company_name": candidate.company_name,
                "source_ids": candidate.supporting_source_ids,
            })
        
        # 只发送来源类型和质量
        for sid, source in context.sources_by_id.items():
            pack["source_summary"].append({
                "id": sid,
                "type": source.source_type,
                "quality": source.source_quality,
            })
        
        return json.dumps(pack, ensure_ascii=False)
```

**修改 `serenity_agent.py`：**
- 在 executor 完成后调用 `ResearchSynthesizer.synthesize()`
- 记录 LLM 调用 2/2

**测试：**
新增 `tests/test_serenity_synthesizer.py`：
- `test_synthesizer_validates_source_ids`
- `test_synthesizer_rejects_non_existent_ids`
- `test_synthesizer_malformed_json_fails`

继续下一块...
