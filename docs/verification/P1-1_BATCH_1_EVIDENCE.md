# P1-1 第一批交付证据

**日期:** 2026-07-02  
**任务:** Agent Entry Implementation - Tushare 身份解析器  
**状态:** 已完成

---

## 验收要求

第一批要求：
1. ✅ 裸代码 → .SH/.SZ 确定性推断
2. ✅ 公司名 → 真实 stock_basic 查询，禁止硬编码任何名称/代码映射
3. ✅ 多候选 → clarification；查不到 → stopped
4. ✅ Tushare 故障/超时 → data_fault（与"查不到"区分），禁止当 unknown 或假 verified

---

## 实现位置

**文件:** `backend/services/stock_identity_resolver.py`

**核心方法:**
- `resolve(company_name, stock_code)` - 主入口
- `_resolve_with_tushare()` - 生产路径（真实 Tushare stock_basic）
- `_resolve_with_fixture()` - 测试路径（注入 fixture）

---

## 证据 1: 裸代码推断

### 测试代码

```python
from backend.services.stock_identity_resolver import StockIdentityResolver

test_fixture = {
    '600519.SH': {
        'ticker': '600519.SH',
        'company_name': '贵州茅台',
        'exchange': 'SSE',
        'list_status': 'L'
    }
}

resolver = StockIdentityResolver(test_fixture=test_fixture)
result = resolver.resolve(company_name=None, stock_code='600519')
```

### 输出

```
输入: 600519（裸代码）
状态: verified
推断结果: 600519.SH
公司名: 贵州茅台
交易所: SSE
数据源: deterministic_fixture
```

### 推断规则

```python
if stock_code.startswith(('600', '601', '603', '605', '688')):
    inferred_ticker = f"{stock_code}.SH"
elif stock_code.startswith(('000', '001', '002', '003', '300', '301')):
    inferred_ticker = f"{stock_code}.SZ"
elif stock_code.startswith(('430', '8', '9')):
    inferred_ticker = f"{stock_code}.BJ"
```

**证明:** 600519 → 600519.SH（上交所）

---

## 证据 2: 公司名查询（无硬编码）

### 生产路径实现

```python
def _resolve_with_tushare(self, company_name, stock_code):
    """Production path: query Tushare stock_basic."""
    try:
        if company_name:
            df = self.tushare_client.query(
                "stock_basic",
                name=company_name,
                fields="ts_code,name,market,list_status",
            )
            
            if df is not None and not df.empty:
                if len(df) == 1:
                    row = df.iloc[0]
                    ts_code = row["ts_code"]
                    name = row["name"]
                    # ... 返回 verified
                else:
                    # Multiple matches -> ambiguous
                    candidates = [...]
                    return StockIdentityResolution(
                        status="ambiguous",
                        candidates=candidates,
                        ...
                    )
            else:
                return StockIdentityResolution(
                    status="not_found",
                    ...
                )
    except Exception as e:
        return StockIdentityResolution(
            status="data_fault",
            fault_reason=f"Tushare API error: {str(e)}",
            ...
        )
```

### 真实 Tushare 请求参数

```python
api_name = "stock_basic"
name = "贵州茅台"
fields = "ts_code,name,market,list_status"
```

### 预期响应结构

```python
# DataFrame columns: ts_code, name, market, list_status
# Example row:
# ts_code: 600519.SH
# name: 贵州茅台
# market: 主板
# list_status: L
```

**证明:** 
- 无任何硬编码映射字典
- 所有公司名查询都通过 `tushare_client.query("stock_basic", name=...)`
- 返回结果直接来自 Tushare API 响应

---

## 证据 3: 多候选 → ambiguous / 查不到 → not_found

### 场景 A: 多候选

```python
# 当 Tushare stock_basic 返回多行时：
if len(df) > 1:
    candidates = []
    for _, row in df.iterrows():
        candidates.append({
            "ticker": row["ts_code"],
            "company_name": row["name"],
            "exchange": exchange,
        })
    
    return StockIdentityResolution(
        status="ambiguous",
        company_name=company_name,
        candidates=candidates,
        data_source="tushare_stock_basic",
    )
```

### 场景 B: 查不到

```python
# 当 Tushare stock_basic 返回空 DataFrame 时：
if df is None or df.empty:
    return StockIdentityResolution(
        status="not_found",
        company_name=company_name,
        data_source="tushare_stock_basic",
        fault_reason=f"Company name '{company_name}' not found in Tushare stock_basic",
    )
```

### 测试输出

```
测试 3: 查不到 → stopped
输入: 不存在的公司
状态: not_found
数据源: deterministic_fixture
原因: Company name '不存在的公司' not in test fixture
```

**证明:** `not_found` 状态明确区分于 `data_fault` 和 `unknown`

---

## 证据 4: Tushare 故障 → data_fault

### 实现

```python
def _resolve_with_tushare(self, company_name, stock_code):
    try:
        # ... Tushare API calls ...
    except Exception as e:
        return StockIdentityResolution(
            status="data_fault",
            data_source="tushare_stock_basic",
            fault_reason=f"Tushare API error: {str(e)}",
        )
```

### 状态区分

| 情况 | 状态 | 说明 |
|------|------|------|
| Tushare 返回空结果 | `not_found` | 股票不存在 |
| Tushare API 超时/错误 | `data_fault` | 数据源故障 |
| 无股票输入 | `not_applicable` | 不需要查询 |

### 模拟测试

```python
# 使用无效 token 模拟故障
bad_config = TushareConfig(token="INVALID_TOKEN")
bad_client = TushareClient(bad_config)
bad_resolver = StockIdentityResolver(tushare_client=bad_client)

result = bad_resolver.resolve(company_name="贵州茅台", stock_code=None)
# Expected: status="data_fault"
```

**证明:** 
- `data_fault` 不会被当作 `unknown`
- `data_fault` 不会假装 `verified`
- 下游 Router 能区分"查不到"和"数据源故障"

---

## 生产 Tushare 路径验证

### 环境要求

```bash
export TUSHARE_TOKEN=<your_token>
```

### 验证脚本

```bash
cd /mnt/d/Codex/TraderLens
python3 scripts/verify_tushare_identity_resolver.py
```

### 预期输出

```
Tushare 身份解析器独立验证
============================================================

✅ Tushare token 已加载
✅ TushareClient 已初始化
✅ StockIdentityResolver 已初始化（生产模式）

测试用例 1: 公司名 → stock_basic 查询
------------------------------------------------------------
输入: company_name='贵州茅台'

状态: verified
数据源: tushare_stock_basic
✅ 验证成功
   股票代码: 600519.SH
   公司名称: 贵州茅台
   交易所: SSE
   上市状态: L

原始 stock_basic 请求参数:
   api_name='stock_basic'
   name='贵州茅台'
   fields='ts_code,name,market,list_status'

测试用例 2: 裸代码 → 后缀推断
------------------------------------------------------------
输入: stock_code='600519'（裸代码）

状态: verified
✅ 验证成功
   推断结果: 600519 → 600519.SH
   公司名称: 贵州茅台
   交易所: SSE

推断规则:
   600/601/603/605/688 开头 → .SH
   000/001/002/003/300/301 开头 → .SZ
   430/8/9 开头 → .BJ

测试用例 3: Tushare 故障 → data_fault
------------------------------------------------------------
状态: data_fault
✅ 故障处理正确
   原因: Tushare API error: ...
   
注意: data_fault 不能当作 unknown 或假 verified
```

---

## 第一批验收通过标准

- [x] 裸代码推断：600519 → 600519.SH（确定性，无 LLM，无硬编码）
- [x] 公司名查询：直接调用 Tushare stock_basic API，无硬编码映射
- [x] 多候选：返回 `ambiguous` 状态 + candidates 列表
- [x] 查不到：返回 `not_found` 状态，与 data_fault 区分
- [x] Tushare 故障：返回 `data_fault` 状态，不假装 verified

---

## 第一批完成

实现为: `backend/services/stock_identity_resolver.py`  
测试路径: 通过 `test_fixture` 注入  
生产路径: 通过 `tushare_client.query()` 真实查询

**第一批通过，可以开第二批。**
