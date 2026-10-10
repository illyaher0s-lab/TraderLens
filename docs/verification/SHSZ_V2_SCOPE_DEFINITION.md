# V2 沪深A股 PIT 数据资格规则冻结计划

## 背景
- 已完成 gap 审计：stk_limit 1198 msg / 15992 stock-days，daily_basic 321 msg / 15085 stock-days
- 主要缺口：001914.SZ (883天) + 71个 .BJ 代码（2020-2021集中）
- 现有 scope `fa4e3fd8f98d8758` 为 not_qualified

## 设计决定
1. **V2 市场范围**：仅沪深 A 股（.SH/.SZ）
   - 北交所（.BJ）移出范围，不是因缺口，是产品范围缩减
   - 后续需独立 BSE 数据包
2. **Universe ≠ 数据完整性**
   - Universe 由：market scope + PIT lifecycle + SW2021唯一行业 + 模板历史窗口决定
   - 不因字段缺失改变 universe
3. **数据资格**：universe 内必须有完整 daily/daily_basic/stk_limit/adj_factor
4. **最小历史窗口**：旧模板无明确 N，新模板设 N=0

## 预计修改文件

### 新增
- `backend/services/strategy_template_library.py` （新模板定义行）
- `tests/test_shsz_v2_qualification.py` （新测试）
- `docs/verification/SHSZ_V2_SCOPE_DEFINITION.md` （范围说明）
- `data/pit/formal_packages/<new_scope_hash>/` （新资格包）

### 修改
- `scripts/qualify_sw2021_pit_package.py` （读取 market_scope，分层过滤）

### 禁止修改
- `data/pit/formal_packages/fa4e3fd8f98d8758/manifest.json` （旧manifest hash: 21f7dd6a...）
- 旧模板 `relative_strength_rotation_sw2021_pit_v1`

## 数据流

```
1. 模板注册
   └─ relative_strength_rotation_shsz_sw2021_v1
      ├─ market_scope: ["SH", "SZ"]
      ├─ minimum_history_trading_days: 0
      └─ data_requirements_hash 包含以上

2. Universe 构造（三阶段）
   ├─ Stage 1: PIT lifecycle + SW2021唯一 + N日窗口
   │            → candidate_stock_days_before_market_scope
   ├─ Stage 2: 应用 market_scope 过滤
   │            .BJ → out_of_scope_bse_stock_days
   │            .SH/.SZ → expected_stock_days_after_market_scope
   └─ Stage 3: 检查必要字段
                缺失 → blocking gaps（按接口分类）

3. 输出
   ├─ manifest.json
   │   ├─ scope_hash (新)
   │   ├─ template_hash (新模板的 frozen_template_hash)
   │   ├─ data_requirements_hash (新)
   │   ├─ candidate_stock_days_before_market_scope
   │   ├─ out_of_scope_bse_stock_days
   │   ├─ expected_stock_days_after_market_scope
   │   ├─ gap_counts_by_type
   │   └─ first_unexplained_gap
   └─ FORMAL_SHSZ_V2_QUALIFICATION.md
```

## Hash 计算
- `template_hash`: 使用 `frozen_template_hash` 属性（已有实现）
- `data_requirements_hash`: JSON({interfaces, benchmarks, market_scope, minimum_history_trading_days}, sort_keys=True) → SHA256
- `scope_hash`: SHA256(template_hash | guard_hash | data_requirements_hash | snapshot_hash)[:16]

## 测试覆盖
1. .BJ 齐全数据仍因 market_scope 排除
2. .SH/.SZ 缺字段产生 blocking gap
3. 新旧模板 hash 不同
4. 旧 manifest 文件内容hash不变
5. N=0 时所有交易日都是 expected
6. out_of_scope_bse_stock_days 计数正确

## 执行步骤
1. 新模板定义（添加到 strategy_template_library.py）
2. 修改 qualifier（三阶段过滤）
3. 写测试
4. 运行测试（第一阶段验证）
5. 运行完整资格 CLI（2554天，第二阶段验证）
6. git diff --check（第三阶段验证）
7. 验证旧 manifest hash 不变

## 预期结果
- 新 scope: qualified（001914.SZ 在 .SZ，需单独解释）或 not_qualified（若001914仍blocking）
- out_of_scope_bse: ~15108 stock-days（.BJ pre-cutoff主体）
- blocking gaps: 仅 .SH/.SZ 的真实缺口
- 旧 scope: 保持 not_qualified，文件hash不变
