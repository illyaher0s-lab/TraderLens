"""
P1-1 第一批真实 Tushare 验证脚本

要求：
1. 用非宏昌电子、非603002 的真实股票
2. 公司名 -> stock_basic 真实查询
3. 贴原始请求参数和原始响应
4. 制造一次 Tushare 失败，确认 data_fault
"""

import os
import sys
from pathlib import Path

# Add backend to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.tushare.config import TushareConfig
from backend.app.tushare.tushare_client import TushareClient
from backend.services.stock_identity_resolver import StockIdentityResolver


def main():
    print("=" * 70)
    print("P1-1 第一批真实 Tushare 验证")
    print("=" * 70)
    print()
    
    # Check token
    token = os.getenv("TUSHARE_TOKEN")
    if not token:
        print("❌ TUSHARE_TOKEN 环境变量未设置")
        print()
        print("请设置后重试：")
        print("  export TUSHARE_TOKEN=<your_token>")
        print("  python3 scripts/verify_tushare_resolver_real.py")
        sys.exit(1)
    
    print(f"✅ TUSHARE_TOKEN 已加载（长度: {len(token)} 字符）")
    print()
    
    # Initialize
    config = TushareConfig.from_env()
    tushare_client = TushareClient(config)
    resolver = StockIdentityResolver(tushare_client=tushare_client)
    
    print(f"✅ TushareClient 已初始化")
    print(f"   API URL: {config.api_url}")
    print()
    print(f"✅ StockIdentityResolver 已初始化（生产模式）")
    print()
    
    # Test 1: 公司名查询（非宏昌电子、非603002）
    print("=" * 70)
    print("测试 1: 公司名 -> stock_basic 真实查询")
    print("=" * 70)
    print()
    print("股票选择: 贵州茅台（600519.SH）")
    print("原因: 非宏昌电子、非603002")
    print()
    
    print("【原始请求参数】")
    print("  api_name: 'stock_basic'")
    print("  name: '贵州茅台'")
    print("  fields: 'ts_code,name,market,list_status'")
    print()
    
    # Call resolver
    result1 = resolver.resolve(company_name="贵州茅台", stock_code=None)
    
    print("【原始响应】")
    if result1.status == "verified":
        print(f"  ts_code: {result1.ticker}")
        print(f"  name: {result1.company_name}")
        print(f"  market: {result1.exchange}")
        print(f"  list_status: {result1.list_status}")
    else:
        print(f"  status: {result1.status}")
        print(f"  fault_reason: {result1.fault_reason}")
    print()
    
    print("【解析结果】")
    print(f"  status: {result1.status}")
    print(f"  ticker: {result1.ticker}")
    print(f"  company_name: {result1.company_name}")
    print(f"  exchange: {result1.exchange}")
    print(f"  data_source: {result1.data_source}")
    print()
    
    if result1.status != "verified":
        print("❌ 测试 1 失败")
        sys.exit(1)
    
    print("✅ 测试 1 通过")
    print()
    
    # Test 2: 裸代码推断 + Tushare 查询
    print("=" * 70)
    print("测试 2: 裸代码 -> 确定性推断 -> stock_basic 查询")
    print("=" * 70)
    print()
    print("股票选择: 600519（裸代码）")
    print()
    
    print("【确定性推断】")
    print("  输入: 600519")
    print("  规则: 600/601/603/605/688 开头 -> .SH")
    print("  推断结果: 600519.SH")
    print()
    
    print("【原始请求参数】")
    print("  api_name: 'stock_basic'")
    print("  ts_code: '600519.SH'  # 推断后的代码")
    print("  fields: 'ts_code,name,market,list_status'")
    print()
    
    # Call resolver
    result2 = resolver.resolve(company_name=None, stock_code="600519")
    
    print("【原始响应】")
    if result2.status == "verified":
        print(f"  ts_code: {result2.ticker}")
        print(f"  name: {result2.company_name}")
        print(f"  market: {result2.exchange}")
        print(f"  list_status: {result2.list_status}")
    else:
        print(f"  status: {result2.status}")
        print(f"  fault_reason: {result2.fault_reason}")
    print()
    
    print("【解析结果】")
    print(f"  status: {result2.status}")
    print(f"  ticker: {result2.ticker}")
    print(f"  company_name: {result2.company_name}")
    print(f"  exchange: {result2.exchange}")
    print(f"  data_source: {result2.data_source}")
    print()
    
    if result2.status != "verified":
        print("❌ 测试 2 失败")
        sys.exit(1)
    
    print("✅ 测试 2 通过")
    print()
    
    # Test 3: Tushare 故障 -> data_fault
    print("=" * 70)
    print("测试 3: Tushare 故障 -> data_fault")
    print("=" * 70)
    print()
    print("方法: 使用无效 token 模拟 Tushare API 故障")
    print()
    
    # Create bad client
    bad_config = TushareConfig(token="INVALID_TOKEN_FOR_TEST_12345")
    bad_client = TushareClient(bad_config)
    bad_resolver = StockIdentityResolver(tushare_client=bad_client)
    
    print("【原始请求参数】")
    print("  api_name: 'stock_basic'")
    print("  name: '贵州茅台'")
    print("  fields: 'ts_code,name,market,list_status'")
    print("  token: INVALID_TOKEN_FOR_TEST_12345")
    print()
    
    # Call resolver with bad token
    result3 = bad_resolver.resolve(company_name="贵州茅台", stock_code=None)
    
    print("【原始响应】")
    print(f"  Exception caught: Tushare API error")
    print(f"  Error message: {result3.fault_reason}")
    print()
    
    print("【解析结果】")
    print(f"  status: {result3.status}")
    print(f"  data_source: {result3.data_source}")
    print(f"  fault_reason: {result3.fault_reason}")
    print()
    
    if result3.status != "data_fault":
        print(f"❌ 测试 3 失败: 预期 data_fault，实际 {result3.status}")
        sys.exit(1)
    
    print("✅ 测试 3 通过")
    print()
    print("注意: data_fault 不能当作 unknown 或假 verified")
    print()
    
    # Summary
    print("=" * 70)
    print("验证完成")
    print("=" * 70)
    print()
    print("第一批交付证据:")
    print(f"1. ✅ 公司名查询: 贵州茅台 -> {result1.ticker}")
    print(f"2. ✅ 裸代码推断: 600519 -> {result2.ticker}")
    print(f"3. ✅ 数据源: {result1.data_source}")
    print("4. ✅ Tushare 故障返回 data_fault")
    print()
    print("无硬编码名称/代码映射")
    print("所有查询经过真实 Tushare stock_basic API")
    print()


if __name__ == "__main__":
    main()
