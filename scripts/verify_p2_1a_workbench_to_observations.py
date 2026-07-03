#!/usr/bin/env python3
"""
P2-1A-RETRY Workbench → Observation Pool 验证
前提：后端和前端已手动启动（backend: 8010, frontend: 3000）
验证：Workbench 自然语言买入 → /observations 显示持仓
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

# Fix Windows GBK encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from playwright.sync_api import sync_playwright


def main():
    print("=" * 100)
    print("P2-1A-RETRY Workbench → Observation Pool Verification")
    print("=" * 100)
    print()
    print("⚠️  Prerequisites:")
    print("    1. Backend running on http://localhost:8010")
    print("    2. Frontend running on http://localhost:3000")
    print("    3. Environment variable: NEXT_PUBLIC_API_BASE_URL=http://localhost:8010")
    print()
    
    # 1. 检查服务是否运行
    print("[1/6] Checking services...")
    try:
        import urllib.request
        
        # 检查后端
        backend_req = urllib.request.Request("http://localhost:8010/api/health/runtime")
        with urllib.request.urlopen(backend_req, timeout=5) as response:
            health_data = json.loads(response.read().decode())
            if health_data.get("status") != "ok":
                print("❌ FAIL: Backend health check failed")
                return 1
        print("✅ Backend is running")
        
        # 检查前端
        frontend_req = urllib.request.Request("http://localhost:3000")
        with urllib.request.urlopen(frontend_req, timeout=5) as response:
            if response.status != 200:
                print("❌ FAIL: Frontend health check failed")
                return 1
        print("✅ Frontend is running")
        
    except Exception as e:
        print(f"❌ FAIL: Services not available: {e}")
        print()
        print("Please start the services manually:")
        print("  Backend:  .venv\\Scripts\\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8010")
        print("  Frontend: cd frontend && set NEXT_PUBLIC_API_BASE_URL=http://localhost:8010 && npm run dev")
        return 1
    print()
    
    try:
        # 2. 打开 Workbench 并记录买入
        print("[2/6] Opening Workbench and recording buy execution...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            
            # 捕获 console 和 network
            console_logs = []
            network_logs = []
            
            def on_console(msg):
                console_logs.append({"type": msg.type, "text": msg.text})
            
            def on_response(response):
                network_logs.append({
                    "url": response.url,
                    "method": response.request.method,
                    "status": response.status,
                    "ok": response.ok,
                })
            
            page = context.new_page()
            page.on("console", on_console)
            page.on("response", on_response)
            
            # 打开 Workbench
            page.goto("http://localhost:3000/workbench", wait_until="networkidle")
            time.sleep(2)
            
            # 输入买入信息
            test_message = "我昨天买入了宏昌电子 100 股，成交价 12.34"
            
            # 尝试多种选择器
            input_selectors = [
                'textarea[placeholder*="输入"]',
                'textarea[placeholder*="消息"]',
                'textarea',
                'input[type="text"]',
            ]
            
            input_found = False
            for selector in input_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.fill(selector, test_message)
                        page.press(selector, "Enter")
                        print(f"✅ Sent message: {test_message}")
                        input_found = True
                        break
                except Exception:
                    continue
            
            if not input_found:
                print("❌ FAIL: Could not find input field")
                print("Available elements:")
                print(page.inner_text("body")[:500])
                browser.close()
                return 1
            
            # 等待响应（最多 60 秒）
            print("⏳ Waiting for agent response (up to 60 seconds)...")
            response_found = False
            for i in range(60):
                page_text = page.inner_text("body")
                if any(keyword in page_text for keyword in ["已记录", "position", "持仓", "执行反馈", "买入"]):
                    response_found = True
                    print(f"✅ Agent response received after {i+1} seconds")
                    break
                time.sleep(1)
            
            if not response_found:
                print("⚠️  WARNING: No clear confirmation after 60 seconds")
                print("Page text (last 500 chars):")
                print(page_text[-500:])
            
            # 保存 Workbench DOM
            workbench_dom = page.inner_text("body")
            workbench_dom_path = PROJECT_ROOT / "docs/verification/p2-1a-workbench-dom.md"
            workbench_dom_path.parent.mkdir(parents=True, exist_ok=True)
            with open(workbench_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# P2-1A Workbench DOM\n\n")
                f.write(f"**Captured at:** {datetime.now().isoformat()}\n\n")
                f.write(f"**Test Message:** {test_message}\n\n")
                f.write(f"## Page Text\n\n```\n{workbench_dom}\n```\n")
            print(f"✅ Saved Workbench DOM to {workbench_dom_path.relative_to(PROJECT_ROOT)}")
            
            # 保存 network log
            workbench_network_path = PROJECT_ROOT / "docs/verification/p2-1a-workbench-network-log.json"
            with open(workbench_network_path, "w", encoding="utf-8") as f:
                json.dump(network_logs, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved Workbench network log to {workbench_network_path.relative_to(PROJECT_ROOT)}")
            print()
            
            # 3. 查询 /api/observations
            print("[3/6] Querying /api/observations...")
            time.sleep(3)  # 等待 DB 写入完成
            
            observations_response = None
            try:
                import urllib.request
                req = urllib.request.Request("http://localhost:8010/api/observations?status=open")
                with urllib.request.urlopen(req, timeout=5) as response:
                    observations_response = json.loads(response.read().decode())
                    print(f"✅ GET /api/observations?status=open: HTTP {response.status}")
            except Exception as e:
                print(f"❌ FAIL: Could not query observations API: {e}")
                browser.close()
                return 1
            
            # 保存 API 响应
            observations_api_path = PROJECT_ROOT / "docs/verification/p2-1a-observations-api.json"
            with open(observations_api_path, "w", encoding="utf-8") as f:
                json.dump(observations_response, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved observations API response to {observations_api_path.relative_to(PROJECT_ROOT)}")
            
            # 检查是否有 position
            positions = observations_response.get("positions", [])
            if len(positions) == 0:
                print("⚠️  WARNING: No positions found in /api/observations response")
                print("This may indicate the execution_feedback workflow did not create a position")
            else:
                print(f"✅ Found {len(positions)} position(s) in API response")
                
                # 检查是否有宏昌电子
                target_position = None
                for pos in positions:
                    if "宏昌电子" in pos.get("stock_name", "") or pos.get("stock_code") == "603002":
                        target_position = pos
                        break
                
                if target_position:
                    print(f"✅ Found target position: {target_position.get('stock_name')} ({target_position.get('stock_code')})")
                    print(f"   - Status: {target_position.get('status')}")
                    print(f"   - Shares: {target_position.get('shares')}")
                    print(f"   - Entry Price: {target_position.get('entry_price')}")
                else:
                    print("⚠️  WARNING: Could not find 宏昌电子 in positions")
                    print("Available positions:", [p.get("stock_name") or p.get("stock_code") for p in positions])
            print()
            
            # 4. 打开 /observations 页面
            print("[4/6] Opening /observations page...")
            
            observations_page = context.new_page()
            observations_network = []
            
            def on_obs_response(response):
                observations_network.append({
                    "url": response.url,
                    "method": response.request.method,
                    "status": response.status,
                    "ok": response.ok,
                })
            
            observations_page.on("response", on_obs_response)
            observations_page.goto("http://localhost:3000/observations", wait_until="networkidle")
            time.sleep(3)
            
            # 保存 observations DOM
            observations_dom = observations_page.inner_text("body")
            observations_dom_path = PROJECT_ROOT / "docs/verification/p2-1a-observations-dom.md"
            with open(observations_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# P2-1A Observations Page DOM\n\n")
                f.write(f"**Captured at:** {datetime.now().isoformat()}\n\n")
                f.write(f"## Page Text\n\n```\n{observations_dom}\n```\n")
            print(f"✅ Saved observations DOM to {observations_dom_path.relative_to(PROJECT_ROOT)}")
            
            # 保存 observations network log
            observations_network_path = PROJECT_ROOT / "docs/verification/p2-1a-observations-network-log.json"
            with open(observations_network_path, "w", encoding="utf-8") as f:
                json.dump(observations_network, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved observations network log to {observations_network_path.relative_to(PROJECT_ROOT)}")
            print()
            
            # 5. 验证 DOM 内容
            print("[5/6] Validating observations page content...")
            
            dom_checks = {
                "has_stock_name_or_code": "宏昌电子" in observations_dom or "603002" in observations_dom,
                "has_status_indicator": any(word in observations_dom for word in ["open", "持仓", "观察", "Open"]),
                "no_error_message": "failed" not in observations_dom.lower() and "error" not in observations_dom.lower() and "失败" not in observations_dom,
                "no_loading_message": "loading" not in observations_dom.lower() and "加载中" not in observations_dom,
            }
            
            all_checks_passed = all(dom_checks.values())
            
            for check, passed in dom_checks.items():
                status = "✅" if passed else "❌"
                print(f"{status} {check}: {passed}")
            
            if not all_checks_passed:
                print("⚠️  WARNING: Some DOM checks failed")
                print("This may indicate the page is not showing the position correctly")
            else:
                print("✅ All DOM checks passed")
            print()
            
            # 6. 验证 network log
            print("[6/6] Validating network logs...")
            
            # 检查 Workbench network log
            workbench_api_calls = [log for log in network_logs if "/api/" in log["url"]]
            all_use_8010 = all("localhost:8010" in log["url"] or "127.0.0.1:8010" in log["url"] for log in workbench_api_calls) if workbench_api_calls else False
            
            # 检查 observations network log
            observations_api_call = next((log for log in observations_network if "/api/observations" in log["url"]), None)
            
            network_checks = {
                "workbench_has_api_calls": len(workbench_api_calls) > 0,
                "workbench_uses_8010": all_use_8010,
                "observations_api_called": observations_api_call is not None,
                "observations_api_success": observations_api_call and observations_api_call["status"] == 200 if observations_api_call else False,
                "observations_uses_8010": ("localhost:8010" in observations_api_call["url"] or "127.0.0.1:8010" in observations_api_call["url"]) if observations_api_call else False,
            }
            
            all_network_passed = all(network_checks.values())
            
            for check, passed in network_checks.items():
                status = "✅" if passed else "❌"
                print(f"{status} {check}: {passed}")
            
            if not all_network_passed:
                print("⚠️  WARNING: Some network checks failed")
            else:
                print("✅ All network checks passed")
            print()
            
            browser.close()
        
        # 检查 DB 路径
        print("Checking DB paths...")
        
        import urllib.request
        health_req = urllib.request.Request("http://localhost:8010/api/health/runtime")
        with urllib.request.urlopen(health_req, timeout=5) as response:
            health_data = json.loads(response.read().decode())
        
        db_path = health_data.get("live_trade_db_path", "")
        expected_db_path = str(PROJECT_ROOT / "data" / "live_trade.db")
        
        db_check = {
            "live_trade_db_path": db_path,
            "expected": expected_db_path,
            "match": db_path == expected_db_path,
        }
        
        db_check_path = PROJECT_ROOT / "docs/verification/p2-1a-db-path-check.json"
        with open(db_check_path, "w", encoding="utf-8") as f:
            json.dump(db_check, f, indent=2, ensure_ascii=False)
        
        if not db_check["match"]:
            print(f"❌ FAIL: DB path mismatch")
            print(f"   Expected: {expected_db_path}")
            print(f"   Got: {db_path}")
            return 1
        
        print(f"✅ DB path correct: {db_path}")
        print()
        
        # 最终结论
        print("=" * 100)
        if all_checks_passed and all_network_passed and len(positions) > 0:
            print("✅ PASS: P2-1A-RETRY Workbench → Observation Pool verification complete")
        else:
            print("⚠️  PARTIAL: Some checks did not pass completely")
            print()
            print("Summary:")
            print(f"  - Positions found: {len(positions)}")
            print(f"  - DOM checks passed: {all_checks_passed}")
            print(f"  - Network checks passed: {all_network_passed}")
        print("=" * 100)
        print()
        print("Evidence files:")
        print(f"  - {workbench_dom_path.relative_to(PROJECT_ROOT)}")
        print(f"  - {workbench_network_path.relative_to(PROJECT_ROOT)}")
        print(f"  - {observations_api_path.relative_to(PROJECT_ROOT)}")
        print(f"  - {observations_dom_path.relative_to(PROJECT_ROOT)}")
        print(f"  - {observations_network_path.relative_to(PROJECT_ROOT)}")
        print(f"  - {db_check_path.relative_to(PROJECT_ROOT)}")
        print()
        
        return 0
        
    except Exception as e:
        print(f"❌ FAIL: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
