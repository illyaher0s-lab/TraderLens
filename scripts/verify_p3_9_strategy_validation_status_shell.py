"""
P3-9 Strategy Validation Status Shell Verification

Verifies the minimal /strategy-validations page and API:
- GET /api/strategy-validations returns empty list
- /strategy-validations page displays empty state correctly
- /strategies hub shows 6 entry points
- Links work correctly
- No fake validation cases
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))
from runtime_process_helpers import (
    start_backend,
    wait_for_http,
    check_and_release_ports,
)


def run_verification():
    """Run P3-9 verification."""
    print("=" * 80)
    print("P3-9 STRATEGY VALIDATION STATUS SHELL VERIFICATION")
    print("=" * 80)
    
    run_id = f"P3_9_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n[INFO] Run ID: {run_id}\n")
    
    evidence_dir = Path(__file__).parent.parent / "docs" / "verification"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    backend_process = None
    frontend_process = None
    
    try:
        # Step 1: Clean up ports
        print("[STEP 1] Checking and releasing ports...")
        check_and_release_ports([8010, 3000])
        print("[OK] Ports ready\n")
        
        # Step 2: Start backend
        print("[STEP 2] Starting backend...")
        backend_process = start_backend()
        wait_for_http("http://localhost:8010/health")
        print("[OK] Backend started\n")
        
        # Step 3: Start frontend
        print("[STEP 3] Starting frontend...")
        frontend_log_path = evidence_dir / "p3-9-frontend-log.txt"
        with open(frontend_log_path, "w", encoding="utf-8") as log_file:
            frontend_process = subprocess.Popen(
                "npm run dev",
                cwd=Path(__file__).parent.parent / "frontend",
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                shell=True,
            )
        
        wait_for_http("http://localhost:3000")
        print("[OK] Frontend started\n")
        
        # Step 4: Verify API endpoint
        print("[STEP 4] Verifying /api/strategy-validations endpoint...")
        
        import urllib.request
        
        api_url = "http://localhost:8010/api/strategy-validations"
        with urllib.request.urlopen(api_url) as response:
            api_data = json.loads(response.read().decode())
        
        api_response_path = evidence_dir / "p3-9-validation-api.json"
        with open(api_response_path, "w", encoding="utf-8") as f:
            json.dump(api_data, f, indent=2, ensure_ascii=False)
        
        # Verify response structure
        if "validations" not in api_data:
            print("[FAIL] API response missing 'validations' field")
            return 1
        
        if "count" not in api_data:
            print("[FAIL] API response missing 'count' field")
            return 1
        
        # Verify empty state
        validations = api_data.get("validations", [])
        count = api_data.get("count", -1)
        
        if validations != []:
            print(f"[FAIL] Expected empty validations list, got {len(validations)} validations")
            print("[FAIL] Red line violation: No validation cases should exist")
            return 1
        
        if count != 0:
            print(f"[FAIL] Expected count=0, got count={count}")
            return 1
        
        print(f"[OK] API returns empty validation list")
        print(f"  validations: {validations}")
        print(f"  count: {count}")
        
        # Step 5: Verify /strategies hub has 6 entries
        print("\n[STEP 5] Verifying /strategies hub page...")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            
            # Listen to network requests
            network_log = []
            
            def log_request(request):
                network_log.append({
                    "url": request.url,
                    "method": request.method,
                    "timestamp": datetime.now().isoformat(),
                })
            
            def log_response(response):
                for entry in network_log:
                    if entry["url"] == response.url and "status" not in entry:
                        entry["status"] = response.status
            
            context.on("request", log_request)
            context.on("response", log_response)
            
            page = context.new_page()
            page.goto("http://localhost:3000/strategies", wait_until="networkidle")
            
            # Wait for page to render
            time.sleep(2)
            
            # Save hub DOM
            hub_dom = page.content()
            hub_dom_path = evidence_dir / "p3-9-strategies-hub-dom.md"
            with open(hub_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategies Hub DOM - {run_id}\n\n")
                f.write(hub_dom)
            
            # Verify 6 entry points/sections
            required_entries = [
                ("策略想法", "/strategy-ideas"),
                ("候选策略", "/candidate-strategies"),
                ("拒绝注册表", "/rejected-strategies"),
                ("策略模板", "/strategy-templates"),
                ("策略验证", "/strategy-validations"),
                ("已批准策略库", "count:"),
            ]
            
            page_html = page.content()
            missing_entries = []
            
            for label, search_term in required_entries:
                if search_term not in page_html:
                    missing_entries.append(f"{label} ({search_term})")
            
            if missing_entries:
                print(f"[FAIL] /strategies hub missing required entries: {missing_entries}")
                return 1
            
            print(f"[OK] /strategies hub has all 6 entry points")
            
            # Step 6: Verify /strategy-validations page
            print("\n[STEP 6] Verifying /strategy-validations page...")
            
            page.goto("http://localhost:3000/strategy-validations", wait_until="networkidle")
            time.sleep(2)
            
            # Save validation page DOM
            validation_dom = page.content()
            validation_dom_path = evidence_dir / "p3-9-validation-dom.md"
            with open(validation_dom_path, "w", encoding="utf-8") as f:
                f.write(f"# /strategy-validations DOM - {run_id}\n\n")
                f.write(validation_dom)
            
            # Verify page content
            if "当前没有策略验证案例" not in page.content():
                print("[FAIL] Page missing empty state message")
                return 1
            
            if "验证案例数量" not in page.content():
                print("[FAIL] Page missing validation count display")
                return 1
            
            # Verify back link to /strategies
            if 'href="/strategies"' not in page.content():
                print("[FAIL] Page missing link back to /strategies")
                return 1
            
            print("[OK] /strategy-validations page displays empty state correctly")
            
            # Save network log
            network_log_path = evidence_dir / "p3-9-network-log.json"
            with open(network_log_path, "w", encoding="utf-8") as f:
                json.dump(network_log, f, indent=2, ensure_ascii=False)
            
            # Verify all API requests go to localhost:8010
            api_requests = [entry for entry in network_log if "/api/" in entry["url"]]
            non_local_requests = [
                entry for entry in api_requests 
                if not entry["url"].startswith("http://localhost:8010")
            ]
            
            if non_local_requests:
                print(f"[FAIL] Found {len(non_local_requests)} non-localhost API requests")
                for entry in non_local_requests:
                    print(f"  {entry['url']}")
                return 1
            
            print(f"[OK] All {len(api_requests)} API requests go to localhost:8010")
            
            browser.close()
        
        # Step 7: Generate evidence summary
        print("\n[STEP 7] Generating evidence summary...")
        
        evidence_summary = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "verification_status": "PASSED",
            "api_response": api_data,
            "hub_entry_count": 6,
            "evidence_files": [
                str(api_response_path.name),
                str(hub_dom_path.name),
                str(validation_dom_path.name),
                str(network_log_path.name),
                str(frontend_log_path.name),
            ],
            "checks": {
                "api_validations_empty": validations == [],
                "api_count_zero": count == 0,
                "hub_has_6_entries": True,
                "validation_page_empty_state": True,
                "validation_page_count_display": True,
                "back_link_to_strategies": True,
                "api_requests_localhost": len(api_requests),
            }
        }
        
        summary_path = evidence_dir / "p3-9-verification-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(evidence_summary, f, indent=2, ensure_ascii=False)
        
        print(f"[OK] Evidence summary saved: {summary_path.name}")
        
        print("\n" + "=" * 80)
        print("PASS: P3-9 VERIFICATION PASSED")
        print("=" * 80)
        print(f"\nRun ID: {run_id}")
        print(f"API validations count: {count}")
        print(f"Hub entry points: 6")
        print(f"Evidence files: {len(evidence_summary['evidence_files'])}")
        
        return 0
        
    except Exception as e:
        print(f"\n[FAIL] Verification error: {e}")
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        # Cleanup
        print("\n[CLEANUP] Stopping processes...")
        if frontend_process:
            frontend_process.terminate()
            try:
                frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                frontend_process.kill()
        
        if backend_process:
            backend_process.terminate()
            try:
                backend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                backend_process.kill()
        
        print("[OK] Cleanup complete")


if __name__ == "__main__":
    exit_code = run_verification()
    sys.exit(exit_code)
