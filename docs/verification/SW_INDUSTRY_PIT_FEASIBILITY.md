# SW Industry PIT Feasibility Verification

**Date:** 2026-07-12 14:27:05

**Endpoint:** http://8.163.90.143:8686/

**Check dates:** 20160104, 20200309, 20241017, 20260710


## 1. SW Classifications


**SW2014:** 28 L1 industries

- Sample: 801020.SI 采掘

**SW2021:** 31 L1 industries

- Sample: 801010.SI 农林牧渔


**Total requests:** 2


## 2. Member Schema


**Fields:** l1_code, l1_name, l2_code, l2_name, l3_code, l3_name, ts_code, name, in_date, out_date, is_new

**Required fields present:** 
✓


**Total requests:** 3


## 3. Coverage Check


### 600000.SH


- is_new=Y: 1 rows

- is_new=N: 0 rows

- 20160104: 801780.SI 银行

- 20200309: 801780.SI 银行

- 20241017: 801780.SI 银行

- 20260710: 801780.SI 银行



### 000001.SZ


- is_new=Y: 1 rows

- is_new=N: 0 rows

- 20160104: 801780.SI 银行

- 20200309: 801780.SI 银行

- 20241017: 801780.SI 银行

- 20260710: 801780.SI 银行



### 300750.SZ


- is_new=Y: 1 rows

- is_new=N: 0 rows

- 20160104: NO MEMBERSHIP

- 20200309: 801730.SI 电力设备

- 20241017: 801730.SI 电力设备

- 20260710: 801730.SI 电力设备



### 688001.SH


- is_new=Y: 1 rows

- is_new=N: 1 rows

- 20160104: NO MEMBERSHIP

- 20200309: 801890.SI 机械设备

- 20241017: 801890.SI 机械设备

- 20260710: 801890.SI 机械设备



### 600519.SH


- is_new=Y: 1 rows

- is_new=N: 0 rows

- 20160104: 801120.SI 食品饮料

- 20200309: 801120.SI 食品饮料

- 20241017: 801120.SI 食品饮料

- 20260710: 801120.SI 食品饮料



**Total requests:** 13


## 4. Conclusion


**Total requests:** 13/80

**SW versions found:** 2

**Status:** feasible_for_full_collection

**Coverage:** Complete for sampled stocks and dates


**Note:** This is a read-only feasibility check. Full collection and formal qualification required before use.
