# Part 4: 数据适配层 + Web 页面设计

## 4.1 数据适配层设计

**定位**：封装 Tushare Pro API，提供统一数据接口，支持本地缓存、数据质量标记、退市股票保留。

### 模块架构

```
backend/tools/
  ├── data_adapter.py        # 统一数据接口
  ├── tushare_client.py      # Tushare Pro 封装
  ├── cache_manager.py       # 本地缓存管理（SQLite metadata + Parquet 文件）
  ├── data_quality.py        # 数据质量检查和标记
  ├── stock_identity.py      # 股票身份查询（上市/退市/交易所/名称）
  ├── market_data.py         # 行情数据（OHLCV、成交额）
  ├── daily_status.py        # 每日状态（ST、停牌、涨跌停）
  ├── financials.py          # 财务数据（ann_date 对齐）
  ├── announcements.py       # 公告数据
  ├── indicators.py          # 技术指标计算
  └── calendar.py            # 交易日历
```

### 缓存架构设计

**关键修正**：不使用 pickle BLOB，改用 Parquet + SQLite metadata

**目录结构**：

```
data/cache/
  ├── daily_bars/
  │   ├── 000001.SZ_20240101_20260620_raw.parquet
  │   ├── 000001.SZ_20240101_20260620_hfq_20260620.parquet
  │   └── ...
  ├── daily_status/
  │   ├── 000001.SZ_20240101_20260620.parquet
  │   └── ...
  ├── financials/
  │   ├── 000001.SZ_income.parquet
  │   ├── 000001.SZ_balance.parquet
  │   └── ...
  ├── announcements/
  │   ├── 000001.SZ_2024_2026.parquet
  │   └── ...
  └── stock_identity/
      └── all_stocks.parquet
```

**SQLite metadata 表**：

```sql
CREATE TABLE data_cache_metadata (
    cache_key TEXT PRIMARY KEY,
    file_path TEXT NOT NULL,
    data_type TEXT NOT NULL,  -- daily_bars / daily_status / financials / announcements / stock_identity
    symbol TEXT,
    start_date TEXT,
    end_date TEXT,
    source TEXT,  -- tushare / manual / calculated
    adjust_method TEXT,  -- raw / hfq / qfq
    adjust_snapshot_date TEXT,  -- 复权基准日期，保证可复现
    quality_status TEXT,  -- ok / degraded / insufficient
    created_at TIMESTAMP,
    ttl_days INTEGER,
    schema_version TEXT
);

CREATE INDEX idx_cache_symbol ON data_cache_metadata(symbol);
CREATE INDEX idx_cache_type ON data_cache_metadata(data_type);
CREATE INDEX idx_cache_quality ON data_cache_metadata(quality_status);
```

### 日线数据设计

**关键修正**：同时保存 raw_price + adj_factor，记录 adjust_snapshot_date

**raw 版本 Parquet schema**：

```python
{
    'date': date,
    'symbol': str,
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int64,
    'amount': float,  # 成交额
    'adj_factor': float  # 复权因子
}
```

**hfq 版本 Parquet schema**：

```python
{
    'date': date,
    'symbol': str,
    'open_adj': float,
    'high_adj': float,
    'low_adj': float,
    'close_adj': float,
    'volume': int64,
    'amount': float,
    'adjust_method': 'hfq',
    'adjust_snapshot_date': '2026-06-20'  # 记录复权基准日期，保证可复现
}
```

### 股票身份与每日状态拆分

**关键修正**：区分公司身份（变化慢）和每日状态（每天变化）

**stock_identity（公司身份）**：

```python
class StockIdentity:
    symbol: str
    name: str
    exchange: str  # SSE / SZSE
    list_date: date
    delist_date: date | None
    current_status: str  # listed / delisted / suspended_long_term
    industry: str
    sector: str
```

**daily_status（每日状态）Parquet schema**：

```python
{
    'date': date,
    'symbol': str,
    'is_st': bool,
    'is_suspended': bool,
    'is_limit_up': bool,
    'is_limit_down': bool,
    'suspend_reason': str | None,
    'st_type': str | None  # ST / *ST / None
}
```

### 板块成分处理

**关键修正**：第一版不承诺历史时点完整可用

```python
def get_sector_constituents(
    self, 
    sector_name: str, 
    date: date = None,
    use_current_snapshot: bool = True
) -> Tuple[List[str], str]:
    """
    获取板块成分股
    
    Returns:
        constituents: 股票列表
        source_note: 数据来源说明
        
    第一版默认 use_current_snapshot=True，返回当前快照
    回测报告必须标注"板块成分为当前快照，可能存在未来函数"
    """
    if use_current_snapshot or date is None:
        constituents = self._get_current_sector_constituents(sector_name)
        return constituents, f"当前快照（{datetime.now().date()}）"
    else:
        # 第一版不保证历史时点准确
        raise NotImplementedError(
            "历史时点板块成分第一版不支持，请使用当前快照或本地标签库"
        )
```

### 财务数据处理

**关键修正**：只给 Evidence Agent 用，V1 不进入 strategy_core 信号

```python
def get_financials(
    self, 
    symbol: str, 
    periods: int = 4,
    fields: List[str] = None,
    as_of_date: date = None  # point-in-time 查询
) -> pd.DataFrame:
    """
    获取财务数据（只给 Evidence Agent 用）
    
    必须按 ann_date 对齐，支持 point-in-time 查询
    V1 不进入 strategy_core 信号
    
    Returns:
        DataFrame with columns:
        - end_date: 报告期
        - ann_date: 公告日期
        - revenue, net_profit, ...
    """
    pass
```

### Cache TTL 配置

**关键修正**：按数据类型区分 TTL

```python
class CacheManager:
    # TTL 配置（天数）
    TTL_CONFIG = {
        'daily_bars_recent': 1,       # 近期日线（最近 30 天）
        'daily_bars_historical': 90,  # 历史日线
        'daily_status': 1,            # 每日状态
        'financials': 30,             # 财务数据（公告后更新）
        'announcements': 7,           # 公告
        'stock_identity': 30,         # 股票身份（支持手动刷新）
        'sector_constituents': 7,     # 板块成分
    }
    
    def get_ttl(self, data_type: str, date_range: Tuple[date, date]) -> int:
        """
        根据数据类型和时间范围返回 TTL
        """
        if data_type == 'daily_bars':
            recent_days = (datetime.now().date() - date_range[1]).days
            if recent_days < 30:
                return self.TTL_CONFIG['daily_bars_recent']
            else:
                return self.TTL_CONFIG['daily_bars_historical']
        else:
            return self.TTL_CONFIG.get(data_type, 7)
```

### Parquet 引擎

**固定使用 pyarrow**：

```python
import pyarrow as pa
import pyarrow.parquet as pq

# 写入
df.to_parquet(file_path, engine='pyarrow', compression='snappy')

# 读取
df = pd.read_parquet(file_path, engine='pyarrow')
```

---

（续下页）

## 4.2 Web 页面设计

**技术栈**：Next.js 14 + React + Tailwind CSS + shadcn/ui

### 页面结构

```
frontend/app/
  ├── dashboard/              # 首页
  ├── themes/                 # 待研究主题页
  │   ├── page.tsx           # 主题列表
  │   └── [id]/              # 主题详情（Serenity 输出 + Evidence 取证）
  ├── strategies/            # 策略库页
  │   ├── page.tsx           # 策略列表
  │   ├── [id]/              # 策略详情
  │   └── builder/           # Hypothesis Builder（表单）
  ├── backtest/              # 回测页
  │   ├── page.tsx           # 回测配置表单
  │   └── [id]/report/       # 回测报告
  ├── signals/               # Signal Board
  │   └── page.tsx           # 下一交易日计划信号
  ├── tasks/                 # 任务状态页
  │   └── page.tsx           # 任务列表（运行中/成功/失败）
  └── audit/                 # 审计页（新增）
      ├── page.tsx           # 审计日志列表
      ├── llm-runs/          # LLM 调用记录
      ├── tool-calls/        # 工具调用记录
      ├── data-snapshots/    # 数据快照
      └── artifacts/         # 产物归档
```

### 核心页面设计

**Dashboard（首页）**：
- 市场状态（红黄绿灯）
- 正在验证的策略（状态、最近回测结果）
- 待研究主题数量
- 今日 Signal Board 触发信号数量
- 最近任务状态
- **最近审计记录入口**（链接到 Audit 页面）

**待研究主题页（Themes）**：
- 主题列表：主题名、来源、研究模式、状态、创建时间
- 筛选：全部 / 待研究 / 研究中 / 已转策略
- 操作：新建主题、触发 Serenity 分析

**主题详情页**：
- Serenity 输出展示：
  - 产业链层级
  - 瓶颈环节
  - candidate_pool_raw（折叠）
  - candidate_shortlist（展开）
  - hypothesis_draft（可规则化部分 + 不可规则化部分）
- Evidence Agent 取证结果（对话式界面）：
  - 每只候选的证据等级、排雷项、blocking_issues
  - tool_trace 展示
- **Forward Candidates 草稿生成**（新增）：
  - 对 Evidence 完成的候选，生成 Forward Candidate 草稿
  - 展示 thesis、invalidation_rules、price_snapshot、benchmark
  - 用户确认加入 Forward Candidates
- 操作：转入 Hypothesis Builder

**Forward Candidates 页面**（新增）：
- 路径：`/forward-candidates`
- 表格展示，不需要复杂 UI
- 列表字段：
  - theme / symbol / company_name / chain_layer
  - evidence_level
  - date_added
  - price_snapshot.close（加入时价格）
  - benchmark（类型 + 名称）
  - alpha_vs_benchmark（相对超额收益）
  - status（active / converted_to_strategy / downgraded / removed）
  - review_date（下次复盘日期）
  - converted_to_strategy_id（如果已转策略）
- 筛选：
  - 按 status
  - 按 theme
  - 按 evidence_level
- 操作：
  - 查看详情（thesis、invalidation_rules、price_snapshot 完整信息、复盘历史）
  - 触发复盘（手动）
  - 转入 Hypothesis Builder（active 状态可用）
  - 更新 status（downgrade / remove）
- 详情抽屉/页面：
  - 研究判断（thesis，锁定）
  - 证伪条件（invalidation_rules，锁定，按 type 分类展示）
  - 价格快照（完整 OHLC + volume + amount）
  - Benchmark 信息
  - 复盘历史（时间线展示）
  - Alpha 走势图（可选，M4+ 实现）
  - Audit 链接

**策略库页（Strategies）**：
- 策略列表：策略名、版本、状态、最近回测结果、OOS 表现、**Admission Gate 结果**
- 筛选：按状态（draft / backtesting / rejected / prototype_passed / execution_validating）
- 显示字段增强：
  - `admission_result`（prototype_passed / rejected / needs_review）
  - `gate_warnings`（Admission Gate 警告列表）
  - `gate_blocking_issues`（阻止通过的问题列表）
- 操作：新建策略、编辑、回测、查看报告、进入 Signal Board（只有 prototype_passed 可用）

**Hypothesis Builder（表单页）**：
- 左侧：结构化表单
  - 策略名称
  - 股票池定义（sector + filters 对象）
  - 入场条件（从 entry_rule_candidates 选择或自定义）
  - 出场条件（从 exit_rule_candidates 选择或自定义）
  - 风险过滤
  - 回测配置（时间区间、样本切分、基准）
- 右侧：假设草案和证据摘要（只读参考）
- 顶部："生成草稿"按钮（LLM 辅助）
- 底部：保存、校验、提交回测
- **页面必须标记：Evidence 未完成**
- **未取证或 evidence_level = unknown 的股票池只能保存为 draft**

**回测页**：
- 选择策略
- 配置回测参数（如果策略已有配置，预填充）
- 提交任务
- 跳转到任务状态页

**回测报告页**：
- 7 块内容（概览、基础指标、样本内外对比、交易明细、成交约束统计、数据质量报告、**Admission Gate 准入检查**）
- **Admission Gate 明细展示**：
  - 准入结果（prototype_passed / rejected / needs_review）
  - 所有检查项（pass / fail / warning）
  - blocking_issues 列表
  - warnings 列表
  - 不通过原因解释
- 失败原因标签
- 操作：重新回测、修改策略、进入 Signal Board（只有 prototype_passed 可用）

**Signal Board 页（升级为 Signal Board + Action Plan）**：

页面结构：
- 左侧/主区域：信号列表
- 右侧/详情抽屉：Signal Detail + **Action Plan（新增）** + Audit Trace

**数据来源约束**：
- **只读取 `strategy.status == prototype_passed` 的策略**
- 未通过 Admission Gate 的策略不出现在 Signal Board
- 策略状态由 Admission Gate 决定，不是人工标记

**信号列表**：
- 今日日期、市场状态（红黄绿灯）
- 信号列表：
  - 股票代码/名称
  - 策略名称/版本
  - 当前状态：计划买入 / 计划卖出 / 继续观察 / 暂不操作
  - 信号触发日期、计划执行日期
  - 触发条件、入场/出场规则
  - 回测摘要：OOS 表现、最大回撤、交易笔数、数据质量
  - **Admission Gate 警告**（如果有）
  - 风险状态
  - **Audit 链接**
- 筛选：全部 / 计划买入 / 计划卖出 / 继续持有
- **明确标注：这是下一交易日计划信号，不是实盘建议**

**Action Plan 详情抽屉/下半部分（新增）**：

展示内容：
- **执行时间**：
  - planned_trade_date（计划执行日期）
  - planned_action（plan_buy / plan_sell / hold / no_action）
  - execution_window（open_next_day / close_next_day / conservative）
  - next_check_date（如果顺延/人工复核）
  - post_trade_review_date（如果执行成功）

- **仓位计划（position_plan）**：
  - max_position_pct（策略允许的单票上限，来自策略配置）
  - current_position_pct（当前持仓，来自账户/模拟账户）
  - planned_position_pct（本次计划执行后目标仓位）
  - available_position_pct（本次最多还能增加的仓位）
  - portfolio_source 标记（paper_portfolio / manual_input / unavailable）

- **执行前检查条件（invalid_if）**：
  - 结构化展示（type / scope / rule）
  - 示例：
    ```
    ✓ 市场状态检查：market_regime != red
    ✓ 个股状态检查：is_suspended == false
    ✓ 价格限制检查：is_limit_up == false (买入时)
    ✓ 流动性检查：daily_amount >= 10,000,000
    ```

- **失败处理**：
  - fallback_action（cancel / defer_next_day / manual_review）
  - 如果是 defer_next_day，展示 next_check_date

- **Execution Log 入口（预留，M4 实现）**：
  - 用户记录实际执行情况的入口
  - 展示历史执行记录（如果有）

- **Audit Trace**：
  - 链接到完整审计日志
  - 显示 signal_id、trade_plan_id、audit_id

**任务状态页（Tasks）**（增强版）：
- 任务列表增强字段：
  - 任务类型：Serenity 分析 / Evidence 取证 / 回测 / Signal 生成
  - 状态：queued / running / success / failed / degraded
  - 开始时间、完成时间、耗时
  - 进度百分比（如果支持）
  - **失败原因**：数据源问题 / schema 校验失败 / LLM 超时 / 回测错误 / 工具调用失败
  - **产物链接**：回测报告、取证结果、Signal Board
  - **数据质量**：ok / degraded / insufficient

**操作增强**：
- 查看日志（完整 stdout/stderr）
- 查看 Audit 记录（跳转到 Audit 页面）
- 重试（保留原配置重新运行）
- 取消（终止运行中任务）
- 下载产物（回测报告 JSON/Markdown/HTML、取证结果 JSON）

**失败原因分类**：
- `data_source_error`：Tushare API 失败、缓存损坏
- `schema_validation_error`：DSL 校验失败、字段不合法
- `llm_error`：LLM 超时、token 超限、API 错误
- `backtest_error`：回测引擎异常、数据不足
- `tool_call_error`：Evidence Agent 工具调用失败
- `execution_error`：未知运行时错误

**Audit 页面（新增，MVP 必需）**：

展示内容：
- **LLM run trace**：每次 LLM 调用的 prompt、response、model、token 使用量、时间戳
- **Tool call trace**：每次工具调用的参数、返回值、数据来源、质量状态
- **Data snapshot**：每次回测/Signal 生成使用的数据快照（文件路径、hash、质量报告）
- **Strategy config hash**：策略配置的 hash 值，用于追踪版本
- **Backtest config hash**：回测配置的 hash 值
- **Hypothesis source snapshot**：假设来源追踪
- **Report artifact**：回测报告、Signal Board 生成记录的归档
- **Signal generation run**：每次 Signal Board 生成的完整记录

筛选和查询：
- 按日期范围
- 按任务类型（Serenity / Evidence / Backtest / Signal）
- 按策略名称
- 按数据质量状态
- 按运行状态（success / failed / degraded）

操作：
- 查看详情（完整 trace）
- 下载产物（回测报告 JSON/Markdown/HTML、数据快照 Parquet）
- **重放（replay）**：
  - **Deterministic replay**：基于相同数据快照和配置 hash，重新执行代码逻辑，不调用 LLM
  - **LLM re-run**：重新调用 LLM，可能产生不同结果（用于测试 prompt 稳定性）

**审计存储设计**：
- LLM trace 完整内容（prompt、response、tool calls）落文件：`audit/llm_runs/{run_id}.json`
- SQLite 只存 metadata（run_id、timestamp、model、token_count、status、file_path、content_hash）

**导出格式**（第一版）：
- JSON / Markdown / HTML
- PDF 后置（Milestone 2+）

---

完整 Part 4 内容已保存。

