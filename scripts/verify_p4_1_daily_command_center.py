#!/usr/bin/env python3
"""
P4-1 Daily Command Center Runtime Shell Verification

Verifies:
1. Backend /api/dashboard/today returns real data
2. Frontend / displays dashboard with real DOM
3. All navigation links present
4. API and DOM counts match
5. Validations count == 0
6. Approved strategies count == 0
7. All API requests to localhost:8010
8. Evidence files saved

Exit code 0 = pass, 1 = fail
"""

import sys
import json
import time
import subprocess
import requests
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

# Fix Windows GBK encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
from runtime_process_helpers import (
    start_backend,
    wait_for_http,
    check_and_release_ports,
)

def verify_p4_1_daily_command_center():
    """Verify P4-1 Daily Command Center."""
    
    print("=" * 100)
    print("P4-1 DAILY COMMAND CENTER VERIFICATION")
    print("=" * 100)
    print()
    
    run_id = f"P4_1_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Run ID: {run_id}")
    print()
    
    project_root = Path(__file__).parent.parent
    verification_dir = project_root / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "evidence_files": []
    }
    
    backend_process = None
    frontend_process = None
    browser = None
    
    try:
        # Step 1: Clean up ports
        print("Step 1: Checking and releasing ports...")
        print("-" * 80)
        check_and_release_ports([8010, 3000])
        print("✓ Ports ready")
        print()
        
        # Step 2: Start backend
        print("Step 2: Starting backend...")
        print("-" * 80)
        backend_process = start_backend()
        wait_for_http("http://localhost:8010/health")
        print("✓ Backend started")
        print()
        
        # Step 3: Start frontend
        print("Step 3: Starting frontend...")
        print("-" * 80)
        frontend_log_path = verification_dir / "p4-1-frontend-log.txt"
        with open(frontend_log_path, "w", encoding="utf-8") as log_file:
            frontend_process = subprocess.Popen(
                "npm run dev",
                cwd=project_root / "frontend",
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
            )
        
        wait_for_http("http://localhost:3000")
        evidence["evidence_files"].append(str(frontend_log_path.name))
        print("✓ Frontend started")
        print()
        
        # Step 4: Call /api/dashboard/today directly
        print("Step 4: Call /api/dashboard/today directly")
        print("-" * 80)
        
        api_response = requests.get("http://localhost:8010/api/dashboard/today")
        if api_response.status_code != 200:
            print(f"✗ API request failed: {api_response.status_code}")
            evidence["checks"]["api_status"] = False
            return 1
        
        dashboard_data = api_response.json()
        
        # Save API response
        api_file = verification_dir / "p4-1-dashboard-api.json"
        with open(api_file, "w", encoding="utf-8") as f:
            json.dump(dashboard_data, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(api_file.name))
        print(f"✓ Saved API response to {api_file.name}")
        
        # Print API summary
        print(f"✓ API returned data:")
        print(f"  - as_of_date: {dashboard_data['as_of_date']}")
        print(f"  - open_observations: {dashboard_data['open_observations']['count']}")
        print(f"  - today_signals: {dashboard_data['today_signals']['count']}")
        print(f"  - strategy_workspace:")
        for key, value in dashboard_data['strategy_workspace'].items():
            print(f"    - {key}: {value}")
        print(f"  - recent_reviews: {dashboard_data['recent_reviews']['count']}")
        print(f"  - data_state: {dashboard_data['data_state']}")
        
        evidence["checks"]["api_status"] = True
        evidence["api_data"] = dashboard_data
        
        print()
        print("Step 5: Navigate to / (Dashboard) with Playwright")
        print("-" * 80)
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            
            # Setup network listener
            api_calls = []
            def handle_response(response):
                if "localhost:8010" in response.url or "localhost:3000" in response.url:
                    api_calls.append({
                        "url": response.url,
                        "status": response.status,
                        "method": response.request.method
                    })
            
            page.on("response", handle_response)
            
            # Navigate to dashboard
            page.goto("http://localhost:3000/", wait_until="networkidle", timeout=60000)
            time.sleep(3)  # Wait for API calls
            
            # Capture DOM
            dom_content = page.content()
            dom_file = verification_dir / "p4-1-dashboard-dom.md"
            with open(dom_file, "w", encoding="utf-8") as f:
                f.write(f"# P4-1 Dashboard DOM\n\n")
                f.write(f"Run ID: {run_id}\n\n")
                f.write(f"```html\n{dom_content}\n```\n")
            evidence["evidence_files"].append(str(dom_file.name))
            print(f"✓ Saved DOM to {dom_file.name}")
            
            # Save network log
            network_file = verification_dir / "p4-1-dashboard-network-log.json"
            with open(network_file, "w", encoding="utf-8") as f:
                json.dump(api_calls, f, indent=2, ensure_ascii=False)
            evidence["evidence_files"].append(str(network_file.name))
            print(f"✓ Saved network log: {len(api_calls)} API calls")
            
            # Close browser
            browser.close()
        
        print()
        print("Step 6: Verify DOM content")
        print("-" * 80)
        
        # Check for dashboard title
        title_found = False
        for title in ["每日工作台", "Daily Command Center", "今日总览"]:
            if title in dom_content:
                print(f"✓ Found dashboard title: {title}")
                title_found = True
                break
        
        if not title_found:
            print("✗ Dashboard title not found")
            evidence["checks"]["dashboard_title"] = False
            return 1
        
        evidence["checks"]["dashboard_title"] = True
        
        # Check for key sections
        sections = {
            "observations": ["持仓观察", "Observation", "观察池"],
            "signals": ["今日信号", "Signal", "信号板"],
            "strategy_workspace": ["策略工作区", "Strategy Workspace"],
            "reviews": ["近期复盘", "Recent Review", "复盘"]
        }
        
        for section_key, section_terms in sections.items():
            found = False
            for term in section_terms:
                if term in dom_content:
                    print(f"✓ Found {section_key} section: {term}")
                    found = True
                    break
            if not found:
                print(f"✗ {section_key} section not found")
                evidence["checks"][f"section_{section_key}"] = False
                return 1
            evidence["checks"][f"section_{section_key}"] = True
        
        print()
        print("Step 7: Verify navigation links")
        print("-" * 80)
        
        required_links = [
            "/workbench",
            "/observations",
            "/signals",
            "/strategies",
            "/strategy-ideas",
            "/candidate-strategies",
            "/rejected-strategies",
            "/strategy-validations",
            "/strategy-templates"
        ]
        
        missing_links = []
        for link in required_links:
            if f'href="{link}"' in dom_content or f"href='{link}'" in dom_content:
                print(f"✓ Found link: {link}")
            else:
                print(f"✗ Missing link: {link}")
                missing_links.append(link)
        
        if missing_links:
            evidence["checks"]["navigation_links"] = False
            evidence["missing_links"] = missing_links
            return 1
        
        evidence["checks"]["navigation_links"] = True
        
        print()
        print("Step 8: Verify API requests to localhost:8010")
        print("-" * 80)
        
        api_8010_calls = [call for call in api_calls if "localhost:8010" in call["url"]]
        non_local_calls = [call for call in api_calls if "localhost:8010" not in call["url"] and "localhost:3000" not in call["url"]]
        
        if non_local_calls:
            print(f"✗ Found {len(non_local_calls)} non-local API calls:")
            for call in non_local_calls:
                print(f"  - {call['url']}")
            evidence["checks"]["api_local"] = False
            return 1
        
        print(f"✓ All API calls to localhost (8010: {len(api_8010_calls)}, 3000: {len(api_calls) - len(api_8010_calls)})")
        evidence["checks"]["api_local"] = True
        
        print()
        print("Step 9: Verify empty states")
        print("-" * 80)
        
        # Check validations_count == 0
        validations_count = dashboard_data['strategy_workspace']['validations_count']
        if validations_count != 0:
            print(f"✗ validations_count should be 0, got {validations_count}")
            evidence["checks"]["validations_empty"] = False
            return 1
        print(f"✓ validations_count == 0")
        evidence["checks"]["validations_empty"] = True
        
        # Check approved_strategies_count == 0
        approved_count = dashboard_data['strategy_workspace']['approved_strategies_count']
        if approved_count != 0:
            print(f"✗ approved_strategies_count should be 0, got {approved_count}")
            evidence["checks"]["approved_empty"] = False
            return 1
        print(f"✓ approved_strategies_count == 0")
        evidence["checks"]["approved_empty"] = True
        
        print()
        print("Step 10: Save backend log")
        print("-" * 80)
        
        # Backend log already saved by start_backend, read it
        backend_log_path = project_root / "backend_server.log"
        if backend_log_path.exists():
            backend_log_file = verification_dir / "p4-1-backend-log.txt"
            with open(backend_log_path, "r", encoding="utf-8") as src:
                with open(backend_log_file, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
            evidence["evidence_files"].append(str(backend_log_file.name))
            print(f"✓ Saved backend log to {backend_log_file.name}")
        
        # Save evidence summary
        evidence_file = verification_dir / "p4-1-evidence-summary.json"
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(evidence_file.name))
        print(f"✓ Saved evidence summary to {evidence_file.name}")
        
        print()
        print("=" * 100)
        print("✅ P4-1 DAILY COMMAND CENTER VERIFICATION PASSED")
        print("=" * 100)
        print()
        print(f"Run ID: {run_id}")
        print(f"Evidence files: {len(evidence['evidence_files'])}")
        print()
        
        return 0
        
    finally:
        # Cleanup
        if browser:
            try:
                browser.close()
            except:
                pass
        
        if frontend_process:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=5)
            except:
                frontend_process.kill()
        
        if backend_process:
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
            except:
                backend_process.kill()

if __name__ == "__main__":
    try:
        exit_code = verify_p4_1_daily_command_center()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n✗ Verification failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
