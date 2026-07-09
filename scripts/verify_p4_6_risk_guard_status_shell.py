#!/usr/bin/env python3
"""
P4-6 Risk Guard Status Shell Verification

Requirements:
1. Backend API /api/dashboard/today returns risk_guard section
2. risk_guard.data_state is NOT "ok"
3. risk_guard.blocks_count == 0, downgrades_count == 0
4. Frontend displays risk guard section with "仅状态展示" disclaimer
5. All API requests to localhost:8010
"""

import sys
import json
import time
import subprocess
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.runtime_process_helpers import (
    start_backend,
    start_frontend,
    wait_for_http,
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)


def stop_owned_process(process, name: str, log_path: Path) -> None:
    """Stop only the process tree started by this verification script."""
    if not process:
        return

    subprocess.run(
        ["taskkill", "/F", "/T", "/PID", str(process.pid)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    stdout = ""
    stderr = ""
    try:
        stdout, stderr = process.communicate(timeout=2)
    except Exception:
        pass

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"{name} PID: {process.pid}\n")
        if stdout:
            f.write(stdout)
        if stderr:
            f.write(stderr)

    print(f"OK: {name} stopped")


def verify_p4_6():
    """Run P4-6 verification."""
    run_id = f"P4_6_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"\n{'='*60}")
    print(f"P4-6 RISK GUARD STATUS SHELL VERIFICATION")
    print(f"Run ID: {run_id}")
    print(f"{'='*60}\n")

    verification_dir = project_root / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)

    backend_proc = None
    frontend_proc = None
    playwright_instance = None
    browser = None
    
    # Use standard ports after cleanup
    backend_port = 8010
    frontend_port = 3010

    try:
        # 1. Start backend
        print("\n[1/9] Starting backend...")
        backend_proc = start_backend(
            port=backend_port,
            project_root=project_root,
            extra_env={
                "RESEARCH_CONVERSATION_MODE": "deterministic",
                "SERENITY_EXECUTION_MODE": "stub",
            }
        )
        
        # ponytail: start_backend already validated, skip redundant check
        print(f"OK: Backend running on {backend_port}")

        # 2. Verify API structure
        print("\n[2/9] Verifying /api/dashboard/today structure...")
        import requests
        
        response = requests.get(f"http://localhost:{backend_port}/api/dashboard/today", timeout=10)
        if response.status_code != 200:
            print(f"ERROR: API returned {response.status_code}")
            return False
        
        data = response.json()
        
        # Save raw API response
        api_path = verification_dir / "p4-6-dashboard-api.json"
        with open(api_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        print(f"OK: API response saved to {api_path.name}")

        # 3. Verify risk_guard presence
        print("\n[3/9] Verifying risk_guard section...")
        if "risk_guard" not in data:
            print("ERROR: risk_guard section missing from API response")
            return False
        
        risk_guard = data["risk_guard"]
        print(f"OK: risk_guard present")

        # 4. Verify risk_guard fields
        print("\n[4/9] Verifying risk_guard data_state...")
        required_fields = ["data_state", "message", "blocks_count", "downgrades_count", "updated_at"]
        for field in required_fields:
            if field not in risk_guard:
                print(f"ERROR: risk_guard missing field: {field}")
                return False
        
        data_state = risk_guard["data_state"]
        if data_state == "ok":
            print(f"ERROR: risk_guard.data_state is 'ok' (must be unavailable/not_configured)")
            return False
        
        print(f"OK: data_state = '{data_state}' (not 'ok')")

        # 5. Verify counts are zero
        print("\n[5/9] Verifying blocks_count and downgrades_count...")
        if risk_guard["blocks_count"] != 0:
            print(f"ERROR: blocks_count = {risk_guard['blocks_count']} (must be 0)")
            return False
        
        if risk_guard["downgrades_count"] != 0:
            print(f"ERROR: downgrades_count = {risk_guard['downgrades_count']} (must be 0)")
            return False
        
        print(f"OK: blocks_count = 0, downgrades_count = 0")

        # 6. Start frontend
        print("\n[6/9] Starting frontend...")
        frontend_proc = start_frontend(port=frontend_port, project_root=project_root)
        
        # ponytail: start_frontend already validated, skip redundant check
        print(f"OK: Frontend running on {frontend_port}")

        # 7. Playwright verification
        print("\n[7/9] Opening dashboard in browser...")
        playwright_instance = sync_playwright().start()
        browser = playwright_instance.chromium.launch(headless=True)
        page = browser.new_page()

        network_log = []
        
        def log_request(request):
            network_log.append({
                "url": request.url,
                "method": request.method,
                "timestamp": datetime.now().isoformat(),
            })
        
        page.on("request", log_request)
        
        page.goto(f"http://localhost:{frontend_port}/", wait_until="load", timeout=30000)
        time.sleep(2)
        
        print("OK: Dashboard loaded")

        # 8. Verify DOM
        print("\n[8/9] Verifying risk guard section in DOM...")
        dom_content = page.content()
        
        dom_path = verification_dir / "p4-6-dashboard-dom.md"
        with open(dom_path, "w", encoding="utf-8") as f:
            f.write(f"# P4-6 Dashboard DOM Capture\n\n")
            f.write(f"**Run ID:** {run_id}\n")
            f.write(f"**Timestamp:** {datetime.now().isoformat()}\n\n")
            f.write("```html\n")
            f.write(dom_content)
            f.write("\n```\n")
        
        print(f"OK: DOM saved to {dom_path.name}")

        # Verify risk guard text
        required_texts = [
            "风险守卫状态",
            "仅状态展示",
            "阻断次数",
            "降级次数",
            "此区域仅显示风险守卫状态",
        ]
        
        missing_texts = []
        for text in required_texts:
            if text not in dom_content:
                missing_texts.append(text)
        
        if missing_texts:
            print(f"ERROR: Missing required texts in DOM: {missing_texts}")
            return False
        
        print("OK: All required risk guard texts present")

        # 9. Verify network log
        print("\n[9/9] Verifying network requests...")
        network_path = verification_dir / "p4-6-network-log.json"
        with open(network_path, "w", encoding="utf-8") as f:
            json.dump(network_log, f, indent=2)
        
        external_requests = [
            req for req in network_log
            if not (req["url"].startswith(f"http://localhost:{frontend_port}") or
                   req["url"].startswith(f"http://localhost:{backend_port}"))
        ]
        
        if external_requests:
            print(f"ERROR: Found {len(external_requests)} external requests")
            return False
        
        print(f"OK: All {len(network_log)} requests to localhost")

        # Generate summary
        summary = {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(),
            "checks": {
                "risk_guard_present": True,
                "data_state_not_ok": data_state != "ok",
                "blocks_count_zero": risk_guard["blocks_count"] == 0,
                "downgrades_count_zero": risk_guard["downgrades_count"] == 0,
                "dom_texts_present": len(missing_texts) == 0,
                "localhost_only": len(external_requests) == 0,
            },
            "risk_guard_payload": risk_guard,
            "evidence_files": [
                "docs\\\\verification\\\\p4-6-dashboard-api.json",
                "docs\\\\verification\\\\p4-6-dashboard-dom.md",
                "docs\\\\verification\\\\p4-6-network-log.json",
                "docs\\\\verification\\\\p4-6-verification-summary.json",
                "docs\\\\verification\\\\p4-6-backend-log.txt",
                "docs\\\\verification\\\\p4-6-frontend-log.txt",
            ],
        }
        
        summary_path = verification_dir / "p4-6-verification-summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\nOK: Summary saved to {summary_path.name}")

        # Check all passed
        all_passed = all(summary["checks"].values())
        
        if all_passed:
            print("\n" + "="*60)
            print("PASS P4-6 RISK GUARD STATUS SHELL VERIFICATION PASSED")
            print("="*60)
            return True
        else:
            print("\n" + "="*60)
            print("FAIL Some checks failed")
            print("="*60)
            return False

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        if browser:
            try:
                browser.close()
            except Exception as e:
                print(f"WARN: browser close failed: {e}")
        if playwright_instance:
            try:
                playwright_instance.stop()
            except Exception as e:
                print(f"WARN: playwright stop failed: {e}")
        if frontend_proc:
            stop_owned_process(
                frontend_proc,
                "frontend",
                verification_dir / "p4-6-frontend-log.txt",
            )
        if backend_proc:
            stop_owned_process(
                backend_proc,
                "backend",
                verification_dir / "p4-6-backend-log.txt",
            )


if __name__ == "__main__":
    success = verify_p4_6()
    sys.exit(0 if success else 1)
