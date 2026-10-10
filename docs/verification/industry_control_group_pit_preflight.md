# 同申万一级行业 PIT 对照组预检 (修正版)

**Date:** 2026-07-11  
**Status:** PIT_CONTROL_GROUP_AVAILABLE  
**Purpose:** 验证申万一级行业成员关系的 PIT 可用性

---

## 1. 已冻结对照组定义

Per plan:
- 每个历史交易日,以该日有效的申万一级行业成员关系确定股票所属行业
- 对照组为同一行业内、当日符合模板交易资格的其它股票
- 不得使用今天的行业分类回填 2010 年历史,不得使用静态列表

---

## 2. Tushare 申万分类来源版本

### 2.1 PIT 对照组来源

**Interface:** `index_member_all`  
**主键/字段:** `ts_code + l1_code + in_date + out_date + is_new`

**返回字段 (11 个):**
- Industry: `l1_code`, `l1_name`, `l2_code`, `l2_name`, `l3_code`, `l3_name`
- Stock: `ts_code`, `name`
- Validity: `in_date`, `out_date`, `is_new`

### 2.2 is_new 参数语义

| is_new | 含义 | 行数 (per stock) |
|--------|------|-----------------|
| `Y` | 当前成分 | 0-1 |
| `N` | 历史已移出成分 | 0-N |

**合并规则:** 每个 `ts_code` 需分别查询 Y 和 N,合并后按 `in_date/out_date` 判断有效期

---

## 3. 样本验证结果

### 3.1 探测样本

| 样本 | ts_code | is_new=Y | is_new=N |
|------|---------|----------|----------|
| 主板 | 600000.SH | 1 | 0 |
| 创业板 | 300750.SZ | 1 | 0 |
| 科创板 | 688001.SH | 1 | 1 |
| 茅台 | 600519.SH | 1 | 0 |

### 3.2 历史移出记录验证

**688001.SH (华兴源创):**

| l1_code | l1_name | in_date | out_date | is_new |
|---------|---------|---------|----------|--------|
| 801890.SI | 机械设备 | 20210730 | None | Y |
| 801890.SI | 机械设备 | 20190626 | 20210729 | N |

**结论:** ✅ 存在真实历史移出记录 (`is_new=N` 且有 `out_date`)

---

## 4. 覆盖检查

### 4.1 检查日期

- 2010-01-01
- 2015-01-01
- 2020-01-01
- 2025-01-01
- 2026-07-10 (最近已收市)

### 4.2 各样本覆盖结果

**600000.SH (浦发银行, 主板):**

| 日期 | 一级行业 | 状态 |
|------|----------|------|
| 2010-01-01 | 801780.SI | ✓ |
| 2015-01-01 | 801780.SI | ✓ |
| 2020-01-01 | 801780.SI | ✓ |
| 2025-01-01 | 801780.SI | ✓ |
| 2026-07-10 | 801780.SI | ✓ |

**300750.SZ (宁德时代, 创业板):**

| 日期 | 一级行业 | 状态 |
|------|----------|------|
| 2010-01-01 | NO MEMBERSHIP | ✓ (未上市) |
| 2015-01-01 | NO MEMBERSHIP | ✓ (未上市) |
| 2020-01-01 | 801730.SI | ✓ |
| 2025-01-01 | 801730.SI | ✓ |
| 2026-07-10 | 801730.SI | ✓ |

**688001.SH (华兴源创, 科创板):**

| 日期 | 一级行业 | 状态 |
|------|----------|------|
| 2010-01-01 | NO MEMBERSHIP | ✓ (未上市) |
| 2015-01-01 | NO MEMBERSHIP | ✓ (未上市) |
| 2020-01-01 | 801890.SI | ✓ |
| 2025-01-01 | 801890.SI | ✓ |
| 2026-07-10 | 801890.SI | ✓ |

**600519.SH (贵州茅台, 主板):**

| 日期 | 一级行业 | 状态 |
|------|----------|------|
| 2010-01-01 | 801120.SI | ✓ |
| 2015-01-01 | 801120.SI | ✓ |
| 2020-01-01 | 801120.SI | ✓ |
| 2025-01-01 | 801120.SI | ✓ |
| 2026-07-10 | 801120.SI | ✓ |

### 4.3 冲突检查

**同一日期多个一级行业:** 0 个冲突

### 4.4 覆盖缺口

**无缺口** — 所有样本在其上市期间均有有效行业成员记录

---

## 5. Formal data_requirements 规则

### 5.1 PIT 对照组来源 (已冻结)

```python
{
  "control_group": {
    "type": "shenwan_l1_industry",
    "source": "index_member_all",
    "source_description": "Tushare index_member_all interface with is_new=Y/N merged",
    "fields": "ts_code,l1_code,l1_name,in_date,out_date,is_new",
    "effective_period": "2010-01-01 to last_closed_trading_day",
    "pit_rule": "in_date <= as_of_date AND (out_date IS NULL OR out_date >= as_of_date)",
    "conflict_resolution": "reject if multiple l1_code valid on same date"
  }
}
```

### 5.2 采集策略

对每个 `ts_code`:
1. Query `index_member_all(ts_code=X, is_new='Y')`
2. Query `index_member_all(ts_code=X, is_new='N')`
3. Merge results
4. Validate no overlapping `in_date/out_date` ranges within same `l1_code`

---

## 6. 结论

### 6.1 是否已冻结 PIT 对照组来源?

✅ **是**

### 6.2 精确 source/version 规则

**Source:** `index_member_all`  
**Version/Schema:** Tushare current (返回 11 字段, 含 `l1_code/l1_name/in_date/out_date/is_new`)  
**PIT 支持:** ✅ 通过 `is_new=Y/N` 合并实现

### 6.3 覆盖缺口

**无** — 所有检查样本在上市期间均有有效行业记录

### 6.4 是否可以开始实现正式采集器?

✅ **是**

**采集器实现要点:**
1. 对每个符合模板资格的 `ts_code`,分别查询 `is_new=Y` 和 `is_new=N`
2. 合并结果, 按 `in_date/out_date` 构建 PIT 有效期索引
3. 在每个 `as_of_date`,筛选有效行业成员 → 构建对照组
4. 对同一日期出现多个 `l1_code` 的股票,标记为 `industry_conflict` 并从对照组中排除

---

## 7. 更新后的 formal_qualification_key

### 7.1 前三项 (现已齐全)

```
template_hash:           4ad573373ea52d786d4fccf58b5f443b97dbb64a68e28787800ea0a1ad8657a7
guard_config_hash:       16119300ea557f33e6628b905597d7c4d0bbfcd0f6eceaa9c9b318ff85af1829
data_requirements_hash:  <recompute after adding control_group>
snapshot_hash:           (待完整采集生成)
```

### 7.2 data_requirements 更新

在 `scripts/verify_gate0_data_feasibility.py` 的 `get_data_requirements()` 中添加:

```python
"control_group": {
    "type": "shenwan_l1_industry",
    "source": "index_member_all",
    "fields": "ts_code,l1_code,l1_name,in_date,out_date,is_new",
    "pit_rule": "merge is_new=Y/N, filter by in_date/out_date"
}
```

---

## 8. 风险提示

1. **is_new=N 返回行数不确定** — 688001.SH 只有 1 条历史记录,其它股票可能有更多,需按 `in_date/out_date` 去重
2. **行业切换历史** — 同一股票在不同时期可能属于不同 `l1_code`,需按时间轴正确处理
3. **申万版本切换** — 当前只发现 SW2014,若未来出现 SW2021,需在 manifest 中记录版本切换时点
