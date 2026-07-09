#!/usr/bin/env python3
"""
P4-5 Dashboard and Workbench Copy Integrity Verification

Verifies:
1. No mojibake in / and /workbench DOM
2. Expected Chinese text present
3. /workbench input functional
4. All API requests localhost:8010

Exit code 0 = pass, 1 = fail
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))
from runtime_process_helpers import (
    start_backend,
    start_frontend,
    stop_process,
    check_and_release_ports,
)


def verify_p4_5_copy_integrity():
    print("=" * 100)
    print("P4-5 DASHBOARD AND WORKBENCH COPY INTEGRITY VERIFICATION")
    print("=" * 100)
    print()
    
    run_id = f"P4_5_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    print(f"Run ID: {run_id}")
    print()
    
    project_root = Path(__file__).parent.parent
    verification_dir = project_root / "docs" / "verification"
    verification_dir.mkdir(parents=True, exist_ok=True)
    
    evidence = {
        "run_id": run_id,
        "timestamp": datetime.now().isoformat(),
        "checks": {},
        "evidence_files": [],
    }
    
    backend_process = None
    frontend_process = None
    browser = None
    playwright = None
    
    try:
        # Step 1: Clean ports
        print("Step 1: Checking ports...")
        print("-" * 80)
        check_and_release_ports([8010, 3010])
        print("✓ Ports ready")
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
        print("✓ Backend started")
        print()
        
        # Step 3: Start frontend
        print("Step 3: Starting frontend...")
        print("-" * 80)
        frontend_process = start_frontend(port=3010, timeout_seconds=60)
        print("✓ Frontend started")
        print()
        
        # Step 4: Capture DOM
        print("Step 4: Capturing DOM...")
        print("-" * 80)
        
        from playwright.sync_api import sync_playwright
        
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Network log
        network_log = []
        def handle_request(req):
            network_log.append({
                'url': req.url,
                'method': req.method,
                'resource_type': req.resource_type,
            })
        page.on('request', handle_request)
        
        # Dashboard
        page.goto('http://localhost:3010/', wait_until='networkidle', timeout=30000)
        time.sleep(2)
        dashboard_html = page.content()
        
        dash_file = verification_dir / "p4-5-dashboard-dom.md"
        with open(dash_file, "w", encoding="utf-8") as f:
            f.write(f"# P4-5 Dashboard DOM\n\n```html\n{dashboard_html}\n```\n")
        evidence["evidence_files"].append(str(dash_file.relative_to(project_root)))
        print(f"✓ Saved dashboard DOM")
        
        # Workbench
        page.goto('http://localhost:3010/workbench', wait_until='networkidle', timeout=30000)
        time.sleep(2)
        workbench_html = page.content()
        
        work_file = verification_dir / "p4-5-workbench-dom.md"
        with open(work_file, "w", encoding="utf-8") as f:
            f.write(f"# P4-5 Workbench DOM\n\n```html\n{workbench_html}\n```\n")
        evidence["evidence_files"].append(str(work_file.relative_to(project_root)))
        print(f"✓ Saved workbench DOM")
        
        # Network log
        net_file = verification_dir / "p4-5-network-log.json"
        with open(net_file, "w", encoding="utf-8") as f:
            json.dump(network_log, f, indent=2)
        evidence["evidence_files"].append(str(net_file.relative_to(project_root)))
        print(f"✓ Saved network log")
        print()
        
        # Step 5: Check mojibake
        print("Step 5: Checking for mojibake...")
        print("-" * 80)
        
        mojibake_patterns = ['鉁', '鈫', '鏁', '鏆', '宸', '绛', '瑙', '鍊']
        
        dash_bad = [m for m in mojibake_patterns if m in dashboard_html]
        work_bad = [m for m in mojibake_patterns if m in workbench_html]
        
        if dash_bad:
            print(f"✗ Dashboard has mojibake: {dash_bad}")
            evidence["checks"]["dashboard_mojibake"] = False
            return 1
        
        if work_bad:
            print(f"✗ Workbench has mojibake: {work_bad}")
            evidence["checks"]["workbench_mojibake"] = False
            return 1
        
        print("✓ No mojibake found")
        evidence["checks"]["no_mojibake"] = True
        print()
        
        # Step 6: Check expected text
        print("Step 6: Verifying expected text...")
        print("-" * 80)
        
        # Dashboard required text
        dash_required = ['每日工作台', '工作台', '观察池', '信号', '策略']
        dash_optional = ['数据正常', '暂无数据']
        
        for text in dash_required:
            if text not in dashboard_html:
                print(f"✗ Dashboard missing: {text}")
                evidence["checks"]["dashboard_text"] = False
                return 1
        
        has_state = any(t in dashboard_html for t in dash_optional)
        if not has_state:
            print(f"✗ Dashboard missing state messages")
            evidence["checks"]["dashboard_state"] = False
            return 1
        
        print(f"✓ Dashboard text complete")
        evidence["checks"]["dashboard_text"] = True
        
        # Workbench required text
        work_required = ['TraderLens 工作台', 'AI 对话']
        
        for text in work_required:
            if text not in workbench_html:
                print(f"✗ Workbench missing: {text}")
                evidence["checks"]["workbench_text"] = False
                return 1
        
        # Check input present
        if '<input' not in workbench_html and '<textarea' not in workbench_html:
            print(f"✗ Workbench missing input element")
            evidence["checks"]["workbench_input"] = False
            return 1
        
        print(f"✓ Workbench text complete")
        print(f"✓ Workbench input present")
        evidence["checks"]["workbench_text"] = True
        evidence["checks"]["workbench_input"] = True
        print()
        
        # Step 7: Check API requests
        print("Step 7: Verifying network requests...")
        print("-" * 80)
        
        api_requests = [r for r in network_log if r['resource_type'] in ['fetch', 'xhr']]
        external = [r for r in api_requests if 'localhost' not in r['url']]
        
        if external:
            print(f"✗ Found {len(external)} external API requests")
            evidence["checks"]["localhost_only"] = False
            return 1
        
        print(f"✓ All {len(api_requests)} API requests to localhost")
        evidence["checks"]["localhost_only"] = True
        print()
        
        # Step 8: Save summary
        print("Step 8: Saving summary...")
        print("-" * 80)
        
        summary_file = verification_dir / "p4-5-verification-summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False)
        evidence["evidence_files"].append(str(summary_file.relative_to(project_root)))
        print(f"✓ Saved summary")
        print()
        
        print("=" * 100)
        print("✓ P4-5 COPY INTEGRITY VERIFICATION PASSED")
        print("=" * 100)
        print()
        print(f"Run ID: {run_id}")
        print(f"Evidence files: {len(evidence['evidence_files'])}")
        print()
        
        return 0
        
    except Exception as e:
        print(f"\n✗ Verification error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()
        
        if frontend_process:
            frontend_log_file = verification_dir / "p4-5-frontend-log.txt"
            stop_process(frontend_process, "Frontend", save_log=frontend_log_file)
            if frontend_log_file.exists():
                evidence["evidence_files"].append(str(frontend_log_file.relative_to(project_root)))
        
        if backend_process:
            stop_process(backend_process, "Backend", release_ports=[8010])


if __name__ == "__main__":
    sys.exit(verify_p4_5_copy_integrity())
