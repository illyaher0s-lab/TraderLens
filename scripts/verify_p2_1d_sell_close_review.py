#!/usr/bin/env python3
"""
P2-1D Sell Close P&L Review 端到端验证

自动化流程：
1. 检查端口占用
2. 启动后端 (8010)
3. 启动前端 (3000)
4. 等待服务就绪
5. Playwright 打开 /workbench，输入买入信息
6. 验证 DB 写入 open position
7. Playwright 输入卖出信息
8. 验证 position closed，P&L 和 review 生成
9. 验证 /api/observations?status=closed 返回
10. 验证 /observations 页面显示 closed position
11. 保存 8 个证据文件
12. 清理进程

PASS 标准：
- 买入 Workbench POST 200
- 卖出 Workbench POST 200
- DB path = D:\\Codex\\TraderLens\\data\\live_trade.db
- 本次 position lifecycle_state 从 open 变 closed
- P&L 记录存在，source = calculated_from_confirmed_details
- review 记录存在，plan_adherence.followed_plan = None (honest unclassified)
- 所有 API 使用 localhost:8010
- DOM 是 Playwright 真实读取
"""

import json
import os
import subprocess
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
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 100)
print("P2-1D Sell Close P&L Review End-to-End Verification")
print("=" * 100)
print()
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
print(f"Current working directory: {os.getcwd()}")
print()


def check_port_in_use(port):
    """检查端口是否被占用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def main():
    backend_proc = None
    frontend_proc = None
    backend_log_file = None
    backend_log_path = None
    
    try:
        # Step 1: 检查端口占用
        print("[1/12] Checking port availability...")
        
        if check_port_in_use(8010):
            print("❌ FAIL: Port 8010 already in use")
            print("Please stop existing backend service before running this script")
            return 1
        print("✅ Port 8010 available")
        
        if check_port_in_use(3000):
            print("❌ FAIL: Port 3000 already in use")
            print("Please stop existing frontend service before running this script")
            return 1
        print("✅ Port 3000 available")
        print()
        
        # Step 2: 启动后端
        print("[2/12] Starting backend on port 8010...")
        os.environ["RESEARCH_CONVERSATION_MODE"] = "deterministic"
        os.environ["SERENITY_EXECUTION_MODE"] = "stub"
        
        backend_proc = subprocess.Popen(
            [
                str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8010",
            ],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        print("✅ Backend process started")
        
        # Save backend logs to file
        import threading
        backend_log_path = PROJECT_ROOT / "docs/verification/p2-1d-backend-log.txt"
        backend_log_file = open(backend_log_path, "w", encoding="utf-8")
        
        def log_backend_output():
            for line in backend_proc.stdout:
                backend_log_file.write(line)
                backend_log_file.flush()
        
        backend_log_thread = threading.Thread(target=log_backend_output, daemon=True)
        backend_log_thread.start()
        
        # Step 3: 等待 health endpoint
        print("[3/12] Waiting for backend health endpoint...")
        import urllib.request
        
        health_url = "http://localhost:8010/api/health/runtime"
        max_wait = 30
        health_data = None
        
        for i in range(max_wait):
            try:
                req = urllib.request.Request(health_url)
                with urllib.request.urlopen(req, timeout=2) as response:
                    health_data = json.loads(response.read().decode())
                    if health_data.get("status") == "ok":
                        print(f"✅ Backend health check passed: {health_data['status']}")
                        break
            except Exception as e:
                if i == max_wait - 1:
                    print(f"❌ FAIL: Backend health check timeout: {e}")
                    return 1
                time.sleep(1)
        
        if not health_data:
            print("❌ FAIL: Backend did not respond to health check")
            return 1
        
        # Verify DB path
        db_path = health_data.get("db_paths", {}).get("live_trade")
        expected_db_path = "D:\\Codex\\TraderLens\\data\\live_trade.db"
        
        if db_path != expected_db_path:
            print(f"❌ FAIL: DB path mismatch")
            print(f"  Expected: {expected_db_path}")
            print(f"  Got: {db_path}")
            return 1
        
        print(f"✅ DB path verified: {db_path}")
        
        # Save DB path check
        db_check_path = PROJECT_ROOT / "docs/verification/p2-1d-db-path-check.json"
        with open(db_check_path, "w", encoding="utf-8") as f:
            json.dump({"db_path": db_path, "expected": expected_db_path, "match": True}, f, indent=2, ensure_ascii=False)
        
        print()
        
        # Step 4: 启动前端
        print("[4/12] Starting frontend on port 3000...")
        frontend_env = os.environ.copy()
        frontend_env["NEXT_PUBLIC_API_BASE_URL"] = "http://localhost:8010"
        
        frontend_proc = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=str(PROJECT_ROOT / "frontend"),
            env=frontend_env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("✅ Frontend process started")
        
        # Wait for frontend to be ready
        print("[5/12] Waiting for frontend to be ready...")
        frontend_ready = False
        for i in range(30):
            try:
                req = urllib.request.Request("http://localhost:3000")
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        print("✅ Frontend is ready")
                        frontend_ready = True
                        break
            except:
                time.sleep(1)
        
        if not frontend_ready:
            print("❌ FAIL: Frontend did not start within 30 seconds")
            return 1
        
        print()
        
        # Step 6: Playwright - Buy execution
        print("[6/12] Playwright: Submitting buy execution via Workbench...")
        
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Enable request interception
            buy_requests = []
            sell_requests = []
            observations_requests = []
            
            def handle_request(route, request):
                if request.url.startswith("http://localhost:8010/api/workbench"):
                    buy_requests.append({
                        "url": request.url,
                        "method": request.method,
                        "headers": dict(request.headers),
                        "post_data": request.post_data,
                    })
                elif request.url.startswith("http://localhost:8010/api/observations"):
                    observations_requests.append({
                        "url": request.url,
                        "method": request.method,
                    })
                route.continue_()
            
            context.route("**/*", handle_request)
            
            page = context.new_page()
            
            # Record responses
            buy_response_data = None
            sell_response_data = None
            
            def handle_response(response):
                nonlocal buy_response_data, sell_response_data
                if response.url.startswith("http://localhost:8010/api/workbench") and response.request.method == "POST":
                    try:
                        data = response.json()
                        if buy_response_data is None:
                            buy_response_data = {"status": response.status, "data": data}
                        else:
                            sell_response_data = {"status": response.status, "data": data}
                    except:
                        pass
            
            page.on("response", handle_response)
            
            # Navigate to workbench
            page.goto("http://localhost:3000/workbench", wait_until="networkidle")
            time.sleep(2)
            
            # Input buy execution
            buy_message = "已买入宏昌电子（603002）100 股，成交价 12.50"
            textarea = page.locator("textarea[placeholder*='输入']").first
            textarea.fill(buy_message)
            time.sleep(0.5)
            
            # Submit
            page.keyboard.press("Enter")
            time.sleep(3)
            
            if not buy_response_data or buy_response_data["status"] != 200:
                print(f"❌ FAIL: Buy workbench POST failed: {buy_response_data}")
                browser.close()
                return 1
            
            print(f"✅ Buy workbench POST 200")
            
            # Extract position_id from timeline
            timeline_artifacts = buy_response_data["data"].get("timeline", {}).get("artifacts", [])
            position_id = None
            for artifact in timeline_artifacts:
                if artifact.get("artifact_type") == "observation_position":
                    position_id = artifact.get("artifact_id")
                    break
            
            if not position_id:
                print("❌ FAIL: No position_id in buy response timeline")
                browser.close()
                return 1
            
            print(f"✅ Position created: {position_id}")
            
            # Step 7: Query open positions before sell
            print("\n[7/12] Querying open positions before sell...")
            
            req = urllib.request.Request("http://localhost:8010/api/observations?status=open")
            with urllib.request.urlopen(req, timeout=5) as response:
                open_positions_before = json.loads(response.read().decode())
            
            # Save evidence
            open_api_path = PROJECT_ROOT / "docs/verification/p2-1d-observations-open-api-before-sell.json"
            with open(open_api_path, "w", encoding="utf-8") as f:
                json.dump(open_positions_before, f, indent=2, ensure_ascii=False)
            
            # Verify position is open
            found_open = any(p["position_id"] == position_id for p in open_positions_before["positions"])
            if not found_open:
                print(f"❌ FAIL: Position {position_id} not found in open positions")
                browser.close()
                return 1
            
            print(f"✅ Position {position_id} is open")
            
            # Step 8: Submit sell execution
            print("\n[8/12] Playwright: Submitting sell execution via Workbench...")
            
            sell_message = "已卖出宏昌电子（603002）100 股，成交价 13.00"
            textarea.fill(sell_message)
            time.sleep(0.5)
            
            page.keyboard.press("Enter")
            time.sleep(3)
            
            if not sell_response_data or sell_response_data["status"] != 200:
                print(f"❌ FAIL: Sell workbench POST failed: {sell_response_data}")
                browser.close()
                return 1
            
            print(f"✅ Sell workbench POST 200")
            
            # Extract review_id from timeline
            sell_timeline_artifacts = sell_response_data["data"].get("timeline", {}).get("artifacts", [])
            review_id = None
            for artifact in sell_timeline_artifacts:
                if artifact.get("artifact_type") == "discipline_review":
                    review_id = artifact.get("artifact_id")
                    break
            
            if not review_id:
                print("❌ FAIL: No review_id in sell response timeline")
                browser.close()
                return 1
            
            print(f"✅ Discipline review created: {review_id}")
            
            # Step 9: Verify position closed
            print("\n[9/12] Verifying position closed...")
            
            req = urllib.request.Request("http://localhost:8010/api/observations?status=closed")
            with urllib.request.urlopen(req, timeout=5) as response:
                closed_positions = json.loads(response.read().decode())
            
            # Save evidence
            closed_api_path = PROJECT_ROOT / "docs/verification/p2-1d-observations-closed-api.json"
            with open(closed_api_path, "w", encoding="utf-8") as f:
                json.dump(closed_positions, f, indent=2, ensure_ascii=False)
            
            found_closed = any(p["position_id"] == position_id for p in closed_positions["positions"])
            if not found_closed:
                print(f"❌ FAIL: Position {position_id} not found in closed positions")
                browser.close()
                return 1
            
            print(f"✅ Position {position_id} is now closed")
            
            # Step 10: Verify P&L and review in DB
            print("\n[10/12] Verifying P&L and review...")
            
            # Query review via internal method (read from DB)
            import sqlite3
            db_path_obj = PROJECT_ROOT / "data" / "live_trade.db"
            conn = sqlite3.connect(str(db_path_obj))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            review_row = cursor.execute(
                "SELECT review_json FROM discipline_reviews WHERE review_id = ?",
                (review_id,)
            ).fetchone()
            
            if not review_row:
                print(f"❌ FAIL: Review {review_id} not found in DB")
                conn.close()
                browser.close()
                return 1
            
            review_data = json.loads(review_row["review_json"])
            
            # Save review evidence
            review_api_path = PROJECT_ROOT / "docs/verification/p2-1d-review-or-pnl-api.json"
            with open(review_api_path, "w", encoding="utf-8") as f:
                json.dump(review_data, f, indent=2, ensure_ascii=False)
            
            # Verify P&L
            pnl_record = review_data.get("pnl_record", {})
            if pnl_record.get("pnl_source") != "calculated_from_confirmed_details":
                print(f"❌ FAIL: P&L source is not calculated_from_confirmed_details: {pnl_record.get('pnl_source')}")
                conn.close()
                browser.close()
                return 1
            
            print(f"✅ P&L source: calculated_from_confirmed_details")
            print(f"✅ P&L amount: {pnl_record.get('pnl_amount')}, pct: {pnl_record.get('pnl_pct')}%")
            
            # Verify review is honest (unclassified)
            plan_adherence = review_data.get("plan_adherence", {})
            if plan_adherence.get("followed_plan") is not None:
                print(f"❌ FAIL: plan_adherence.followed_plan should be None (honest unclassified), got: {plan_adherence.get('followed_plan')}")
                conn.close()
                browser.close()
                return 1
            
            print(f"✅ Review is honest: followed_plan = None (unclassified)")
            
            conn.close()
            
            # Step 11: Navigate to /observations and verify DOM
            print("\n[11/12] Navigating to /observations and verifying DOM...")
            
            page.goto("http://localhost:3000/observations", wait_until="networkidle")
            time.sleep(2)
            
            # Switch to "已平仓" tab
            closed_tab = page.locator("button:has-text('已平仓')").first
            closed_tab.click()
            time.sleep(1)
            
            # Extract DOM content
            dom_content = page.content()
            
            # Verify position appears in DOM
            if "宏昌电子" not in dom_content or "603002" not in dom_content:
                print("❌ FAIL: Position not found in /observations DOM")
                browser.close()
                return 1
            
            print("✅ Position found in /observations DOM")
            
            # Save DOM evidence
            dom_path = PROJECT_ROOT / "docs/verification/p2-1d-observations-dom.md"
            with open(dom_path, "w", encoding="utf-8") as f:
                f.write("# P2-1D Observations DOM Evidence\n\n")
                f.write(f"**Timestamp**: {datetime.now().isoformat()}\n\n")
                f.write(f"**URL**: http://localhost:3000/observations?status=closed\n\n")
                f.write(f"**Position ID**: {position_id}\n\n")
                f.write(f"**Position found in DOM**: Yes\n\n")
                f.write("## Sample DOM Content\n\n")
                f.write("```html\n")
                # Extract a snippet around 宏昌电子
                idx = dom_content.find("宏昌电子")
                if idx != -1:
                    snippet = dom_content[max(0, idx-200):idx+200]
                    f.write(snippet)
                f.write("\n```\n")
            
            # Step 12: Save network logs
            print("\n[12/12] Saving network logs...")
            
            buy_log_path = PROJECT_ROOT / "docs/verification/p2-1d-buy-workbench-network-log.json"
            with open(buy_log_path, "w", encoding="utf-8") as f:
                json.dump({
                    "requests": buy_requests[:1] if buy_requests else [],
                    "response": buy_response_data,
                }, f, indent=2, ensure_ascii=False)
            
            sell_log_path = PROJECT_ROOT / "docs/verification/p2-1d-sell-workbench-network-log.json"
            with open(sell_log_path, "w", encoding="utf-8") as f:
                json.dump({
                    "requests": buy_requests[1:] if len(buy_requests) > 1 else [],
                    "response": sell_response_data,
                }, f, indent=2, ensure_ascii=False)
            
            print("✅ All network logs saved")
            
            browser.close()
        
        print("\n" + "=" * 100)
        print("✅ P2-1D VERIFICATION PASSED")
        print("=" * 100)
        print()
        print("Evidence files:")
        print("  - docs/verification/p2-1d-buy-workbench-network-log.json")
        print("  - docs/verification/p2-1d-sell-workbench-network-log.json")
        print("  - docs/verification/p2-1d-observations-open-api-before-sell.json")
        print("  - docs/verification/p2-1d-observations-closed-api.json")
        print("  - docs/verification/p2-1d-observations-dom.md")
        print("  - docs/verification/p2-1d-review-or-pnl-api.json")
        print("  - docs/verification/p2-1d-db-path-check.json")
        print("  - docs/verification/p2-1d-backend-log.txt")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        print("\nCleaning up processes...")
        if backend_proc:
            backend_proc.terminate()
            try:
                backend_proc.wait(timeout=5)
            except:
                backend_proc.kill()
        if frontend_proc:
            frontend_proc.terminate()
            try:
                frontend_proc.wait(timeout=5)
            except:
                frontend_proc.kill()
        if backend_log_file:
            backend_log_file.close()
        print("✅ Cleanup complete")


if __name__ == "__main__":
    sys.exit(main())
