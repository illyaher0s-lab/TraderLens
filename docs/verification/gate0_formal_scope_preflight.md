# Gate 0 Formal PIT Scope Preflight

**Date:** 2026-07-11  
**Purpose:** 确认第一份 formal 数据包的作用域要素是否齐全  
**Status:** SCOPE_INCOMPLETE — 缺失 Market Guard 冻结配置

---

## 1. 可选模板版本

### 1.1 当前模板状态

| Template ID | Version | Hash (前16位) | Governance Status | Source Citation | Retrieval Date |
|-------------|---------|---------------|-------------------|-----------------|----------------|
| `relative_strength_rotation_v1` | v1 | `4ad573373ea52d78...` | **candidate** | `10.1111/j.1540-6261.1993.tb04702.x` | 2026-07-10 |
| `theme_momentum_breakout_v1` | v1 | (未读取) | candidate | `10.1111/0022-1082.00146` | 2026-07-10 |
| `volume_breakout_followthrough_v1` | v1 | (未读取) | candidate | `10.1111/0022-1082.00280` | 2026-07-10 |
| `trend_pullback_watch_v1` | v1 | (未读取) | **retired** | None | None |

### 1.2 Source Lifecycle 状态

**所有可用模板均为 `candidate`，无 `approved` 模板。**

Per plan 2.3: 只有 `approved` 模板才能启动 formal validation。Candidate 必须完成以下字段才能晋升：

- ✅ `source_citation` (已填)
- ✅ `source_retrieval_date` (已填)
- ❌ `rule_mapping` — **缺失**：source claim → frozen rule 一对一映射
- ❌ `reviewer_id` — **缺失**
- ❌ `reviewed_at` — **缺失**
- ❌ `review_due_date` — **缺失**

### 1.3 Immutable data_requirements

**当前 `relative_strength_rotation_v1` 的 data_requirements:**

```python
{
  "template_id": "relative_strength_rotation_v1",
  "interfaces": {
    "daily": {"fields": "ts_code,trade_date,open,high,low,close,vol,amount"},
    "daily_basic": {"fields": "ts_code,trade_date,turnover_rate,pe,pb,total_mv,circ_mv"},
    "stk_limit": {"fields": "ts_code,trade_date,up_limit,down_limit"},
    "adj_factor": {"fields": "ts_code,trade_date,adj_factor"},
    "index_daily": {"fields": "ts_code,trade_date,close,vol,amount"},
    "trade_cal": {"fields": "exchange,cal_date,is_open,pretrade_date"},
    "stock_basic": {"fields": "ts_code,symbol,name,list_date,delist_date"},
    "namechange": {"fields": "ts_code,name,start_date,end_date"},
    "suspend_d": {"fields": "native_default"},
    "index_classify": {"fields": "index_code,industry_code,level,is_pub"},
    "index_member_all": {"fields": "index_code,con_code,in_date,out_date"}
  },
  "benchmarks": ["000300.SH", "000905.SH"],
  "guard_rules": {
    "min_avg_amount_20d": 50000000,
    "market_regime_allowed": ["green", "yellow"]
  }
}
```

**data_requirements_hash:** `c70408c0a516bb8d8357da3d2743d5f9`

**缺失字段：**
- ❌ `control_group` — 计划 2.2 表格第 3 行要求 benchmark + **control group**
- ❌ `index_membership_sources` — `index_classify` / `index_member_all` 的具体指数来源和有效期未声明
- ⚠️ `guard_rules` — 当前为 legacy 键值对，非 Market Guard frozen config hash 引用

### 1.4 所需 Benchmark、Control Group、撮合字段

**Benchmarks (已声明):**
- `000300.SH` (CSI 300)
- `000905.SH` (CSI 500)

**Control Group (未声明):**
- 计划 2.2 要求 "benchmark, controls, and Market Guard" 数据
- 当前 data_requirements **无 control group 定义**

**撮合字段 (已覆盖):**
- Trading eligibility: `trade_cal`, `stock_basic(L/D/P)`, namechange, `suspend_d` ✓
- Raw market: `daily`, `daily_basic`, `stk_limit`, `adj_factor` ✓
- Benchmark: `index_daily` for 000300.SH / 000905.SH ✓
- Template membership: `index_classify`, `index_member_all` ✓

**排除字段 (符合计划):**
- ResearchCase 财务表 (`income`, `balancesheet`, `cashflow`, `fina_indicator`) — 正确排除 ✓

---

## 2. Market Guard Candidate 配置

### 2.1 配置文件状态

**查找结果:** `backend/config/` 下 **无 `market_regime_thresholds.yaml`**

### 2.2 需要的配置内容

Per plan 2.4, Market Guard candidate 必须包含：

| 字段 | 要求 | 当前状态 |
|------|------|----------|
| `validation_status` | `candidate` | ❌ 文件不存在 |
| Candidate triggers | 3条预注册规则 (极端普跌 >80%, 结构破位 单日<=-5% 或 5日<=-10%, 流动性 <30%) | ❌ 未定义 |
| PIT metric sources | `daily`, `index_daily`, `trade_cal`, stock_basic, ST, suspend | ❌ 未映射 |
| Stress windows | 2015-06-15~2015-08-31, 2020-03-09~2020-03-23 | ❌ 未声明 |
| Normal window | 2017-09-01~2017-11-30 | ❌ 未声明 |
| Zero-gap rule | 任一 trading day 缺失必需聚合输入 = 失败 | ❌ 未编码 |
| Normal-window block ratio | `floor(0.05 * normal_window_trading_day_count)` | ❌ 未计算 |
| Semantic hash | Configuration SHA-256 | ❌ 无配置无 hash |

### 2.3 可计算的 guard_config_hash

**无法计算** — 配置文件不存在，无候选阈值、窗口、指标定义。

---

## 3. Formal 首包字段逐项来源

### 3.1 Trading Eligibility

| 字段 | Tushare Interface | 当前 feasibility 状态 | Formal 要求 |
|------|-------------------|----------------------|-------------|
| `trade_cal` | `trade_cal` | ✓ 已采 2019-2025 | 2010-01-01 至最后闭市日 |
| `stock_basic(L)` | `stock_basic(list_status=L)` | ✓ 已采 | 全历史 |
| `stock_basic(D)` | `stock_basic(list_status=D)` | ❌ 未采 | 必需（退市股） |
| `stock_basic(P)` | `stock_basic(list_status=P)` | ❌ 未采 | 必需（暂停上市） |
| ST status | `namechange` (推断) 或 `stock_basic` 状态字段 | ⚠️ 已采 namechange，ST 标志未验证 | 每个 ST 生效期 |
| Name change | `namechange` | ✓ 已采 | 全历史 |
| `suspend_d` | `suspend_d` | ✓ 已采，65122行，月分区 <5000 | 全历史 |

### 3.2 Raw Market Data

| 字段 | Interface | 当前状态 | Formal 要求 |
|------|-----------|----------|-------------|
| `daily` | `daily` | ✓ 已采 2019-2025 | 2010-至今，每日分区 |
| `daily_basic` | `daily_basic` | ✓ 已采 | 同上 |
| `stk_limit` | `stk_limit` | ✓ 已采 | 同上 |
| `adj_factor` | `adj_factor` | ✓ 已采 | 同上 (V1 用原始价格) |

### 3.3 Benchmark / Control / Guard

| 用途 | Interface | 当前状态 |
|------|-----------|----------|
| Benchmark (000300.SH, 000905.SH) | `index_daily` | ✓ 已采 |
| Control group | — | ❌ **未定义** control group 是什么指数 |
| Index membership | `index_member_all` | ✓ 已采 |
| Index classification | `index_classify` | ✓ 已采 |
| 全 A 股日聚合 (Market Guard) | `daily` 聚合 | ✓ 原始数据已采，聚合逻辑未验证 |

### 3.4 ResearchCase 按需财务表

**正确排除** — `income`, `balancesheet`, `cashflow`, `fina_indicator` 不在首包 data_requirements 中 ✓

---

## 4. 2010-至今采集估算

### 4.1 基于实际 trade_cal

- **2019-2025 交易日:** 1699 天
- **年均交易日:** 243 天
- **2010-2026 估算交易日:** 3883 天 (16 年 × 243)

### 4.2 请求数估算

**日频接口 (需逐日分区):**
- `daily`, `daily_basic`, `stk_limit`, `adj_factor`, `suspend_d`
- 每接口请求数 = 3883
- **小计:** 5 × 3883 = **19,415 requests**

**非日频接口:**
- `trade_cal`: 1 request (全历史)
- `stock_basic` (L/D/P): 3 requests
- `namechange`: 1 request (全历史)
- `index_daily` (2 benchmarks): 2 × 16 = 32 requests (按年分区)
- `index_classify`, `index_member_all`: 各 2-5 requests
- **小计:** ~50 requests

**总请求数:** 19,465 requests

### 4.3 分区策略

**Daily 接口:** 按自然日分区 (YYYYMMDD)，每日一个请求
**Index 接口:** 按年或季度分区
**Suspend_d:** 季度分区，5000 行截断时细化至月

### 4.4 磁盘估算

- **2019-2025 snapshot:** 12 个 interface Parquet 文件，总计 ~1.5 MB (compressed)
- **2010-2026 (16 年):** 按比例 × 2.3 ≈ **3.5 MB** (final merged)
- **Staging 未压缩:** 预留 50 MB

### 4.5 最短限速时间

**Tushare 限速:** 200 req/min (假设)

**计算:**
```
19,465 requests ÷ 200 req/min = 97.3 minutes
```

**实际时间 (含重试/解析/写盘):** 预计 **110-120 分钟**

---

## 5. 唯一结论

### 5.1 是否已具备启动正式采集的条件？

❌ **否** — 缺失以下作用域要素：

### 5.2 第一个缺失项及现有证据

**缺失项:** Market Guard frozen configuration

**现有证据:**
1. `backend/config/market_regime_thresholds.yaml` **文件不存在**
2. Plan 2.4 要求的 candidate 配置字段 (triggers, windows, metrics, hash) 全部缺失
3. 无法计算 `guard_config_hash`
4. `formal_qualification_key = (template_hash, guard_config_hash, data_requirements_hash, snapshot_hash)` 中第 2 项无法填写

**次要缺失 (阻断晋升但不阻断 candidate 首包冻结):**
- Template governance: 缺 `rule_mapping`, `reviewer_id`, `reviewed_at`, `review_due_date`
- Control group 未定义

### 5.3 无法给出 formal_qualification_key 前三项

Per plan 2.2:

```
formal_qualification_key = (template_hash, guard_config_hash, data_requirements_hash, snapshot_hash)
```

**当前可填:**
- `template_hash`: `4ad573373ea52d788b4e0c6c7bc41f11e7e627fc7a19ba42fa66f6da9f5c4d9e` (relative_strength_rotation_v1)
- `guard_config_hash`: **❌ 无法计算**
- `data_requirements_hash`: `c70408c0a516bb8d8357da3d2743d5f9`
- `snapshot_hash`: 尚未采集 2010-present，不存在

### 5.4 无法给出完整采集命令

**阻断原因:** 没有 frozen Market Guard 配置，无法确定：
1. Guard 所需的全 A 股日聚合字段
2. 压力/正常窗口对应的精确日期范围
3. Control group 指数及其成员数据要求

**即使采集，也无法通过 `formal_qualified` probe** — 缺失 guard_config_hash 导致 formal_qualification_key 不完整。

---

## 6. 下一步行动

### 6.1 立即阻断点

创建 `backend/config/market_regime_thresholds.yaml` 并填写：

```yaml
validation_status: candidate
version: "1.0"
candidate_rules:
  extreme_breadth_selloff:
    metric: "proportion_daily_pct_chg_lte_minus5"
    threshold: 0.80
    source: "qualified daily + stock_basic"
  structural_breakdown:
    one_day:
      metric: "index_000300_SH_daily_return"
      threshold: -0.05
      source: "qualified index_daily"
    five_day:
      metric: "index_000300_SH_5d_compounded_return"
      threshold: -0.10
      source: "qualified index_daily"
  liquidity_exhaustion:
    metric: "all_a_share_amount_vs_30d_mean"
    threshold: 0.30
    source: "qualified daily aggregation"

stress_windows:
  - {id: "A", start: "2015-06-15", end: "2015-08-31"}
  - {id: "B", start: "2020-03-09", end: "2020-03-23"}

normal_window:
  start: "2017-09-01"
  end: "2017-11-30"

zero_gap_rule: true
normal_window_block_ratio_max: 0.05

validation_report_hash: null
validated_at: null
frozen_at: null
approved_by: null
```

计算其 `guard_config_hash`，更新 `data_requirements` 引用该 hash。

### 6.2 次要阻断 (不阻止 candidate 首包，但阻止晋升)

完成 template governance:
- 编写 source claim → frozen rule mapping
- 指定 reviewer_id
- 记录 reviewed_at / review_due_date

定义 control group (若模板需要)。

### 6.3 完整采集命令 (待 6.1/6.2 完成后)

```bash
# 创建新 snapshot (含 guard_config_hash)
python scripts/verify_gate0_data_feasibility.py collect \
  --worker-id=1 \
  --start-year=2010 \
  --end-year=2026 \
  --template-id=relative_strength_rotation_v1 \
  --guard-config-hash=<computed_hash>

# 6 workers 并行，每人负责 2-3 年
# Merge + probe with formal=true
python scripts/verify_gate0_data_feasibility.py merge --snapshot-id=<new_id>
python scripts/verify_gate0_data_feasibility.py probe --snapshot-id=<new_id> --formal=true
```

---

## 7. 风险提示

1. **当前 feasibility snapshot 不能晋升为 formal** — 只覆盖 2019-2025
2. **Guard 配置冻结后不可修改** — 任何阈值变更 = 新 candidate + 重跑 replay
3. **Template candidate 状态允许 Gate 0，但不允许 promotion** — 首包可冻结 formal scope，但无 approved 模板则无法到 `prototype_passed`
4. **Control group 缺失可能导致 benchmark 计算不完整** — 需明确模板是否依赖 control
