#!/usr/bin/env python3
"""P7-4 V1 Boundary and UI Smoke Acceptance"""

import json
import re
import sys
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

RUN_ID = f"P7_4_RUN_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
DOCS = Path(__file__).parent.parent / "docs" / "verification"
DOCS.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("/", "dashboard"),
    ("/workbench", "workbench"),
    ("/observations", "observations"),
    ("/signals", "signals"),
    ("/strategies", "strategies"),
    ("/strategy-ideas", "strategy-ideas"),
    ("/candidate-strategies", "candidate"),
    ("/rejected-strategies", "rejected"),
    ("/strategy-validations", "validations"),
    ("/strategy-templates", "templates"),
]

BANNED = [
    "自动交易", "自动下单", "保证收益", "稳赚", "无风险",
    "fake", "mock", "placeholder", "TODO", "coming soon"
]


def main():
    print("=" * 60)
    print(f"P7-4: V1 BOUNDARY AND UI SMOKE\nRun ID: {RUN_ID}")
    print("=" * 60)

    check_and_release_ports([8010, 3010])
    backend = start_backend(port=8010, project_root=Path(__file__).parent.parent)
    frontend = start_frontend(port=3010, project_root=Path(__file__).parent.parent)

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context()
    page = ctx.new_page()

    net_log = []
    page.on("request", lambda r: net_log.append({"url": r.url, "method": r.method}))

    boundary_fails = []
    pages_ok = 0

    try:
        # UI smoke
        for path, name in PAGES:
            page.goto(f"http://localhost:3010{path}", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            dom = page.content()
            (DOCS / f"p7-4-{name}-dom.md").write_text(f"# {name.title()}\n\n{dom}", encoding="utf-8")

            # Check 404
            if "404" in page.title().lower() or "not found" in dom.lower()[:500]:
                boundary_fails.append(f"{name}: 404")
                continue

            # Check banned phrases (skip HTML attributes like placeholder="...")
            dom_text = re.sub(r'<[^>]+>', ' ', dom)  # ponytail: strip tags, check text only
            for b in BANNED:
                if re.search(rf"\b{re.escape(b)}\b", dom_text, re.IGNORECASE):
                    boundary_fails.append(f"{name}: banned phrase '{b}'")

            pages_ok += 1
            print(f"[{pages_ok}/{len(PAGES)}] {name} OK")

        # API checks
        strat_resp = requests.get("http://localhost:8010/api/strategies?status=approved", timeout=10)
        approved = strat_resp.json().get("strategies", [])
        approved_count = len(approved)

        cand_resp = requests.get("http://localhost:8010/api/strategies?status=candidate_unapproved", timeout=10)
        candidate_count = len(cand_resp.json().get("strategies", []))

        rej_resp = requests.get("http://localhost:8010/api/strategy-ideas", timeout=10)
        ideas = rej_resp.json().get("ideas", [])
        rejected_count = len([i for i in ideas if i.get("decision") == "rejected"])

        val_resp = requests.get("http://localhost:8010/api/strategy-validations", timeout=10)
        validations_count = len(val_resp.json().get("validations", []))

        # Boundary: approved must be 0
        if approved_count != 0:
            boundary_fails.append(f"approved_count={approved_count}, expected 0")

        print(f"\nAPI: approved={approved_count}, candidate={candidate_count}, rejected={rejected_count}, validations={validations_count}")

        # Network
        external = [r for r in net_log if "localhost" not in r["url"]]
        if external:
            boundary_fails.append(f"external requests={len(external)}")

        (DOCS / "p7-4-network-log.json").write_text(json.dumps(net_log, indent=2), encoding="utf-8")

        summary = {
            "run_id": RUN_ID,
            "pages_checked": pages_ok,
            "boundary_checks_passed": len(boundary_fails) == 0,
            "boundary_failures": boundary_fails,
            "approved_strategies_count": approved_count,
            "candidate_count": candidate_count,
            "rejected_count": rejected_count,
            "validations_count": validations_count,
            "network_external_count": len(external),
        }
        (DOCS / "p7-4-verification-summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

        if boundary_fails:
            print(f"\nFAIL: {len(boundary_fails)} boundary check(s) failed:")
            for f in boundary_fails:
                print(f"  - {f}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("P7-4 VERIFICATION: PASS")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        browser.close()
        pw.stop()
        stop_process(frontend, "Frontend", DOCS / "p7-4-frontend-log.txt")
        stop_process(backend, "Backend", DOCS / "p7-4-backend-log.txt")


if __name__ == "__main__":
    main()
