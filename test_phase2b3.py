"""Phase 2B-3 验收测试 - sector_strength_tool

测试目标：
1. 独立测试 sector_strength_tool
2. 验证 Mock 模式下的板块分析
3. 验证输出格式和信号生成
"""

import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.tools.sector_strength_tool import sector_strength_tool
from src.core.data_fetcher import DataFetcher


def test_sector_strength_tool():
    """测试 1: 独立测试 sector_strength_tool"""
    print("\n" + "="*60)
    print("测试 1: 独立测试 sector_strength_tool")
    print("="*60)
    
    # 设置环境变量为 mock 模式
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 测试股票代码
    stock_code = "000001"
    
    print(f"\n分析股票: {stock_code}")
    print("-" * 60)
    
    # 调用工具
    result = sector_strength_tool(stock_code=stock_code)
    
    # 验证返回格式
    assert result["tool"] == "sector_strength_tool", "工具名称错误"
    assert result["status"] in ["success", "error"], "状态字段错误"
    assert "result" in result, "缺少 result 字段"
    assert "summary" in result, "缺少 summary 字段"
    assert "signals" in result, "缺少 signals 字段"
    assert "data_refs" in result, "缺少 data_refs 字段"
    assert "created_at" in result, "缺少 created_at 字段"
    
    # 打印结果
    print(f"\n✓ 板块分析完成")
    print(f"  - 状态: {result['status']}")
    print(f"  - 板块: {result['result'].get('sector', 'N/A')}")
    print(f"  - 行业: {result['result'].get('industry', 'N/A')}")
    print(f"  - 强度: {result['result'].get('strength', 'N/A')}")
    print(f"  - 板块平均涨跌: {result['result'].get('sector_performance', {}).get('avg_change_pct', 0):.2f}%")
    print(f"  - 个股排名: {result['result'].get('stock_rank', {}).get('rank', 0)}/{result['result'].get('stock_rank', {}).get('total', 0)}")
    print(f"  - Summary: {result['summary']}")
    print(f"  - Signals: {result['signals']}")
    print(f"  - Data source: {result['data_refs'].get('source', 'N/A')}")
    
    # 验证 result 包含必需字段
    assert "sector" in result["result"], "result 缺少 sector"
    assert "industry" in result["result"], "result 缺少 industry"
    assert "strength" in result["result"], "result 缺少 strength"
    assert "sector_performance" in result["result"], "result 缺少 sector_performance"
    assert "stock_rank" in result["result"], "result 缺少 stock_rank"
    
    print("\n✓ 所有断言通过")
    
    return result


def test_mock_mode():
    """测试 2: 验证 Mock 模式"""
    print("\n" + "="*60)
    print("测试 2: 验证 Mock 模式")
    print("="*60)
    
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    result = sector_strength_tool(stock_code="000001")
    
    # 验证 mock 模式标记
    assert result["data_refs"]["source"] == "mock", "Mock 模式未正确标记"
    
    print(f"\n✓ Mock 模式正常工作")
    print(f"  - data_refs.source: {result['data_refs']['source']}")
    print(f"  - 板块: {result['result']['sector']}")
    print(f"  - 成分股数量: {result['data_refs']['constituent_count']}")


def test_signal_generation():
    """测试 3: 验证信号生成"""
    print("\n" + "="*60)
    print("测试 3: 验证信号生成")
    print("="*60)
    
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    result = sector_strength_tool(stock_code="000001")
    
    signals = result["signals"]
    
    print(f"\n✓ 信号生成测试")
    print(f"  - 生成了 {len(signals)} 个信号")
    print(f"  - 信号列表: {signals}")
    
    # 验证信号是字符串列表
    assert isinstance(signals, list), "signals 应该是列表"
    for signal in signals:
        assert isinstance(signal, str), f"信号应该是字符串: {signal}"
    
    print("\n✓ 信号格式正确")


def test_data_fetcher_methods():
    """测试 4: 验证 DataFetcher 新增方法"""
    print("\n" + "="*60)
    print("测试 4: 验证 DataFetcher 新增方法")
    print("="*60)
    
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    fetcher = DataFetcher()
    
    # 测试 get_stock_sector
    print("\n测试 get_stock_sector:")
    sector_info = fetcher.get_stock_sector("000001")
    assert sector_info is not None, "get_stock_sector 返回 None"
    assert "sector" in sector_info, "sector_info 缺少 sector"
    assert "industry" in sector_info, "sector_info 缺少 industry"
    print(f"  ✓ 板块: {sector_info['sector']}")
    print(f"  ✓ 行业: {sector_info['industry']}")
    
    # 测试 get_sector_constituents
    print("\n测试 get_sector_constituents:")
    constituents = fetcher.get_sector_constituents("银行")
    assert constituents is not None, "get_sector_constituents 返回 None"
    assert isinstance(constituents, list), "constituents 应该是列表"
    assert len(constituents) > 0, "constituents 为空"
    print(f"  ✓ 成分股数量: {len(constituents)}")
    print(f"  ✓ 前3只股票: {constituents[:3]}")
    
    print("\n✓ DataFetcher 方法测试通过")


def main():
    """主测试入口"""
    print("\n" + "="*60)
    print("Phase 2B-3 验收测试 - sector_strength_tool")
    print("="*60)
    
    try:
        # 测试 1: 独立测试工具
        result = test_sector_strength_tool()
        
        # 测试 2: Mock 模式验证
        test_mock_mode()
        
        # 测试 3: 信号生成
        test_signal_generation()
        
        # 测试 4: DataFetcher 方法
        test_data_fetcher_methods()
        
        print("\n" + "="*60)
        print("✅ Phase 2B-3 所有测试通过")
        print("="*60)
        print("\n下一步: Phase 2B-4 (fundamentals_tool)")
        
    except AssertionError as e:
        print(f"\n❌ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
