#!/usr/bin/env python3
"""
P4-4 Dashboard Data Freshness and State Verification

Verifies:
1. GET /api/dashboard/today returns data_state/message for all 4 sections
2. data_state is one of: ok | empty | stale | unavailable
3. Business rules:
   - today_signals.count == 0 → data_state == empty
   - recent_reviews.count == 0 → data_state == empty
   - strategy_workspace.ideas_count > 0 → data_state == ok
   - open_observations.count >= 0 and data_state is legal
4. Frontend DOM displays all 4 section states (not placeholder)
5. All API requests point to localhost:8010

Real browser verification with Playwright - no API-only downgrade.

Exit code 0 = pass, 1 = fail
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

# Fix Windows GBK encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
from runtime_process_helpers import (
    start_backend,
    start_frontend,
    stop_process,
    check_and_release_ports,
)


def verify_p4_4_dashboard_data_freshness():
    """Verify P4-4 Dashboard Data Freshness and State."""
    
    print("=" * 100)
    print("P4-4 DASHBOARD DATA FRESHNESS AND STATE VERIFICATION")
    print("=" * 100)
    print()
    
    run_id = f"P4_4_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Run ID: {run_id}")
    print()
    
    project_root = Path(__file__).parent.parent
    verification_dir = project_root / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "api_response": {},
        "sections": {},
        "checks": {},
        "evidence_files": [],
        "network_requests": []
    }
    
    backend_process = None
    frontend_process = None
    browser = None
    playwright = None
    
    try:
        # Step 1: Clean up ports
        print("Step 1: Checking and releasing ports...")
        print("-" * 80)
        check_and_release_ports([8010, 3000])
        print("PASS Ports 8010, 3000 ready")
        print()
        
        # Step 2: Start backend
        print("Step 2: Starting backend...")
        print("-" * 80)
        backend_process = start_backend(
            port=8010,
            timeout_seconds=60,
            extra_env={
                "RESEARCH_CONVERSATION_MODE": "deterministic",
                "SERENITY_EXECUTION_MODE": "stub",
            },
        )
        print("PASS Backend started")
        print()
        
        # Step 3: Verify dashboard API
        print("Step 3: Verifying dashboard API...")
        print("-" * 80)
        
        import requests
        response = requests.get("http://localhost:8010/api/dashboard/today", timeout=10)
        if response.status_code != 200:
            print(f"FAIL Dashboard API returned {response.status_code}")
            return 1
        
        dashboard_data = response.json()
        evidence["api_response"] = dashboard_data
        
        # Save API response
        api_file = verification_dir / "p4-4-dashboard-api.json"
        with open(api_file, "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(api_file.relative_to(project_root)))
        print(f"PASS Dashboard API returned 200")
        print(f"     Saved to {api_file.relative_to(project_root)}")
        print()
        
        # Step 4: Verify all 4 sections have required fields
        print("Step 4: Verifying section structure...")
        print("-" * 80)
        
        required_sections = ["open_observations", "today_signals", "strategy_workspace", "recent_reviews"]
        legal_states = ["ok", "empty", "stale", "unavailable"]
        
        for section_name in required_sections:
            if section_name not in dashboard_data:
                print(f"FAIL Missing section: {section_name}")
                return 1
            
            section = dashboard_data[section_name]
            evidence["sections"][section_name] = {
                "count": section.get("count") or section.get("ideas_count", 0),
                "data_state": section.get("data_state"),
                "message": section.get("message"),
                "timestamp": section.get("updated_at") or section.get("as_of_date")
            }
            
            # Check required fields
            if "data_state" not in section:
                print(f"FAIL {section_name}: missing data_state")
                return 1
            
            if "message" not in section:
                print(f"FAIL {section_name}: missing message")
                return 1
            
            timestamp_field = "updated_at" if "updated_at" in section else "as_of_date"
            if timestamp_field not in section:
                print(f"FAIL {section_name}: missing {timestamp_field}")
                return 1
            
            # Check data_state is legal
            if section["data_state"] not in legal_states:
                print(f"FAIL {section_name}: data_state '{section['data_state']}' not in {legal_states}")
                return 1
            
            print(f"PASS {section_name}: has data_state/message/timestamp")
            print(f"     data_state={section['data_state']}, message={section['message']}")
        
        print()
        
        # Step 5: Verify business rules
        print("Step 5: Verifying business rules...")
        print("-" * 80)
        
        checks_passed = 0
        checks_total = 0
        
        # Rule 1: today_signals.count == 0 → data_state == empty
        checks_total += 1
        sig_count = dashboard_data["today_signals"]["count"]
        sig_state = dashboard_data["today_signals"]["data_state"]
        if sig_count == 0:
            if sig_state != "empty":
                print(f"FAIL today_signals.count=0 but data_state={sig_state} (expected empty)")
                return 1
            print(f"PASS today_signals.count=0 → data_state=empty")
            checks_passed += 1
        else:
            print(f"SKIP today_signals.count={sig_count} (rule only applies when count=0)")
        
        # Rule 2: recent_reviews.count == 0 → data_state == empty
        checks_total += 1
        rev_count = dashboard_data["recent_reviews"]["count"]
        rev_state = dashboard_data["recent_reviews"]["data_state"]
        if rev_count == 0:
            if rev_state != "empty":
                print(f"FAIL recent_reviews.count=0 but data_state={rev_state} (expected empty)")
                return 1
            print(f"PASS recent_reviews.count=0 → data_state=empty")
            checks_passed += 1
        else:
            print(f"SKIP recent_reviews.count={rev_count} (rule only applies when count=0)")
        
        # Rule 3: strategy_workspace.ideas_count > 0 → data_state == ok
        checks_total += 1
        ideas_count = dashboard_data["strategy_workspace"]["ideas_count"]
        strat_state = dashboard_data["strategy_workspace"]["data_state"]
        if ideas_count > 0:
            if strat_state != "ok":
                print(f"FAIL strategy_workspace.ideas_count={ideas_count} but data_state={strat_state} (expected ok)")
                return 1
            print(f"PASS strategy_workspace.ideas_count={ideas_count} → data_state=ok")
            checks_passed += 1
        else:
            print(f"SKIP strategy_workspace.ideas_count={ideas_count} (rule only applies when count>0)")
        
        # Rule 4: open_observations.count >= 0 and data_state is legal
        checks_total += 1
        obs_count = dashboard_data["open_observations"]["count"]
        obs_state = dashboard_data["open_observations"]["data_state"]
        if obs_count >= 0 and obs_state in legal_states:
            print(f"PASS open_observations.count={obs_count}, data_state={obs_state} (legal)")
            checks_passed += 1
        else:
            print(f"FAIL open_observations: count={obs_count}, data_state={obs_state}")
            return 1
        
        evidence["checks"]["business_rules_passed"] = checks_passed
        evidence["checks"]["business_rules_total"] = checks_total
        print()
        
        # Step 6: Start frontend
        print("Step 6: Starting frontend...")
        print("-" * 80)
        frontend_process = start_frontend(port=3000, timeout_seconds=90)
        print("PASS Frontend started")
        print()
        
        # Step 7: Playwright DOM verification
        print("Step 7: Verifying DOM state display...")
        print("-" * 80)
        
        from playwright.sync_api import sync_playwright
        
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Capture network requests
        network_log = []
        def handle_request(request):
            network_log.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
            })
        page.on("request", handle_request)
        
        # Navigate to dashboard
        page.goto("http://localhost:3000/", wait_until="networkidle", timeout=30000)
        time.sleep(2)  # Let React hydrate
        
        # Get page content
        page_content = page.content()
        
        # Save DOM
        dom_file = verification_dir / "p4-4-dashboard-dom.md"
        with open(dom_file, "w", encoding="utf-8") as f:
            f.write(f"# P4-4 Dashboard DOM\n\n")
            f.write(f"Run ID: {run_id}\n\n")
            f.write(f"```html\n{page_content}\n```\n")
        evidence["evidence_files"].append(str(dom_file.relative_to(project_root)))
        print(f"PASS Captured dashboard DOM")
        print(f"     Saved to {dom_file.relative_to(project_root)}")
        
        # Verify state badges for all 4 sections
        state_checks = [
            ("open_observations", "持仓观察"),
            ("today_signals", "今日信号"),
            ("strategy_workspace", "策略工作区"),
            ("recent_reviews", "近期复盘"),
        ]
        
        for section_key, section_label in state_checks:
            section_data = dashboard_data[section_key]
            expected_message = section_data["message"]
            
            # Check if message appears in DOM
            if expected_message not in page_content:
                print(f"FAIL {section_label}: message '{expected_message}' not found in DOM")
                return 1
            
            print(f"PASS {section_label}: state '{expected_message}' found in DOM")
        
        print()
        
        # Step 8: Verify network log
        print("Step 8: Verifying network requests...")
        print("-" * 80)
        
        # Save network log
        network_file = verification_dir / "p4-4-network-log.json"
        with open(network_file, "w", encoding="utf-8") as f:
            json.dump(network_log, f, indent=2)
        evidence["evidence_files"].append(str(network_file.relative_to(project_root)))
        evidence["network_requests"] = network_log
        
        # Verify all API requests are localhost
        api_requests = [req for req in network_log if req["resource_type"] in ["fetch", "xhr"]]
        external_apis = [req for req in api_requests if "localhost" not in req["url"]]
        
        if external_apis:
            print(f"FAIL Found {len(external_apis)} external API requests:")
            for req in external_apis:
                print(f"     {req['method']} {req['url']}")
            return 1
        
        backend_apis = [req for req in api_requests if "localhost:8010" in req["url"]]
        print(f"PASS All {len(api_requests)} API requests point to localhost")
        print(f"     Backend (localhost:8010): {len(backend_apis)}")
        print(f"     Saved to {network_file.relative_to(project_root)}")
        print()
        
        # Step 9: Save verification summary
        print("Step 9: Saving verification summary...")
        print("-" * 80)
        
        summary_file = verification_dir / "p4-4-verification-summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        print(f"PASS Saved summary to {summary_file.relative_to(project_root)}")
        print()
        
        # Success
        print("=" * 100)
        print("P4-4 VERIFICATION PASSED")
        print("=" * 100)
        print()
        print(f"Run ID: {run_id}")
        print(f"Evidence files: {len(evidence['evidence_files'])}")
        for ef in evidence["evidence_files"]:
            print(f"  - docs/verification/{Path(ef).name}")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\nFAIL Verification error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        # Cleanup
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        
        if frontend_process:
            frontend_log_file = verification_dir / "p4-4-frontend-log.txt"
            stop_process(frontend_process, "Frontend", save_log=frontend_log_file)
            if frontend_log_file.exists():
                evidence["evidence_files"].append(str(frontend_log_file.relative_to(project_root)))
        
        if backend_process:
            stop_process(backend_process, "Backend", release_ports=[8010])


if __name__ == "__main__":
    sys.exit(verify_p4_4_dashboard_data_freshness())
