# SHSZ Official Lifecycle Evidence

**Scope:** 35d996036cc04179  
**Purpose:** Official announcement evidence for 5 focus codes

## 001914.SZ / 000043.SZ

### Search Results
- **Official announcement found**: https://static.cninfo.com.cn/finalpage/2019-11-08/1207074291.PDF
- **Title**: "中航善达股份有限公司关于拟变更公司名称、证券简称及证券代码的公告"
- **Announced changes**:
  - 拟变更后的公司名称: 招商局积余产业运营服务股份有限公司
  - 拟变更后的证券简称: 招商积余
  - 拟变更后的证券代码: 001914
- **Status**: `official_alias_unconfirmed` (PDF不可自动提取，未获取生效日期)
- **Required**: 人工核实生效交易日、确认000043→001914为同一证券代码变更

## 300216.SZ (千山退)
- **Stock basic**: delist 20200916
- **Gap**: daily_basic 20200805-20200817 (退市前1个月)
- **Status**: `unexplained_blocking` (未找到该期间停牌公告)

## 002604.SZ (龙力退)
- **Stock basic**: delist 20200715
- **Gap**: daily_basic 20200601-20200609 (退市前1.5个月)
- **Status**: `unexplained_blocking` (未找到该期间停牌公告)

## 000939.SZ (凯迪退)
- **Stock basic**: delist 20201217
- **Gap**: daily_basic 20201106-20201109 (退市前1个月)
- **Status**: `unexplained_blocking` (未找到该期间停牌公告)

## 000760.SZ (斯太退)
- **Stock basic**: delist 20210723
- **Gap**: daily_basic 20210610-20210611 (退市前1.5个月)
- **Status**: `unexplained_blocking` (未找到该期间停牌公告)

## Limitation
本次审计受限于：
1. PDF公告无法自动提取，需人工核实生效日期
2. 退市股停牌/整理期公告需逐只手工查询巨潮资讯
3. 未找到官方公告时保持 unexplained_blocking

**结论**: 001914/000043有官方代码变更公告但未确认生效日；其余4只未找到gap期间停牌证据。本次不修改任何代码或资格状态。
