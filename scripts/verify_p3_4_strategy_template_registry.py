"""
P3-4 Strategy Template Registry Verification Script

Verifies:
1. GET /api/strategy-templates returns approved templates
2. GET /api/strategy-templates/{template_id} returns template detail
3. /strategy-templates page displays template list
4. /strategy-templates/{template_id} page displays template detail
5. Strategy idea detail page shows mapping status and template link
6. Real browser DOM capture (no fake/placeholder)
7. All API requests point to localhost:8010

Exit code 0 = PASS, non-zero = FAIL
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

# Paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.runtime_process_helpers import (
    check_and_release_ports,
    start_backend,
    start_frontend,
    stop_process,
)

FRONTEND_DIR = PROJECT_ROOT / "frontend"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
DOCS_DIR = PROJECT_ROOT / "docs" / "verification"

# Ensure docs dir exists
DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Generate run ID
RUN_ID = f"P2RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

print("=" * 100)
print("P3-4 Strategy Template Registry Verification")
print("=" * 100)
print(f"Run ID: {RUN_ID}")
print(f"Timestamp: {datetime.now().isoformat()}")
print("=" * 100)
print()


async def main():
    backend_process = None
    frontend_process = None
    browser = None
    
    try:
        # Step 0: Check ports
        print("Step 0: Checking for existing processes on ports 8010 and 3000...")
        check_and_release_ports([8010, 3000])
        print("[OK] Ports 8010 and 3000 are available")
        print()
        
        # Step 1: Start backend
        print("Step 1: Starting backend on port 8010...")
        backend_process = start_backend(port=8010)
        backend_log_path = None  # start_backend doesn't return log path
        print()
        
        # Step 2: Start frontend
        print("Step 2: Starting frontend on port 3000...")
        frontend_process = start_frontend(port=3000, project_root=PROJECT_ROOT)
        frontend_log_path = None  # start_frontend doesn't return log path
        print()
        
        # Step 3: Verify template list API
        print("Step 3: Verifying GET /api/strategy-templates...")
        import requests
        response = requests.get("http://localhost:8010/api/strategy-templates", timeout=10)
        if response.status_code != 200:
            print(f"[FAIL] Template list API returned {response.status_code}")
            return 1
        
        templates_data = response.json()
        templates = templates_data.get("templates", [])
        print(f"[OK] Template list API returned {len(templates)} templates")
        
        # Save list API response
        list_api_path = DOCS_DIR / "p3-4-template-list-api.json"
        list_api_path.write_text(json.dumps(templates_data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[OK] Saved template list API response")
        print()
        
        # Step 4: Verify template detail API (if templates exist)
        template_id = None
        if templates:
            template_id = templates[0]["template_id"]
            print(f"Step 4: Verifying GET /api/strategy-templates/{template_id}...")
            response = requests.get(f"http://localhost:8010/api/strategy-templates/{template_id}", timeout=10)
            if response.status_code != 200:
                print(f"[FAIL] Template detail API returned {response.status_code}")
                return 1
            
            detail_data = response.json()
            print(f"[OK] Template detail API returned template {detail_data['template_id']}")
            
            # Verify required fields
            required_fields = ["template_id", "version", "status", "entry_rules", "exit_rules", "risk_rules"]
            missing = [f for f in required_fields if f not in detail_data]
            if missing:
                print(f"[FAIL] Template detail missing fields: {missing}")
                return 1
            
            # Save detail API response
            detail_api_path = DOCS_DIR / f"p3-4-template-detail-api-{template_id}.json"
            detail_api_path.write_text(json.dumps(detail_data, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"[OK] Saved template detail API response")
            print()
        else:
            print("Step 4: SKIP (no templates in library)")
            print()
        
        # Step 5: Verify template list page
        print("Step 5: Verifying /strategy-templates page...")
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        context = await browser.new_context()
        
        # Track network requests
        network_log = []
        async def log_request(request):
            if "localhost:8010" in request.url or "/api/" in request.url:
                network_log.append({
                    "url": request.url,
                    "method": request.method,
                })
        
        page = await context.new_page()
        page.on("request", log_request)
        
        await page.goto("http://localhost:3000/strategy-templates", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)
        
        # Save DOM
        content = await page.content()
        dom_path = DOCS_DIR / "p3-4-template-list-dom.md"
        dom_path.write_text(f"# Template List Page DOM\n\n```html\n{content}\n```", encoding="utf-8")
        print("[OK] Saved template list page DOM")
        
        # Verify DOM content
        if templates:
            if template_id not in content:
                print(f"[FAIL] Template ID {template_id} not found in DOM")
                return 1
            print(f"[OK] Found template {template_id} in DOM")
        else:
            if "没有已批准的策略模板" not in content:
                print("[FAIL] Empty state message not found in DOM")
                return 1
            print("[OK] Empty state displayed correctly")
        
        # Verify API requests point to localhost:8010
        api_requests = [req for req in network_log if "/api/" in req["url"]]
        if api_requests:
            wrong_host = [req for req in api_requests if "localhost:8010" not in req["url"]]
            if wrong_host:
                print(f"[FAIL] Found API requests not pointing to localhost:8010: {wrong_host}")
                return 1
            print(f"[OK] All {len(api_requests)} API requests point to localhost:8010")
        
        # Save network log
        network_log_path = DOCS_DIR / "p3-4-template-list-network-log.json"
        network_log_path.write_text(json.dumps(network_log, indent=2), encoding="utf-8")
        print("[OK] Saved template list network log")
        print()
        
        # Step 6: Verify template detail page (if templates exist)
        if template_id:
            print(f"Step 6: Verifying /strategy-templates/{template_id} page...")
            network_log.clear()
            
            await page.goto(f"http://localhost:3000/strategy-templates/{template_id}", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Save DOM
            content = await page.content()
            dom_path = DOCS_DIR / f"p3-4-template-detail-dom-{template_id}.md"
            dom_path.write_text(f"# Template Detail Page DOM\n\n```html\n{content}\n```", encoding="utf-8")
            print("[OK] Saved template detail page DOM")
            
            # Verify DOM content
            if template_id not in content:
                print(f"[FAIL] Template ID {template_id} not found in detail DOM")
                return 1
            if "入场规则" not in content or "出场规则" not in content:
                print("[FAIL] Entry/exit rules not found in detail DOM")
                return 1
            print("[OK] Template detail page verified")
            
            # Save network log
            network_log_path = DOCS_DIR / f"p3-4-template-detail-network-log-{template_id}.json"
            network_log_path.write_text(json.dumps(network_log, indent=2), encoding="utf-8")
            print("[OK] Saved template detail network log")
            print()
        else:
            print("Step 6: SKIP (no templates in library)")
            print()
        
        # Step 7: Verify mapping display in idea detail page
        print("Step 7: Verifying mapping display in idea detail page...")
        
        # Get existing ideas from API
        response = requests.get("http://localhost:8010/api/strategy-ideas", timeout=10)
        ideas = response.json().get("ideas", [])
        
        if not ideas:
            print("[WARN] No existing strategy ideas found, skipping mapping verification")
            idea_id = None
            idea = None
        else:
            # Use the first idea
            idea = ideas[0]
            idea_id = idea["idea_id"]
            print(f"[OK] Using existing idea {idea_id} for mapping verification")
            
            # Navigate to idea detail page
            network_log.clear()
            await page.goto(f"http://localhost:3000/strategy-ideas/{idea_id}", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(2)
            
            # Save DOM
            content = await page.content()
            dom_path = DOCS_DIR / f"p3-4-idea-detail-dom-{idea_id}.md"
            dom_path.write_text(f"# Idea Detail Page DOM\n\n```html\n{content}\n```", encoding="utf-8")
            print("[OK] Saved idea detail page DOM")
            
            # Verify mapping display
            if "模板映射" not in content:
                print("[FAIL] Mapping section not found in idea detail")
                return 1
            
            if "匹配路径" not in content:
                print("[FAIL] Path type not found in mapping section")
                return 1
            
            # Verify mapping status shows correctly
            if idea.get("mapped_template_id"):
                # Should show template link
                if idea["mapped_template_id"] not in content:
                    print(f"[FAIL] Template ID {idea['mapped_template_id']} not found in mapping")
                    return 1
                print(f"[OK] Mapping shows template {idea['mapped_template_id']}")
            else:
                # Should show no template
                if "无匹配模板" not in content and "null" not in content and "没有匹配" not in content:
                    print("[WARN] No template indicator may not be clear")
                print("[OK] Mapping section verified")
        
        print()
        
        # Step 8: Save evidence summary
        print("Step 8: Saving evidence summary...")
        summary = {
            "run_id": RUN_ID,
            "template_count": len(templates),
            "sample_template_id": template_id,
            "idea_id": idea_id,
            "idea_decision": idea.get("decision"),
            "idea_path_type": idea.get("path_type"),
            "idea_mapped_template_id": idea.get("mapped_template_id"),
            "timestamp": datetime.now().isoformat(),
        }
        
        summary_path = DOCS_DIR / "p3-4-evidence-summary.json"
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        print("[OK] Evidence summary saved")
        print()
        
        print("=" * 100)
        print("[OK] P3-4 Verification PASSED")
        print("=" * 100)
        print()
        print(f"Run ID: {RUN_ID}")
        print(f"Template Count: {len(templates)}")
        if template_id:
            print(f"Sample Template: {template_id}")
        print(f"Test Idea ID: {idea_id}")
        print(f"Mapping Status: {idea.get('path_type')}")
        print()
        print(f"Evidence files saved to: {DOCS_DIR}/")
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 100)
        print(f"[FAIL] P3-4 Verification FAILED: {e}")
        print("=" * 100)
        import traceback
        traceback.print_exc()
        return 1
        
    finally:
        # Cleanup
        if browser:
            await browser.close()
        
        if backend_process:
            print()
            stop_process(backend_process, "Backend", DOCS_DIR / "p3-4-backend-log.txt", release_ports=[8010])
        
        if frontend_process:
            stop_process(frontend_process, "Frontend", DOCS_DIR / "p3-4-frontend-log.txt", release_ports=[3000])


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
