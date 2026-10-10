# Formal PIT Interface Audit (Corrected)

**Date:** 2026-07-11  
**Window:** 2016-01-04 至最后已收市日  
**Status:** 2016-01-04 起 formal_candidate, 尚未 formal_qualified

---

## Executive Summary

✅ **存在覆盖 2016-01-04 至今的完整 required-interface 组合**

**Hard Blockers:** 无

**Scope:** 
- 2016-01-04+ 为 `formal_candidate` (可启动正式采集)
- 2010-2015 明确 unqualified (按计划排除)
- 尚未全量采集,因此未 formal-qualified

---

## Audit Matrix (Corrected)

### Trading Calendar
- Rows: 4015, date_range: 20160104-20261231
- Required fields: ✓ all present
- Classification: `formal_candidate`

### Stock Basic (L/D/P)
- **L:** 5530 rows, all required fields ✓ (含 exchange/list_status/delist_date)
- **D:** 335 rows, all required fields ✓
- **P:** 0 rows (当前无暂停上市样本,合法)
- Classification: `formal_candidate`

### ST History
- **stock_st(20161230):** 实际返回数据 (2016 年末有 ST 样本)
- **stock_st(recent=20260710):** 实际返回数据
- Classification: `formal_candidate` (2016-01-04+ 日度 ST 列表可用)

### Daily Market Data
- daily/daily_basic/stk_limit/adj_factor: 单日验证通过
- Classification: `formal_candidate` (需逐日分区采集)

### Index & Industry
- index_daily(000300.SH): ✓
- index_member_all(Y/N): ✓
- Classification: `formal_candidate`

---

## 撤销错误结论

**原审计错误:**
1. 倒序取 trading_day 导致 recent=20100104
2. stock_basic 默认投影缺字段误判为 unavailable
3. 2016-01-01 休市日误判为缺数据
4. st 仅作可选变更事件,不应作为 2010 起 hard prerequisite

**修正:**
- 2016-01-04 起 formal window 已批准
- stock_st 提供 2016+ 日度 ST 列表
- stock_basic 显式字段请求返回完整 schema
- namechange/suspend_d 空结果合法 (稀疏事件表)

---

## Formal Plan Output

```json
{
  "status": "ready_to_collect",
  "window_start": "20160104",
  "last_closed_trading_day": "20260710",
  "template_hash": "4ad573373ea52d786d4fccf58b5f443b97dbb64a68e28787800ea0a1ad8657a7",
  "data_requirements_hash": "ec205b1c33e0c7d076316276f214f5a4",
  "guard_config_hash": "16119300ea557f33e6628b905597d7c4d0bbfcd0f6eceaa9c9b318ff85af1829"
}
```

**下一步:** 可启动 formal-collect
