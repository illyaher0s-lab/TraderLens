#!/usr/bin/env python3
"""Phase 3B 验收测试

测试人工确认流程 + 观察池管理
"""

import sys
import os
import json

sys.path.insert(0, '/home/ubuntu/TraderLens')

from src.ui.pages.watchlist import (
    load_watchlist, 
    add_to_watchlist, 
    remove_from_watchlist,
    restore_to_watchlist,
    clear_watchlist,
    WATCHLIST_FILE
)


def test_watchlist_crud():
    """测试观察池 CRUD 操作"""
    print("🔍 测试 1: 观察池 CRUD 操作...")
    
    # 清空观察池
    clear_watchlist()
    
    # 添加股票
    add_to_watchlist(
        stock_code="000001",
        stock_name="平安银行",
        reason="测试添加",
        strategy_profile="trend",
        analysis_summary={"market": "震荡"},
        trade_plan={"action": "buy", "entry_price": 12.50}
    )
    
    # 加载并验证
    items = load_watchlist()
    
    if len(items) != 1:
        print(f"  ❌ 添加失败: 预期 1 只股票，实际 {len(items)} 只")
        return False
    
    if items[0]["stock_code"] != "000001":
        print(f"  ❌ 股票代码错误: {items[0]['stock_code']}")
        return False
    
    if items[0]["status"] != "active":
        print(f"  ❌ 状态错误: {items[0]['status']}")
        return False
    
    print("  ✅ 添加成功")
    
    # 移除股票
    remove_from_watchlist("000001")
    items = load_watchlist()
    
    if items[0]["status"] != "removed":
        print(f"  ❌ 移除失败: 状态 = {items[0]['status']}")
        return False
    
    print("  ✅ 移除成功")
    
    # 恢复股票
    restore_to_watchlist("000001")
    items = load_watchlist()
    
    if items[0]["status"] != "active":
        print(f"  ❌ 恢复失败: 状态 = {items[0]['status']}")
        return False
    
    print("  ✅ 恢复成功")
    
    # 清空
    clear_watchlist()
    items = load_watchlist()
    
    if len(items) != 0:
        print(f"  ❌ 清空失败: 仍有 {len(items)} 只股票")
        return False
    
    print("  ✅ 清空成功")
    
    return True


def test_watchlist_file_structure():
    """测试观察池文件结构"""
    print("\n🔍 测试 2: 观察池文件结构...")
    
    # 添加一只股票
    clear_watchlist()
    add_to_watchlist(
        stock_code="000001",
        stock_name="平安银行",
        reason="测试",
        strategy_profile="trend"
    )
    
    # 检查文件是否存在
    if not os.path.exists(WATCHLIST_FILE):
        print(f"  ❌ 文件不存在: {WATCHLIST_FILE}")
        return False
    
    print(f"  ✅ 文件存在: {WATCHLIST_FILE}")
    
    # 检查 JSON 格式
    try:
        with open(WATCHLIST_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ❌ JSON 解析失败: {e}")
        return False
    
    print("  ✅ JSON 格式正确")
    
    # 检查必需字段
    required_top_level = ["items", "last_updated"]
    for field in required_top_level:
        if field not in data:
            print(f"  ❌ 缺少顶级字段: {field}")
            return False
    
    print("  ✅ 顶级字段完整")
    
    # 检查 items 字段
    if not isinstance(data["items"], list):
        print(f"  ❌ items 应该是列表")
        return False
    
    if len(data["items"]) == 0:
        print(f"  ❌ items 为空")
        return False
    
    # 检查 item 字段
    item = data["items"][0]
    required_item_fields = [
        "stock_code", "stock_name", "reason", "strategy_profile",
        "status", "added_at", "updated_at"
    ]
    
    for field in required_item_fields:
        if field not in item:
            print(f"  ❌ item 缺少字段: {field}")
            return False
    
    print("  ✅ item 字段完整")
    
    return True


def test_watchlist_update():
    """测试更新现有股票"""
    print("\n🔍 测试 3: 更新现有股票...")
    
    clear_watchlist()
    
    # 添加股票
    add_to_watchlist(
        stock_code="000001",
        stock_name="平安银行",
        reason="原始理由",
        strategy_profile="trend"
    )
    
    # 再次添加（应该更新而非新增）
    add_to_watchlist(
        stock_code="000001",
        stock_name="平安银行",
        reason="更新后的理由",
        strategy_profile="value"
    )
    
    items = load_watchlist()
    
    if len(items) != 1:
        print(f"  ❌ 应该只有 1 只股票，实际 {len(items)} 只")
        return False
    
    if items[0]["reason"] != "更新后的理由":
        print(f"  ❌ 理由未更新: {items[0]['reason']}")
        return False
    
    if items[0]["strategy_profile"] != "value":
        print(f"  ❌ 策略未更新: {items[0]['strategy_profile']}")
        return False
    
    print("  ✅ 更新成功")
    
    return True


def test_ui_modules():
    """测试 UI 模块导入"""
    print("\n🔍 测试 4: UI 模块导入...")
    
    try:
        from src.ui.pages import research_simple, watchlist
        print("  ✅ research_simple 导入成功")
        print("  ✅ watchlist 导入成功")
        
        # 检查关键函数
        if not hasattr(research_simple, 'render'):
            print("  ❌ research_simple.render() 不存在")
            return False
        
        if not hasattr(watchlist, 'render'):
            print("  ❌ watchlist.render() 不存在")
            return False
        
        print("  ✅ render() 函数存在")
        
        return True
    
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 3B 验收测试")
    print("=" * 60)
    
    results = []
    
    # 测试 1: CRUD 操作
    results.append(("观察池 CRUD 操作", test_watchlist_crud()))
    
    # 测试 2: 文件结构
    results.append(("观察池文件结构", test_watchlist_file_structure()))
    
    # 测试 3: 更新操作
    results.append(("更新现有股票", test_watchlist_update()))
    
    # 测试 4: UI 模块
    results.append(("UI 模块导入", test_ui_modules()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = 0
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name:20s} {status}")
        if result:
            passed += 1
    
    print("=" * 60)
    print(f"通过率: {passed}/{total} ({100*passed//total}%)")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 所有测试通过！Phase 3B 验收完成")
        
        # 恢复示例数据
        print("\n正在恢复示例数据...")
        os.system("python /home/ubuntu/TraderLens/add_sample_watchlist.py > /dev/null 2>&1")
        print("✅ 示例数据已恢复")
        
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
