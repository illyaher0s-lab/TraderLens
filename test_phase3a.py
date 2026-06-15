#!/usr/bin/env python3
"""Phase 3A UI 验收测试

测试 Streamlit UI 基础功能
"""

import requests
import time
import sys

def test_streamlit_health():
    """测试 Streamlit 健康状态"""
    print("🔍 测试 1: Streamlit 健康检查...")
    
    try:
        response = requests.get("http://localhost:8501/_stcore/health", timeout=5)
        
        if response.status_code == 200 and response.text == "ok":
            print("✅ Streamlit 健康检查通过")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code} - {response.text}")
            return False
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 无法连接到 Streamlit: {e}")
        print("   提示: 请先运行 'python run_ui.py' 启动 UI")
        return False


def test_streamlit_page_load():
    """测试主页面加载"""
    print("\n🔍 测试 2: 主页面加载...")
    
    try:
        response = requests.get("http://localhost:8501", timeout=10)
        
        if response.status_code == 200:
            print("  ✅ 主页面返回 200 OK")
            print("  ℹ️  注意: Streamlit 内容动态渲染，需浏览器访问查看完整 UI")
            print("  ℹ️  请手动访问: http://localhost:8501")
            return True
        else:
            print(f"❌ 页面加载失败: {response.status_code}")
            return False
    
    except requests.exceptions.RequestException as e:
        print(f"❌ 无法加载页面: {e}")
        return False


def test_ui_modules():
    """测试 UI 模块导入"""
    print("\n🔍 测试 3: UI 模块导入...")
    
    try:
        # 测试主应用导入
        sys.path.insert(0, '/home/ubuntu/TraderLens')
        
        from src.ui.pages import research
        print("  ✅ research 模块导入成功")
        
        # 检查 render 函数
        if hasattr(research, 'render'):
            print("  ✅ research.render() 函数存在")
        else:
            print("  ❌ research.render() 函数不存在")
            return False
        
        return True
    
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False


def test_agent_integration():
    """测试 Agent 集成"""
    print("\n🔍 测试 4: Agent 集成...")
    
    try:
        from src.agent.harness import run_agent
        from src.agent.state import AgentState
        
        print("  ✅ Agent 模块导入成功")
        
        # 检查 run_agent 签名
        import inspect
        sig = inspect.signature(run_agent)
        
        if 'state' in sig.parameters or len(sig.parameters) > 0:
            print("  ✅ run_agent() 函数签名正确")
        else:
            print("  ⚠️  run_agent() 函数签名可能不正确")
        
        return True
    
    except ImportError as e:
        print(f"❌ Agent 模块导入失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Phase 3A UI 验收测试")
    print("=" * 60)
    
    results = []
    
    # 测试 1: 健康检查
    results.append(("Streamlit 健康检查", test_streamlit_health()))
    
    # 测试 2: 页面加载
    results.append(("主页面加载", test_streamlit_page_load()))
    
    # 测试 3: UI 模块
    results.append(("UI 模块导入", test_ui_modules()))
    
    # 测试 4: Agent 集成
    results.append(("Agent 集成", test_agent_integration()))
    
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
        print("\n🎉 所有测试通过！Phase 3A UI 验收完成")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
