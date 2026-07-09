#!/usr/bin/env python3
"""
P7-3 Browser Demo B: Strategy Full E2E

Dashboard → Workbench strategy → idea → extraction → mapping → rejection
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.runtime_process_helpers import (
    check_and_release_ports,
    start_backend,
    start_frontend,
    stop_process,
)

RUN_ID = datetime.now().strftime("P7_3_RUN_%Y%m%d_%H%M%S")
DOCS_DIR = Path(__file__).parent.parent / "docs" / "verification"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def main():
    print("=" * 60)
    print("P7-3: BROWSER DEMO B STRATEGY FULL E2E")
    print(f"Run ID: {RUN_ID}")
    print("=" * 60)
    print()

    check_and_release_ports([8010, 3010])

    backend_proc = start_backend(
        port=8010,
        project_root=Path(__file__).parent.parent,
        extra_env={
            "RESEARCH_CONVERSATION_MODE": "deterministic",
            "SERENITY_EXECUTION_MODE": "stub",
        }
    )
    frontend_proc = start_frontend(port=3010, project_root=Path(__file__).parent.parent)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    network_log = []
    page.on("request", lambda req: network_log.append({"url": req.url, "method": req.method}))

    try:
        # Dashboard
        page.goto("http://localhost:3010/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1000)
        (DOCS_DIR / "p7-3-dashboard-dom.md").write_text(f"# Dashboard\n\n{page.content()}", encoding="utf-8")
        print("[1/8] Dashboard OK")

        # Workbench
        page.goto("http://localhost:3010/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        page.wait_for_timeout(500)
        
        strategy_msg = f"[{RUN_ID}] 我刷到一个策略，下午两点半买入，第二天早上卖出，请帮我验证"
        page.fill("input[placeholder='输入消息...']", strategy_msg)
        page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=5000)
        page.click("button:has-text('发送')")
        page.wait_for_timeout(5000)
        
        (DOCS_DIR / "p7-3-workbench-dom.md").write_text(f"# Workbench\n\n{page.content()}", encoding="utf-8")
        print("[2/8] Strategy submitted")

        # Get idea_id from API
        resp = requests.get("http://localhost:8010/api/strategy-ideas", timeout=10)
        ideas = resp.json().get("ideas", [])
        idea = next((i for i in ideas if RUN_ID in i.get("original_message", "")), None)
        if not idea:
            print("ERROR: Idea not found")
            sys.exit(1)
        
        idea_id = idea["idea_id"]
        conversation_id = idea.get("conversation_id")
        print(f"[3/8] idea_id={idea_id}, conversation_id={conversation_id}")

        # Get detail
        detail_resp = requests.get(f"http://localhost:8010/api/strategy-ideas/{idea_id}", timeout=10)
        detail = detail_resp.json()
        (DOCS_DIR / "p7-3-api-evidence.json").write_text(json.dumps(detail, indent=2, ensure_ascii=False), encoding="utf-8")

        # Verify workflow
        if detail.get("workflow_type") != "strategy_idea":
            print(f"ERROR: workflow_type={detail.get('workflow_type')}, expected strategy_idea")
            sys.exit(1)
        print("[4/8] workflow_type OK")

        # Strategy detail page
        page.goto(f"http://localhost:3010/strategy-ideas/{idea_id}", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        (DOCS_DIR / "p7-3-strategy-detail-dom.md").write_text(f"# Strategy Detail\n\n{page.content()}", encoding="utf-8")
        
        detail_dom = page.content()
        if idea_id not in detail_dom:
            print("ERROR: idea_id not in detail DOM")
            sys.exit(1)
        print("[5/8] Strategy detail OK")

        # Rejected registry
        page.goto("http://localhost:3010/rejected-strategies", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        (DOCS_DIR / "p7-3-rejected-registry-dom.md").write_text(f"# Rejected\n\n{page.content()}", encoding="utf-8")
        print("[6/8] Rejected registry OK")

        # Candidate registry
        page.goto("http://localhost:3010/candidate-strategies", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        (DOCS_DIR / "p7-3-candidate-registry-dom.md").write_text(f"# Candidate\n\n{page.content()}", encoding="utf-8")
        print("[7/8] Candidate registry OK")

        # Approved strategies (should be empty)
        page.goto("http://localhost:3010/strategies", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        (DOCS_DIR / "p7-3-strategies-dom.md").write_text(f"# Approved\n\n{page.content()}", encoding="utf-8")
        
        resp = requests.get("http://localhost:8010/api/strategies?status=approved", timeout=10)
        approved_count = len(resp.json().get("strategies", []))
        if approved_count != 0:
            print(f"ERROR: approved_count={approved_count}, expected 0")
            sys.exit(1)
        print("[8/8] Approved strategies=0 OK")

        # Summary
        summary = {
            "run_id": RUN_ID,
            "conversation_id": conversation_id,
            "idea_id": idea_id,
            "workflow_type": detail.get("workflow_type"),
            "decision": detail.get("decision"),
            "candidate_status": detail.get("candidate_status"),
            "mapped_template_id": detail.get("mapped_template_id"),
            "considered_template_ids_count": len(detail.get("considered_template_ids", [])),
            "mismatch_reasons_count": len(detail.get("mismatch_reasons", [])),
            "final_reason": detail.get("final_reason"),
            "approved_strategies_count": approved_count,
            "network_requests_total": len(network_log),
            "network_requests_external": len([r for r in network_log if "localhost" not in r["url"]]),
        }
        (DOCS_DIR / "p7-3-verification-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        (DOCS_DIR / "p7-3-network-log.json").write_text(json.dumps(network_log, indent=2, ensure_ascii=False), encoding="utf-8")

        print("\n" + "=" * 60)
        print("P7-3 VERIFICATION: PASS")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        browser.close()
        pw.stop()
        stop_process(frontend_proc, "Frontend", DOCS_DIR / "p7-3-frontend-log.txt")
        stop_process(backend_proc, "Backend", DOCS_DIR / "p7-3-backend-log.txt")


if __name__ == "__main__":
    main()
