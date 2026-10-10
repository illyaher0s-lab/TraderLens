# 只读计划检查报告：沪深V2 PIT身份规范化与退市整理期规则实施前检查

## 执行状态：**implementation_blocked - 证据不足**

---

## 1. 001914.SZ / 000043.SZ 证据边界核实

### 本地数据事实
- **最后000043交易日**: 20191213
- **首个001914交易日**: 20191216
- **代码切换窗口**: 20191213(五) → 20191216(一)，跨周末
- **两代码共存**: 20191213两代码同时存在于 daily
- **切换后纯净**: 20191216起仅 001914，无000043

### 官方公告状态
- **公告URL**: https://static.cninfo.com.cn/finalpage/2019-11-08/1207074291.PDF
- **公告日**: 2019-11-08
- **内容**: "拟变更后的证券代码: 001914"
- **生效日**: **未确认**（PDF无法自动提取）

### 证据缺口
1. **无直接生效日期**: 公告使用"拟变更"，未明确生效交易日
2. **2019-12-16非官方证据**: 该日期仅从本地数据观察得出
3. **同一证券身份未确认**: 需公告明确"代码变更"而非"新旧证券"

### 当前结论
**`identity_mapping_blocked`** — 不能用本地数据推断官方生效日，不能用指数调整日替代证券代码变更生效日。

---

## 2. 通用身份模型设计检查

### 现有系统字段核实
已读取：
- `daily`: ts_code, trade_date, open, high, low, close, vol, amount
- `daily_basic`: ts_code, trade_date, turnover_rate, volume_ratio, pe, pb
- `stk_limit`: ts_code, trade_date, up_limit, down_limit
- `stock_basic`: ts_code, symbol, name, market, exchange, list_status, list_date, delist_date
- `sw_l1_membership`: ts_code, industry_code, industry_name, in_date, out_date

**观察**: 所有表仅有 `ts_code`，无 `security_id` 或 raw_ts_code 字段。

### 通用模型要求

```
必需字段：
- raw_ts_code (原始代码，不变)
- security_id (稳定标识)
- effective_start (映射生效日)
- effective_end (映射失效日)
- policy_version
- evidence_hash (官方文件SHA256，非URL字符串)
```

### 各环节使用决策

| 环节 | 使用字段 | 理由 |
|------|---------|------|
| expected universe | security_id | 避免代码变更导致重复计入 |
| daily关联 | raw_ts_code → security_id | 保留原始数据，映射查询 |
| SW2021 membership | security_id | 行业归属跟随证券身份 |
| stock_st | raw_ts_code | ST状态与代码绑定 |
| suspend_d | raw_ts_code | 停牌记录按代码 |
| lifecycle | security_id | 上市/退市跟随身份 |
| gap统计 | security_id | 缺口统计不因代码变更断裂 |
| 回测数据读取 | raw_ts_code + security_id | 原始行用raw，去重用security_id |

**实施阻断**: 当前数据表无 security_id，需整体改造或建立mapping表。

---

## 3. 通用退市风险规则检查

### 模板定义核实
读取 `relative_strength_rotation_shsz_sw2021_v1`:
```python
forbidden_market=("limit_up", "st_stock", "delisting_risk")
```

### 现有执行逻辑
搜索qualifier:
- **未发现** `delisting_risk` 实际筛选逻辑
- **未发现** stock_st、suspend_d 与 forbidden_market 关联

### PIT数据源检查
- `stock_st`: 存在，可提供ST/退市风险警示标记
- `suspend_d`: 存在，可提供停牌日期
- **退市整理期标识**: 不存在独立字段

### 四个样本代码退市前gap
- 300216: gap 20200805-20200817, delist 20200916 (gap在退市前41天)
- 002604: gap 20200601-20200609, delist 20200715 (gap在退市前45天)
- 000939: gap 20201106-20201109, delist 20201217 (gap在退市前41天)
- 000760: gap 20210610-20210611, delist 20210723 (gap在退市前43天)

### 规则可行性分析
**问题**:
1. gap均在退市前1-1.5个月，无统一触发点
2. 无PIT字段标识"退市整理期"开始日
3. 仅delist_date无法推断整理期起点（各股票不同）

**实施阻断**: 
- 若使用固定"退市前N天"规则 → 不通用，且缺PIT依据
- 若需"退市整理期开始日" → 本地数据不存在该字段
- 若逐股手工标注 → 退化为"四股票日期表"，非通用规则

---

## 4. Policy与Hash规范

### Policy Schema草案
```json
{
  "policy_id": "shsz_pit_identity_v1",
  "policy_version": "1.0.0",
  "policy_hash": "<JSON canonical SHA256>",
  "identity_mappings": [
    {
      "security_id": "<stable_id>",
      "ts_code_sequence": [
        {"code": "000043.SZ", "effective_start": 19940928, "effective_end": 20191213},
        {"code": "001914.SZ", "effective_start": 20191216, "effective_end": null}
      ],
      "evidence": {
        "announcement_url": "https://...",
        "announcement_date": 20191108,
        "evidence_file_hash": "<local PDF SHA256>",
        "effective_date_status": "unconfirmed"
      }
    }
  ],
  "lifecycle_overrides": [],
  "delisting_risk_periods": []
}
```

### Hash传播
```
policy_content → policy_hash
  ↓
data_requirements_hash (包含 policy_hash + interfaces + market_scope + minimum_history)
  ↓
scope_hash (template_hash | guard_hash | data_requirements_hash | snapshot_hash)
```

### 官方证据Hash
- **必须**: 本地保存的PDF/文本内容SHA256
- **禁止**: 远程URL字符串SHA256冒充文件hash
- **当前**: PDF未下载 → evidence_file_hash为null → policy无法freeze

### 旧manifest保护
- 旧scope `35d996036cc04179` manifest SHA256: 待运行前记录
- 新scope将产生新hash
- 验证方法: 运行前后对比旧manifest字节

---

## 5. 本轮结束条件与实施边界

### 数据资格阶段终点
1. ✅ 身份规则对所有输入一致生效
2. ❌ 通用退市风险规则有PIT来源 (**阻断**)
3. ⏸️ 完整2554日资格验证 (待实施后)
4. ⏸️ 旧manifest SHA256不变 (待验证)
5. ❌ 沪深expected universe内blocking gap=0 (**不确定**)

### 若资格后仍有gap
- **禁止**: 逐代码增加policy
- **允许**: 输出剩余gap证据
- **决策**: 用户在"换数据源 / 缩小范围 / 容忍阈值"中选择

---

## 预计修改文件

### 新增
- `backend/pit/security_identity_policy.py` (policy加载器)
- `data/pit/policies/shsz_pit_identity_v1.json` (policy文件)
- `tests/test_pit_identity_policy.py`

### 修改
- `scripts/sw2021_pit_qualification_core.py` (增加identity映射)
- `scripts/qualify_sw2021_pit_package.py` (读取policy, 应用映射)
- `backend/services/strategy_template_library.py` (增加policy_id字段)

---

## 规范化前后数据流

### 当前流程
```
daily (raw ts_code) → eligible_codes → expected universe → gap check
```

### 规范化后
```
daily (raw ts_code) 
  ↓
identity_policy.map(raw_ts_code, date) → security_id
  ↓
eligible_codes (by security_id) → expected universe → gap check (按security_id去重)
```

---

## 通用规则与代码级Override边界

### 通用规则
- 所有代码变更通过 identity_policy
- 所有退市风险通过 stock_st + PIT字段

### 代码级Override
- **仅允许**: 明确官方公告且无法通用识别的个案
- **禁止**: 无官方依据的日期表

---

## 测试清单

1. identity映射生效日边界
2. 000043→001914切换日前后universe去重
3. 代码变更不产生gap (security_id连续)
4. 旧scope manifest字节不变
5. policy_hash确定性
6. 无policy时行为不变(向后兼容)

---

## 完整资格验证命令

```bash
# 记录旧manifest
sha256sum data/pit/formal_packages/35d996036cc04179/manifest.json > /tmp/old_manifest.sha256

# 运行新资格
python scripts/qualify_sw2021_pit_package.py

# 验证旧manifest不变
sha256sum -c /tmp/old_manifest.sha256
```

---

## 当前证据缺口

### 关键阻断
1. **001914生效日未确认** (PDF需人工读取)
2. **退市整理期PIT字段不存在** (四股票gap无通用规则)
3. **官方证据文件未本地化** (policy_hash无法freeze)

### 次要缺口
- security_id生成规则未定义
- 历史回测如何处理已映射数据
- policy version升级路径

---

## 已核实事实

✅ 000043最后交易日20191213, 001914首交易日20191216  
✅ 代码切换窗口跨周末  
✅ 本地数据无security_id字段  
✅ 退市风险规则在qualifier中未实现  
✅ 四个退市股gap在退市前1-1.5个月  
✅ 无PIT字段标识退市整理期起点

---

## 未核实事实

❌ 20191216是否为官方生效日 (需人工读PDF)  
❌ 001914/000043是否同一证券身份 (需人工读公告)  
❌ 四股票gap是否在停牌/整理期 (需逐只查公告)  
❌ 其他代码是否存在类似映射需求

---

## 最大实现风险

1. **生效日不确定** → 映射错误 → universe重复计入/遗漏
2. **退市规则无通用字段** → 退化为硬编码日期表
3. **policy引入后scope变化** → 历史对比失效
4. **官方证据未本地化** → 无法审计policy演化

---

## 是否具备进入实施阶段

### 结论: **NO - implementation_blocked**

### 阻断原因
1. **001914生效日未确认**: 不能用本地数据观察值替代官方公告
2. **退市整理期PIT字段缺失**: 四股票gap无法形成通用规则
3. **官方证据未本地化**: policy无法freeze hash

### 解除条件
1. 人工提取PDF公告，确认生效日期与同一证券身份
2. 获取退市整理期PIT数据源，或正式决策"缩小范围排除退市股"
3. 下载并hash官方PDF文件

---

## 建议的唯一下一步

**停止技术实施，转入决策阶段**:

### 决策选项
A. **人工核实001914公告** → 确认生效日 → 仅实施identity映射 → 接受四股票blocking
B. **正式缩小V2范围** → 排除退市/ST股 → 001914仍需identity映射
C. **换数据源** → 寻找包含退市整理期字段的供应商
D. **容忍阈值** → 预注册"897 blocking gaps可接受" → 不实施任何修复

**不建议**: 在证据不足时强行实施，将导致policy退化为硬编码补丁。

---

## 附录：Token预算状态
当前: 101K/200K (50%使用)，足够完成本报告，但不足以进入完整实施。
