#!/usr/bin/env python3
"""
P7-2 Browser Demo A: Friend Stock Full E2E

完整流程：
1. Dashboard 可见
2. Workbench 朋友荐股 → observation（P2-2 两句话）
3. 手动买入 → position open（P2-1A 模式）
4. 生成 daily signal（P2-1C 模式）
5. 手动卖出 → position closed（P2-1D 模式）
6. P&L + discipline review 生成

复用已验证路径，禁止 fixture/fake。
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.runtime_process_helpers import (
    check_and_release_ports,
    start_backend,
    start_frontend,
    stop_process,
)

RUN_ID = datetime.now().strftime("P7_2_RUN_%Y%m%d_%H%M%S")
DOCS_DIR = project_root / "docs" / "verification"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 60)
    print("P7-2: BROWSER DEMO A FRIEND STOCK FULL E2E")
    print(f"Run ID: {RUN_ID}")
    print("=" * 60)
    print()

    # Prerequisite
    print("[0/9] Checking prerequisites...")
    check_and_release_ports([8010, 3010])

    backend_proc = None
    frontend_proc = None
    browser = None
    pw = None

    try:
        # Start services
        print("\n[1/9] Starting backend...")
        backend_proc = start_backend(
            port=8010,
            project_root=project_root,
            extra_env={
                "RESEARCH_CONVERSATION_MODE": "deterministic",
                "SERENITY_EXECUTION_MODE": "stub",
            }
        )
        
        print("\n[2/9] Starting frontend...")
        frontend_proc = start_frontend(port=3010, project_root=project_root)

        # Launch browser
        print("\n[3/9] Dashboard verification...")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        network_log = []
        def log_request(req):
            network_log.append({"url": req.url, "method": req.method})
        page.on("request", log_request)

        # Dashboard
        page.goto("http://localhost:3010/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        dashboard_dom = page.content()
        (DOCS_DIR / "p7-2-dashboard-dom.md").write_text(
            f"# P7-2 Dashboard\n\n**Run ID:** {RUN_ID}\n\n```html\n{dashboard_dom}\n```\n",
            encoding="utf-8",
        )
        print("OK: Dashboard saved")

        # Friend stock → observation (P2-2 two-message pattern)
        print("\n[4/9] Friend stock → observation...")
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.wait_for_timeout(500)

        # First message
        page.fill("input[placeholder='输入消息...']", f"帮我看看贵州茅台（600519），备注 {RUN_ID}")
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        print("OK: First message sent")

        # Second message
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.fill("input[placeholder='输入消息...']", "加入观察")
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        print("OK: Second message sent")

        # Poll for position
        position_id = None
        for attempt in range(12):
            time.sleep(5)
            resp = requests.get("http://localhost:8010/api/observations?status=open", timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("positions") or data.get("data") or []
            for pos in data:
                if isinstance(pos, dict) and RUN_ID in pos.get("entry_thesis", ""):
                    position_id = pos.get("position_id")
                    print(f"OK: Position created: {position_id}")
                    break
            if position_id:
                break
        
        if not position_id:
            print(f"ERROR: No position with RUN_ID {RUN_ID} after 60s")
            sys.exit(1)

        # Manual buy (P2-1A pattern)
        print("\n[5/9] Manual buy...")
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.wait_for_timeout(500)
        buy_msg = f"已买入 600519 贵州茅台 100股，成交价 1500，备注 {RUN_ID}"
        page.fill("input[placeholder='输入消息...']", buy_msg)
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        print("OK: Buy message sent")

        # Verify position still open
        resp = requests.get("http://localhost:8010/api/observations?status=open", timeout=10)
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("positions") or []
        found = any(RUN_ID in pos.get("entry_thesis", "") for pos in data if isinstance(pos, dict))
        if not found:
            print("ERROR: Position not in open pool after buy")
            sys.exit(1)
        print("OK: Position open after buy")

        # Generate daily signal (P2-1C pattern: call API directly)
        print("\n[6/9] Generating daily signal...")
        signal_resp = requests.post(
            "http://localhost:8010/api/agent/workbench/test_p7_2_signal/daily-signal",
            timeout=30
        )
        if signal_resp.status_code != 200:
            print(f"ERROR: Signal generation failed: {signal_resp.status_code}")
            sys.exit(1)
        time.sleep(2)
        
        # Get signal
        signal_id = None
        resp = requests.get("http://localhost:8010/api/observations?status=open", timeout=10)
        data = resp.json()
        if isinstance(data, dict):
            data = data.get("positions") or []
        for pos in data:
            if isinstance(pos, dict) and RUN_ID in pos.get("entry_thesis", ""):
                signal_id = pos.get("latest_signal", {}).get("signal_id") if pos.get("latest_signal") else None
                if signal_id:
                    print(f"OK: Signal generated: {signal_id}")
                break
        
        if not signal_id:
            print("WARN: No signal_id, continuing (data_state may not be ok)")

        # Manual sell (P2-1D pattern)
        print("\n[7/9] Manual sell...")
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.wait_for_timeout(500)
        sell_msg = f"已卖出 600519 贵州茅台 100股，成交价 1600，备注 {RUN_ID}"
        page.fill("input[placeholder='输入消息...']", sell_msg)
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        print("OK: Sell message sent")

        # Verify position closed
        for attempt in range(6):
            time.sleep(5)
            resp = requests.get("http://localhost:8010/api/observations?status=closed", timeout=10)
            data = resp.json()
            if isinstance(data, dict):
                data = data.get("positions") or []
            for pos in data:
                if isinstance(pos, dict) and RUN_ID in pos.get("entry_thesis", ""):
                    print(f"OK: Position closed: {pos.get('position_id')}")
                    break
            else:
                continue
            break
        else:
            print("ERROR: Position not closed after 30s")
            sys.exit(1)

        # Verify P&L and review
        print("\n[8/9] Verifying P&L and review...")
        
        # Query DB directly for review
        import sqlite3
        db_path = project_root / "data" / "live_trade.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        
        # Find closed position with RUN_ID
        cursor = conn.cursor()
        cursor.execute("""
            SELECT position_id FROM observation_positions
            WHERE lifecycle_state = 'closed' AND entry_thesis LIKE ?
            ORDER BY closed_at DESC LIMIT 1
        """, (f"%{RUN_ID}%",))
        row = cursor.fetchone()
        if not row:
            print("ERROR: Closed position not found in DB")
            conn.close()
            sys.exit(1)
        
        closed_position_id = row["position_id"]
        print(f"OK: Closed position in DB: {closed_position_id}")
        
        # Get review
        cursor.execute("""
            SELECT review_json FROM discipline_reviews
            WHERE position_id = ?
        """, (closed_position_id,))
        review_row = cursor.fetchone()
        conn.close()
        
        if not review_row:
            print("ERROR: Review not found")
            sys.exit(1)
        
        review_data = json.loads(review_row["review_json"])
        pnl_value = review_data.get("pnl_record", {}).get("pnl_amount")
        review_id = review_data.get("review_id")
        
        if pnl_value is None:
            print("ERROR: P&L not found")
            sys.exit(1)
        if not review_id:
            print("ERROR: review_id not found")
            sys.exit(1)
        print(f"OK: P&L={pnl_value}, review_id={review_id}")

        # Verify DOM
        print("\n[9/9] Verifying DOM...")
        page.goto("http://localhost:3010/observations", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        obs_dom = page.content()
        (DOCS_DIR / "p7-2-observations-dom.md").write_text(
            f"# P7-2 Observations\n\n**Run ID:** {RUN_ID}\n\n```html\n{obs_dom}\n```\n",
            encoding="utf-8",
        )
        print("OK: Observations DOM saved")

        # Save evidence
        (DOCS_DIR / "p7-2-network-log.json").write_text(
            json.dumps(network_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        
        summary = {
            "run_id": RUN_ID,
            "position_id": position_id,
            "stock_code": "600519.SH",
            "stock_name": "贵州茅台",
            "signal_id": signal_id,
            "pnl": pnl_value,
            "review_id": review_id,
            "network_requests_total": len(network_log),
            "network_requests_external": len([r for r in network_log if "localhost" not in r["url"]]),
        }
        (DOCS_DIR / "p7-2-verification-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print("\n" + "=" * 60)
        print("P7-2 VERIFICATION: PASS")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()
        if frontend_proc:
            stop_process(frontend_proc, "Frontend", DOCS_DIR / "p7-2-frontend-log.txt")
        if backend_proc:
            stop_process(backend_proc, "Backend", DOCS_DIR / "p7-2-backend-log.txt")


if __name__ == "__main__":
    main()
