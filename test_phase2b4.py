"""Phase 2B-4 验收测试 - fundamentals_tool

测试目标：
1. 独立测试 fundamentals_tool
2. 验证 Mock 模式下的基本面分析
3. 验证 JudgmentEngine 评分逻辑
4. 验证输出格式和信号生成
"""

import os
import sys

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.tools.fundamentals_tool import analyze_stock_fundamentals
from src.core.data_fetcher import DataFetcher
from src.core.judgment_engine import JudgmentEngine


def test_fundamentals_tool():
    """测试 1: 独立测试 fundamentals_tool"""
    print("\n" + "="*60)
    print("测试 1: 独立测试 fundamentals_tool")
    print("="*60)
    
    # 设置环境变量为 mock 模式
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    # 测试股票代码
    stock_code = "000001"
    
    print(f"\n分析股票: {stock_code}")
    print("-" * 60)
    
    # 调用工具
    result = analyze_stock_fundamentals(
        stock_code=stock_code,
        strategy_profile="trend",
        include_industry_context=True
    )
    
    # 验证返回格式
    assert result["tool"] == "analyze_stock_fundamentals", "工具名称错误"
    assert result["status"] in ["success", "error"], "状态字段错误"
    assert "result" in result, "缺少 result 字段"
    assert "summary" in result, "缺少 summary 字段"
    assert "signals" in result, "缺少 signals 字段"
    assert "data_refs" in result, "缺少 data_refs 字段"
    assert "created_at" in result, "缺少 created_at 字段"
    
    # 打印结果
    print(f"\n✓ 基本面分析完成")
    print(f"  - 状态: {result['status']}")
    print(f"  - 评级: {result['result'].get('verdict', 'N/A')}")
    print(f"  - 综合得分: {result['result'].get('combined_score', 0):.1f}")
    print(f"  - 绝对得分: {result['result'].get('absolute_score', 0):.1f}")
    print(f"  - 行业相对得分: {result['result'].get('industry_relative_score', 'N/A')}")
    print(f"  - 关键指标:")
    metrics = result['result'].get('key_metrics', {})
    print(f"    - PE: {metrics.get('pe', 'N/A')}")
    print(f"    - PB: {metrics.get('pb', 'N/A')}")
    print(f"    - ROE: {metrics.get('roe', 'N/A')}%")
    print(f"    - 负债率: {metrics.get('debt_ratio', 'N/A')}%")
    print(f"  - 优势: {result['result'].get('strengths', [])}")
    print(f"  - 劣势: {result['result'].get('weaknesses', [])}")
    print(f"  - Summary: {result['summary']}")
    print(f"  - Signals: {result['signals']}")
    print(f"  - Data source: {result['data_refs'].get('source', 'N/A')}")
    
    # 验证 result 包含必需字段
    assert "verdict" in result["result"], "result 缺少 verdict"
    assert "combined_score" in result["result"], "result 缺少 combined_score"
    assert "key_metrics" in result["result"], "result 缺少 key_metrics"
    
    print("\n✓ 所有断言通过")
    
    return result


def test_judgment_engine():
    """测试 2: 验证 JudgmentEngine 评分逻辑"""
    print("\n" + "="*60)
    print("测试 2: 验证 JudgmentEngine 评分逻辑")
    print("="*60)
    
    engine = JudgmentEngine()
    
    # 测试案例 1: 优秀股票
    financial_data_excellent = {
        "pe": 12.0,
        "pb": 1.5,
        "roe": 18.0,
        "debt_ratio": 35.0,
        "revenue_growth": 25.0,
        "profit_growth": 30.0,
        "gross_margin": 35.0,
        "net_margin": 15.0,
        "current_ratio": 2.0,
        "quick_ratio": 1.5
    }
    
    result_excellent = engine.evaluate_fundamentals(
        financial_data=financial_data_excellent,
        strategy_profile="trend"
    )
    
    print(f"\n测试案例 1: 优秀股票")
    print(f"  - 综合得分: {result_excellent['combined_score']:.1f}")
    print(f"  - 评级: {result_excellent['verdict']}")
    assert result_excellent["verdict"] in ["优秀", "良好"], "优秀股票评级错误"
    
    # 测试案例 2: 差股票
    financial_data_poor = {
        "pe": 50.0,
        "pb": 5.0,
        "roe": 3.0,
        "debt_ratio": 85.0,
        "revenue_growth": -10.0,
        "profit_growth": -15.0,
        "gross_margin": 8.0,
        "net_margin": 2.0,
        "current_ratio": 0.8,
        "quick_ratio": 0.5
    }
    
    result_poor = engine.evaluate_fundamentals(
        financial_data=financial_data_poor,
        strategy_profile="trend"
    )
    
    print(f"\n测试案例 2: 差股票")
    print(f"  - 综合得分: {result_poor['combined_score']:.1f}")
    print(f"  - 评级: {result_poor['verdict']}")
    assert result_poor["verdict"] in ["差", "一般"], "差股票评级错误"
    
    # 测试案例 3: 行业相对评分
    industry_context = {
        "avg_roe": 10.0,
        "avg_pe": 15.0,
        "avg_pb": 2.0
    }
    
    result_with_industry = engine.evaluate_fundamentals(
        financial_data=financial_data_excellent,
        industry_context=industry_context,
        strategy_profile="trend"
    )
    
    print(f"\n测试案例 3: 行业相对评分")
    print(f"  - 绝对得分: {result_with_industry['absolute_score']:.1f}")
    print(f"  - 行业相对得分: {result_with_industry['industry_relative_score']:.1f}")
    print(f"  - 综合得分: {result_with_industry['combined_score']:.1f}")
    assert result_with_industry["industry_relative_score"] is not None, "行业相对评分缺失"
    
    print("\n✓ JudgmentEngine 评分逻辑正确")


def test_strategy_profiles():
    """测试 3: 验证不同策略类型"""
    print("\n" + "="*60)
    print("测试 3: 验证不同策略类型")
    print("="*60)
    
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    stock_code = "000001"
    
    # 测试 trend 策略
    result_trend = analyze_stock_fundamentals(
        stock_code=stock_code,
        strategy_profile="trend"
    )
    print(f"\nTrend 策略:")
    print(f"  - 综合得分: {result_trend['result']['combined_score']:.1f}")
    print(f"  - 信号: {result_trend['signals']}")
    
    # 测试 growth 策略
    result_growth = analyze_stock_fundamentals(
        stock_code=stock_code,
        strategy_profile="growth"
    )
    print(f"\nGrowth 策略:")
    print(f"  - 综合得分: {result_growth['result']['combined_score']:.1f}")
    print(f"  - 信号: {result_growth['signals']}")
    
    # 测试 value 策略
    result_value = analyze_stock_fundamentals(
        stock_code=stock_code,
        strategy_profile="value"
    )
    print(f"\nValue 策略:")
    print(f"  - 综合得分: {result_value['result']['combined_score']:.1f}")
    print(f"  - 信号: {result_value['signals']}")
    
    print("\n✓ 不同策略类型测试通过")


def test_signal_generation():
    """测试 4: 验证信号生成"""
    print("\n" + "="*60)
    print("测试 4: 验证信号生成")
    print("="*60)
    
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    result = analyze_stock_fundamentals(
        stock_code="000001",
        strategy_profile="trend"
    )
    
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
    """测试 5: 验证 DataFetcher 新增方法"""
    print("\n" + "="*60)
    print("测试 5: 验证 DataFetcher 新增方法")
    print("="*60)
    
    os.environ["TRADERLENS_DATA_MODE"] = "mock"
    
    fetcher = DataFetcher()
    
    # 测试 get_financial_data
    print("\n测试 get_financial_data:")
    financial_data = fetcher.get_financial_data("000001")
    assert financial_data is not None, "get_financial_data 返回 None"
    assert "pe" in financial_data, "financial_data 缺少 pe"
    assert "pb" in financial_data, "financial_data 缺少 pb"
    assert "roe" in financial_data, "financial_data 缺少 roe"
    print(f"  ✓ PE: {financial_data['pe']}")
    print(f"  ✓ PB: {financial_data['pb']}")
    print(f"  ✓ ROE: {financial_data['roe']}%")
    print(f"  ✓ 负债率: {financial_data['debt_ratio']}%")
    
    # 测试 get_industry_context
    print("\n测试 get_industry_context:")
    industry_context = fetcher.get_industry_context("银行")
    assert industry_context is not None, "get_industry_context 返回 None"
    assert "avg_roe" in industry_context, "industry_context 缺少 avg_roe"
    print(f"  ✓ 行业平均 ROE: {industry_context['avg_roe']}%")
    print(f"  ✓ 行业平均 PE: {industry_context.get('avg_pe', 'N/A')}")
    
    print("\n✓ DataFetcher 方法测试通过")


def main():
    """主测试入口"""
    print("\n" + "="*60)
    print("Phase 2B-4 验收测试 - fundamentals_tool")
    print("="*60)
    
    try:
        # 测试 1: 独立测试工具
        result = test_fundamentals_tool()
        
        # 测试 2: JudgmentEngine 评分逻辑
        test_judgment_engine()
        
        # 测试 3: 不同策略类型
        test_strategy_profiles()
        
        # 测试 4: 信号生成
        test_signal_generation()
        
        # 测试 5: DataFetcher 方法
        test_data_fetcher_methods()
        
        print("\n" + "="*60)
        print("✅ Phase 2B-4 所有测试通过")
        print("="*60)
        print("\n下一步: Phase 2B-5 (search_research_memory_tool)")
        
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
