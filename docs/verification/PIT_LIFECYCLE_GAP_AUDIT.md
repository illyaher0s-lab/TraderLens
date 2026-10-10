# PIT Lifecycle Gap Audit

**Status:** lifecycle_source_incomplete  
**Checked trading days:** 2554  
**Formal qualification run:** No

## Local gaps

| ts_code | Missing stock-days | First | Last | namechange | stock_st |
|---|---:|---|---|---|---|
| 300114.SZ | 2203 | 20160104 | 20250214 | False | False |
| 000043.SZ | 883 | 20160104 | 20191213 | False | False |
| 000022.SZ | 567 | 20160104 | 20181220 | False | False |

## Native provider probe

- Calls: `stock_basic` for L, D, P only
- Requested fields: `ts_code,symbol,name,market,exchange,list_status,list_date,delist_date`
- Provider found gap codes: []
- Probe errors: []

No name-based or vendor-based lifecycle inference was used. This audit does not qualify the data package.
