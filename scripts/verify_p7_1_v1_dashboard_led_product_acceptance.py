"""
P7-1: V1 Dashboard-Led Product Acceptance

Phase 7 E2E verification (simplified):
- Dashboard visibility
- Workbench → Observation flow
- Workbench → Strategy flow
- Risk guard display-only
- No mojibake, localhost-only network
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

RUN_ID = datetime.now().strftime("P7_1_RUN_%Y%m%d_%H%M%S")
DOCS_DIR = project_root / "docs" / "verification"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def check_mojibake(text: str) -> list[str]:
    """Check for common GBK→UTF-8 mojibake patterns."""
    patterns = ["鉁", "鈫", "鏁", "鏆", "宸", "绛", "瑙", "鍊"]
    found = [p for p in patterns if p in text]
    return found


def main():
    print("=" * 60)
    print("P7-1: V1 DASHBOARD-LED PRODUCT ACCEPTANCE")
    print(f"Run ID: {RUN_ID}")
    print("=" * 60)
    print()

    # Prerequisite check
    print("[0/8] Checking prerequisites...")
    check_and_release_ports([8010, 3010])

    backend_proc = None
    frontend_proc = None
    browser = None
    pw = None

    try:
        # Start services
        print("\n[1/8] Starting backend...")
        backend_proc = start_backend(
            port=8010,
            project_root=project_root,
            extra_env={
                "RESEARCH_CONVERSATION_MODE": "deterministic",
                "SERENITY_EXECUTION_MODE": "stub",
            }
        )
        
        print("\n[2/8] Starting frontend...")
        frontend_proc = start_frontend(port=3010, project_root=project_root)

        # Launch browser
        print("\n[3/8] Launching browser...")
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        network_log = []
        def log_request(req):
            network_log.append({"url": req.url, "method": req.method})
        page.on("request", log_request)

        # Dashboard verification
        print("\n[4/8] Verifying dashboard...")
        page.goto("http://localhost:3010/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        
        dashboard_dom = page.content()
        dashboard_text = page.inner_text("body")
        
        # Save DOM
        (DOCS_DIR / "p7-1-dashboard-dom.md").write_text(
            f"# P7-1 Dashboard DOM\n\n**Run ID:** {RUN_ID}\n\n```html\n{dashboard_dom}\n```\n",
            encoding="utf-8",
        )
        print("OK: Dashboard DOM saved")

        # Check sections
        required = ["每日工作台", "持仓观察", "策略工作区"]
        missing = [r for r in required if r not in dashboard_text]
        if missing:
            print(f"ERROR: Dashboard missing: {missing}")
            sys.exit(1)
        print(f"OK: Dashboard sections present")

        # Check mojibake
        mojibake = check_mojibake(dashboard_text)
        if mojibake:
            print(f"ERROR: Mojibake found: {mojibake}")
            sys.exit(1)
        print("OK: No mojibake")

        # Flow A: Workbench → Friend stock → add to observation (P2-2 pattern)
        print("\n[5/8] Flow A: Workbench → Friend Stock → Observation...")
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("h1:has-text('TraderLens 工作台')", timeout=10000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.wait_for_timeout(500)

        # First message: friend stock
        friend_msg = f"帮我看看贵州茅台（600519），备注 {RUN_ID}"
        page.fill("input[placeholder='输入消息...']", friend_msg)
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)  # ponytail: P2-2 uses 5s for backend processing
        print(f"OK: First message sent")

        # Second message: add to observation
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.fill("input[placeholder='输入消息...']", "加入观察")
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        print(f"OK: Second message sent")

        # Poll /api/observations for position (max 60s)
        position_id = None
        friend_conversation_id = None
        for attempt in range(12):  # 12 * 5s = 60s
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
                    # ponytail: conversation_id not in position API, extract from workbench DOM if needed
                    print(f"OK: Position created: {position_id}")
                    break
            if position_id:
                break
        
        if not position_id:
            print(f"ERROR: No position found with RUN_ID {RUN_ID} after 60s")
            sys.exit(1)

        # Verify /observations DOM
        page.goto("http://localhost:3010/observations", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        obs_dom = page.content()
        if RUN_ID not in obs_dom and position_id not in obs_dom:
            print(f"ERROR: Neither RUN_ID nor position_id in /observations DOM")
            sys.exit(1)
        (DOCS_DIR / "p7-1-observations-dom.md").write_text(
            f"# P7-1 Observations DOM\n\n**Run ID:** {RUN_ID}\n**Position ID:** {position_id}\n\n```html\n{obs_dom}\n```\n",
            encoding="utf-8",
        )
        print("OK: Observation verified in DOM")

        # Flow B: Workbench → Strategy
        print("\n[6/8] Flow B: Workbench → Strategy → Strategy Workspace...")
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.wait_for_timeout(500)

        strategy_msg = f"[{RUN_ID}] 下午两点半买入，第二天早上卖出"
        page.fill("input[placeholder='输入消息...']", strategy_msg)
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        print(f"OK: Strategy message sent")

        # Poll /api/strategy-ideas for idea_id
        idea_id = None
        strategy_conversation_id = None
        for attempt in range(12):
            time.sleep(5)
            try:
                resp = requests.get("http://localhost:8010/api/strategy-ideas", timeout=10)
                if resp.status_code != 200:
                    continue
                data = resp.json()
                if isinstance(data, dict):
                    data = data.get("ideas") or data.get("data") or []
                for idea in data:
                    if isinstance(idea, dict) and RUN_ID in idea.get("original_description", ""):
                        idea_id = idea.get("idea_id")
                        strategy_conversation_id = idea.get("conversation_id")  # ponytail: may not exist in API
                        print(f"OK: Strategy idea created: {idea_id}")
                        break
                if idea_id:
                    break
            except:
                continue
        
        if not idea_id:
            print(f"ERROR: No idea found with RUN_ID {RUN_ID} after 60s")
            sys.exit(1)

        # Verify strategy pages DOM
        for name, url in [
            ("strategy-ideas", "/strategy-ideas"),
            ("candidate", "/candidate-strategies"),
            ("rejected", "/rejected-strategies"),
        ]:
            page.goto(f"http://localhost:3010{url}", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1000)
            dom = page.content()
            (DOCS_DIR / f"p7-1-{name}-dom.md").write_text(
                f"# P7-1 {name.title()} DOM\n\n**Run ID:** {RUN_ID}\n**Idea ID:** {idea_id}\n\n```html\n{dom}\n```\n",
                encoding="utf-8",
            )
        print("OK: Strategy workspace pages saved")

        # Risk guard verification
        print("\n[7/8] Verifying risk guard...")
        dashboard_api = requests.get("http://localhost:8010/api/dashboard/today", timeout=10).json()
        risk_guard = dashboard_api.get("risk_guard", {})
        
        if risk_guard.get("data_state") == "ok":
            print("ERROR: risk_guard.data_state is 'ok'")
            sys.exit(1)
        if risk_guard.get("blocks_count", 0) != 0 or risk_guard.get("downgrades_count", 0) != 0:
            print(f"ERROR: risk_guard counts non-zero")
            sys.exit(1)
        print(f"OK: risk_guard.data_state = {risk_guard.get('data_state')}")

        # Network verification
        print("\n[8/8] Verifying network log...")
        external = [r for r in network_log if "localhost" not in r["url"]]
        if external:
            print(f"ERROR: {len(external)} external requests found")
            for req in external[:3]:
                print(f"  {req['method']} {req['url']}")
            sys.exit(1)
        print(f"OK: All {len(network_log)} requests to localhost")

        # Save evidence
        (DOCS_DIR / "p7-1-network-log.json").write_text(
            json.dumps(network_log, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        
        summary = {
            "run_id": RUN_ID,
            "friend_position_id": position_id,
            "strategy_idea_id": idea_id,
            "risk_guard_data_state": risk_guard.get("data_state"),
            "network_requests_total": len(network_log),
            "network_requests_external": len(external),
        }
        (DOCS_DIR / "p7-1-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        print("\n" + "=" * 60)
        print("P7-1 VERIFICATION: PASS")
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
            stop_process(frontend_proc, "Frontend", DOCS_DIR / "p7-1-frontend-log.txt")
        if backend_proc:
            stop_process(backend_proc, "Backend", DOCS_DIR / "p7-1-backend-log.txt")


if __name__ == "__main__":
    main()
