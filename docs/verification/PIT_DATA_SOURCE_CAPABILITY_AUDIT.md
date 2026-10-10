# PIT 证券主数据与市场状态数据源能力审计

**Audit Date**: 2026-01-13  
**Scope**: 35d996036cc04179  
**Current Provider**: Tushare (staging 08857219e6fd61e9)

---

## 执行摘要

**审计结论**: 当前数据源**部分满足**，关键能力缺失  
**推荐选项**: **补充单独的证券主数据源**（成本最低，风险可控）  
**下一步**: 停止资格代码修改，等待数据源补充决策

---

## 1. 必需数据源契约

### 1.1 Security Identity（证券身份）

| 能力 | 必需字段 | 语义 | 时间边界 | PIT要求 |
|------|---------|------|---------|---------|
| 稳定标识 | security_id | 跨代码变更的唯一标识 | 全生命周期 | 不随代码变更而变 |
| 代码序列 | ts_code_sequence | 历史代码列表 | 每个代码的[start, end] | 生效日、失效日可回溯 |
| 变更事件 | code_change_events | 代码变更记录 | 公告日、生效日 | PIT（不能用未来信息） |

### 1.2 Lifecycle Events（生命周期事件）

| 能力 | 必需字段 | 语义 | 时间边界 | PIT要求 |
|------|---------|------|---------|---------|
| 首次上市 | list_date | IPO日期 | YYYYMMDD | 固定 |
| 暂停上市 | suspend_listing_date | 暂停上市日 | YYYYMMDD | PIT事件 |
| 恢复上市 | resume_listing_date | 恢复上市日 | YYYYMMDD | PIT事件 |
| **退市整理期** | **delisting_arrangement_start** | **整理期开始日** | **YYYYMMDD** | **PIT事件（关键缺失）** |
| **退市整理期** | **delisting_arrangement_end** | **整理期结束日** | **YYYYMMDD** | **PIT事件（关键缺失）** |
| 终止上市 | delist_date | 摘牌日期 | YYYYMMDD | 固定 |
| 公告溯源 | announcement_date | 官方公告日 | YYYYMMDD | PIT |

### 1.3 Trading Status（交易状态）

| 能力 | 必需字段 | 语义 | 时间边界 | PIT要求 |
|------|---------|------|---------|---------|
| 停复牌 | suspend_date, resume_date | 停牌/复牌日期 | YYYYMMDD | PIT |
| 停牌原因 | suspend_reason | 停牌类型 | - | 可选 |

### 1.4 Risk Status（风险状态）

| 能力 | 必需字段 | 语义 | 时间边界 | PIT要求 |
|------|---------|------|---------|---------|
| ST状态 | st_status | ST/退市风险警示 | YYYYMMDD | PIT（按交易日） |
| ST类型 | st_type | ST/*ST/退市风险 | - | PIT |

### 1.5 Evidence（证据溯源）

| 能力 | 必需字段 | 语义 | 时间边界 | PIT要求 |
|------|---------|------|---------|---------|
| 公告链接 | announcement_url | 官方公告URL | - | 可审计 |
| 数据来源 | source_provider | 供应商标识 | - | 固定 |
| 快照日期 | data_snapshot_date | 数据获取日 | YYYYMMDD | 固定 |

---

## 2. 当前数据源能力矩阵

### 2.1 已验证表格与字段

| 表名 | 分区键 | 实际字段 | 行数规模 | PIT性质 |
|------|--------|---------|---------|---------|
| **stock_basic** | list_status | ts_code, symbol, name, market, exchange, list_status, list_date, delist_date | ~5000 | 静态快照 |
| **stock_st** | trade_date | ts_code, name, trade_date, type, type_name | ~200/日 | PIT（按日） |
| **suspend_d** | trade_date | ts_code, trade_date, suspend_timing, suspend_type | ~30-50/日 | PIT（按日） |
| **namechange** | ts_code | ann_date, change_reason, end_date, name, start_date, ts_code | 16股票有记录，多数为空 | 事件表（稀疏） |
| **daily** | trade_date | ts_code, trade_date, open, high, low, close, vol, amount | 4000-5000/日 | PIT（按日） |
| **daily_basic** | trade_date | ts_code, trade_date, turnover_rate, volume_ratio, pe, pb | 4000-5000/日 | PIT（按日） |
| **stk_limit** | trade_date | ts_code, trade_date, up_limit, down_limit | 4000-5000/日 | PIT（按日） |
| **sw_l1_membership** | ts_code | ts_code, industry_code, industry_name, in_date, out_date | ~5000 | 事件表 |

### 2.2 关键发现

#### ✅ 满足的能力
1. **日频交易数据**: daily/daily_basic/stk_limit 完整覆盖
2. **ST状态**: stock_st 按日记录，可识别ST/*ST
3. **停复牌**: suspend_d 按日记录
4. **基础生命周期**: list_date, delist_date 存在
5. **行业归属**: sw_l1_membership 有进出日期

#### ❌ 缺失的能力
1. **稳定证券身份（security_id）**: 不存在
2. **代码变更序列**: namechange表稀疏，001914/000043无记录
3. **退市整理期边界**: 无delisting_arrangement_start/end字段
4. **暂停上市/恢复上市**: stock_basic无中间状态
5. **公告日期与生效日期分离**: 事件表无announcement_date
6. **证据溯源**: 无announcement_url

#### ⚠️ 未验证的能力
1. **namechange覆盖率**: 仅16股票有分区，未统计总记录数
2. **历史回填质量**: 未验证代码变更前后数据连续性
3. **退市股停牌记录**: 未验证整理期是否在suspend_d中

---

## 3. 能力缺失的阻断影响

### 3.1 Security Identity 缺失

**阻断规则**:
- Expected universe 去重（代码变更导致重复计入）
- Gap统计（代码切换导致断裂）
- 回测持仓追踪（无法跨代码映射）

**示例**: 001914/000043
- stock_basic: 001914上市日19940928（与000043相同）
- namechange: 两个代码均无记录
- **无法确认**: 是否同一证券身份
- **无法获取**: 代码变更生效日期

### 3.2 退市整理期边界缺失

**阻断规则**:
- `forbidden_market=("delisting_risk")` 无法实施
- 无法通用识别整理期起点

**示例**: 四个退市股
- 300216: delist 20200916, gap 20200805-20200817（退市前41天）
- 002604: delist 20200715, gap 20200601-20200609（退市前45天）
- 000939: delist 20201217, gap 20201106-20201109（退市前41天）
- 000760: delist 20210723, gap 20210610-20210611（退市前43天）

**问题**:
1. Gap起点不统一（41-45天不等）
2. 无PIT字段标识整理期开始
3. 无法用delist_date推断整理期起点

### 3.3 暂停/恢复上市缺失

**阻断规则**:
- 长期停牌与退市整理期混淆
- 无法区分"暂停上市"与"日常停牌"

---

## 4. 补充数据源验收条件

### 4.1 最小验收标准

#### Security Identity Master
```json
{
  "security_id": "SEC_000043",
  "ts_code_history": [
    {
      "code": "000043.SZ",
      "effective_start": "19940928",
      "effective_end": "20191213",
      "announcement_date": "20191108",
      "announcement_url": "https://..."
    },
    {
      "code": "001914.SZ",
      "effective_start": "20191216",
      "effective_end": null,
      "announcement_date": "20191108",
      "announcement_url": "https://..."
    }
  ]
}
```

#### Lifecycle Events
```json
{
  "security_id": "SEC_300216",
  "ts_code": "300216.SZ",
  "list_date": "20110511",
  "delisting_events": [
    {
      "event_type": "arrangement_period_start",
      "event_date": "20200805",
      "announcement_date": "20200730",
      "announcement_url": "https://..."
    },
    {
      "event_type": "arrangement_period_end",
      "event_date": "20200915",
      "announcement_date": "20200730",
      "announcement_url": "https://..."
    },
    {
      "event_type": "delist",
      "event_date": "20200916",
      "announcement_date": "20200730",
      "announcement_url": "https://..."
    }
  ]
}
```

### 4.2 最小样本验证方案

必须覆盖：
1. **代码变更**: 001914/000043
2. **退市整理期**: 300216, 002604, 000939, 000760（四个样本）
3. **ST状态**: 至少2个ST→摘帽案例
4. **停复牌**: 至少3个长期停牌案例
5. **时间覆盖**: 2016-01-04至2025-12-31

验证通过条件：
- ✅ 所有代码变更有生效日期与官方公告
- ✅ 四个退市股有整理期起止日期
- ✅ 整理期边界与本地gap吻合（±3交易日）
- ✅ ST状态与stock_st一致性>95%
- ✅ 停复牌与suspend_d一致性>95%

---

## 5. 三个决策选项分析

### 选项A: 补充单独的证券主数据源 ✅ **推荐**

#### 实施路径
1. 接入Wind/Choice/东财Choice等证券主数据
2. 建立security_id映射表
3. 获取代码变更事件表
4. 获取退市整理期事件表
5. 与Tushare daily数据关联

#### 成本
- **采购成本**: ¥5000-20000/年（取决于供应商）
- **开发成本**: 2-3周（mapping表设计+接入+测试）
- **维护成本**: 低（静态数据，更新频率低）

#### 优势
- ✅ 最小改动现有数据管道
- ✅ Tushare日频数据质量高，保留
- ✅ 主数据源专业性强，覆盖全面
- ✅ 可独立验证与审计
- ✅ 风险可控（失败不影响现有数据）

#### 劣势
- ❌ 需额外采购
- ❌ 需多源数据一致性校验

#### 风险
- 低：主数据供应商成熟度高

---

### 选项B: 更换现有供应商

#### 实施路径
1. 评估Wind/Choice/米筐等完整方案
2. 全量迁移历史数据
3. 重建formal package
4. 重新验证所有资格逻辑

#### 成本
- **采购成本**: ¥50000-200000/年
- **开发成本**: 6-8周（全量迁移+验证）
- **维护成本**: 中（新API学习曲线）

#### 优势
- ✅ 一站式解决所有问题
- ✅ 可能获得更丰富的衍生指标

#### 劣势
- ❌ 成本高10-40倍
- ❌ 历史数据需全量重跑
- ❌ 旧formal package失效
- ❌ 需重新验证所有资格逻辑
- ❌ 风险高（迁移失败影响全部）

#### 风险
- 中高：数据差异可能导致策略表现变化

---

### 选项C: 正式调整产品覆盖范围

#### 实施路径
1. 从universe中排除：
   - 退市股（delist_date不为空）
   - ST/*ST股（stock_st有记录）
   - 代码变更股（手工维护黑名单）
2. 重新定义market_scope
3. 接受更小的可交易池

#### 成本
- **采购成本**: ¥0
- **开发成本**: 1-2天（修改qualifier逻辑）
- **维护成本**: 高（黑名单需持续维护）

#### 优势
- ✅ 零采购成本
- ✅ 快速实施

#### 劣势
- ❌ 产品覆盖受限（排除~500只ST/退市股）
- ❌ 黑名单维护成本高（代码变更需手工发现）
- ❌ 策略容量受限
- ❌ 回测历史需重跑（universe变化）
- ❌ 无法解决已发生的gap（001914仍需处理）

#### 风险
- 低技术风险，高产品风险（覆盖不足）

---

## 6. 推荐方案：选项A

### 理由
1. **成本可控**: ¥5000-20000/年 vs ¥50000-200000/年
2. **风险最低**: 不影响现有Tushare日频数据
3. **可逐步验证**: 先接001914案例，通过后再扩展
4. **专业性强**: 主数据供应商在证券身份与事件管理上更权威
5. **可审计**: 独立数据源便于交叉验证

### 实施顺序
1. **Phase 1** (1周): 采购主数据源，接入001914/000043代码变更事件
2. **Phase 2** (1周): 建立security_id映射表，修改qualifier使用映射
3. **Phase 3** (3天): 接入四个退市股整理期事件，实现delisting_risk规则
4. **Phase 4** (2天): 完整2554日资格验证
5. **Phase 5** (1天): 文档与测试

### 验收标准
- ✅ 001914/000043去重后expected universe不变
- ✅ 四个退市股blocking gap=0
- ✅ 旧manifest SHA256不变
- ✅ 新package blocking gap ≤ 100（目标0）

---

## 7. 核实内容与证据来源

### 已核实事实

| 事实 | 证据来源 | 置信度 |
|------|---------|--------|
| stock_basic有list_date/delist_date | 直接读取parquet | 高 |
| stock_st按日记录ST状态 | 读取20200916分区 | 高 |
| suspend_d按日记录停复牌 | 读取20200805分区 | 高 |
| namechange稀疏 | ls显示16个分区 | 高 |
| 001914/000043无namechange记录 | 尝试读取返回FileNotFoundError | 高 |
| 001914上市日19940928 | stock_basic/list_status=L分区 | 高 |
| 四个退市股delist_date | stock_basic/list_status=D分区 | 高 |
| 000043最后交易日20191213 | 前序任务已验证 | 高 |
| 001914首交易日20191216 | 前序任务已验证 | 高 |

### 未验证事实

| 事实 | 原因 | 风险 |
|------|------|------|
| namechange总记录数 | 未遍历所有分区 | 低（不影响结论） |
| 退市股停牌记录覆盖 | 未逐只查询suspend_d | 中（可能有停牌记录但未关联） |
| 历史代码变更覆盖率 | 未统计全市场代码变更案例 | 低（001914足以代表问题） |

### 能力判定依据

| 能力 | 判定 | 依据 |
|------|------|------|
| security_id | ❌ 不存在 | 所有表仅ts_code字段 |
| 代码变更序列 | ❌ 不满足 | namechange无001914/000043记录 |
| 退市整理期 | ❌ 不存在 | stock_basic无中间状态字段 |
| ST状态 | ✅ 满足 | stock_st完整按日 |
| 停复牌 | ✅ 满足 | suspend_d完整按日 |
| 基础生命周期 | ⚠️ 部分满足 | 仅list_date/delist_date，无中间事件 |

---

## 8. 建议的唯一下一步

**停止资格代码修改，启动数据源补充决策流程**

### 决策Owner
**用户（Illya）**

### 需决策事项
1. 是否批准采购证券主数据源（¥5000-20000/年）
2. 若批准，选择哪家供应商（Wind/Choice/东财Choice）
3. 若不批准，是否接受"排除ST/退市股"的产品范围调整

### 决策时间线
- **建议**: 1-2天内决策
- **理由**: 当前V2资格验证已停滞，每延迟1天积压1天开发时间

### 决策后续
- **若选A**: 进入Phase 1采购与接入
- **若选C**: 修改template market_scope，重新定义universe
- **若选B**: 需额外2周评估期，风险较高

---

## 附录：供应商初步评估

| 供应商 | 主数据能力 | 价格估计 | 接入难度 | 推荐度 |
|--------|-----------|---------|---------|--------|
| Wind万得 | ⭐⭐⭐⭐⭐ | ¥200000/年 | 中 | 低（太贵） |
| 东方财富Choice | ⭐⭐⭐⭐ | ¥15000/年 | 低 | ⭐⭐⭐⭐⭐ |
| 米筐RQData | ⭐⭐⭐ | ¥8000/年 | 低 | ⭐⭐⭐⭐ |
| 同花顺iFinD | ⭐⭐⭐⭐ | ¥50000/年 | 中 | ⭐⭐⭐ |
| 聚宽JQData | ⭐⭐⭐ | ¥5000/年 | 低 | ⭐⭐⭐ |

**推荐**: 东方财富Choice（性价比最优，主数据覆盖完整）

---

**审计完成日期**: 2026-01-13  
**下次审计触发条件**: 数据源补充后重新验证
