"""
P7-1: V1 Dashboard-Led Product Acceptance.

Verifies the product from the dashboard through both accepted V1 journeys:
- friend stock to observation
- strategy idea to rejection/candidate registries
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.runtime_process_helpers import (  # noqa: E402
    get_port_owner_pid,
    start_backend,
    start_frontend,
    stop_process,
)


BACKEND_PORT = 8010
FRONTEND_PORT = 3010
BACKEND = f"http://localhost:{BACKEND_PORT}"
FRONTEND = f"http://localhost:{FRONTEND_PORT}"
RUN_ID = datetime.now().strftime("P7_1_RUN_%Y%m%d_%H%M%S")
DOCS_DIR = project_root / "docs" / "verification"
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    sys.exit(1)


def check_ports_without_kill() -> None:
    occupied = []
    for port in [BACKEND_PORT, FRONTEND_PORT]:
        pid = get_port_owner_pid(port)
        if pid:
            occupied.append((port, pid))
    if occupied:
        for port, pid in occupied:
            print(f"Port {port} is occupied by PID {pid}. Stop and report; not killing.")
        sys.exit(1)


def post_workbench(page, message: str) -> dict[str, Any]:
    input_selector = "input[placeholder='输入消息...']"
    button_selector = "button[type='submit']"
    page.wait_for_selector(input_selector, state="visible", timeout=10000)
    input_box = page.locator(input_selector).first
    input_box.click()
    input_box.press("Control+A")
    input_box.press("Backspace")
    input_box.type(message, delay=5)
    page.wait_for_function(
        """() => {
            const button = document.querySelector("button[type='submit']");
            return button && !button.disabled;
        }""",
        timeout=10000,
    )
    with page.expect_response(
        lambda r: "/api/agent/workbench/message" in r.url and r.request.method == "POST",
        timeout=30000,
    ) as response_info:
        page.locator(button_selector).first.click()
    response = response_info.value
    if response.status != 200:
        fail(f"Workbench POST returned HTTP {response.status}")
    return response.json()


def read_route_decision(conversation_id: str) -> dict[str, Any]:
    db_path = project_root / "data" / "research.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            """
            SELECT content
            FROM agent_artifact_refs
            WHERE session_id = ? AND artifact_type = 'workflow_route_decision'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        fail(f"Missing workflow_route_decision for {conversation_id}")
    return json.loads(row["content"])


def poll_observation_position() -> dict[str, Any]:
    for _ in range(12):
        time.sleep(5)
        response = requests.get(f"{BACKEND}/api/observations?status=open", timeout=10)
        if response.status_code != 200:
            continue
        payload = response.json()
        positions = payload.get("positions", payload if isinstance(payload, list) else [])
        for position in positions:
            if isinstance(position, dict) and RUN_ID in position.get("entry_thesis", ""):
                return position
    fail(f"No observation position found for {RUN_ID} after 60s")


def poll_strategy_idea() -> dict[str, Any]:
    for _ in range(12):
        time.sleep(5)
        response = requests.get(f"{BACKEND}/api/strategy-ideas", timeout=10)
        if response.status_code != 200:
            continue
        ideas = response.json().get("ideas", [])
        for idea in ideas:
            if RUN_ID in idea.get("original_message", ""):
                return idea
    fail(f"No strategy idea found for {RUN_ID} after 60s")


def write_dom(name: str, html: str, title: str) -> None:
    (DOCS_DIR / name).write_text(f"# {title}\n\n```html\n{html}\n```\n", encoding="utf-8")


def assert_no_mojibake(text: str, label: str) -> None:
    patterns = ["鉁", "鈫", "鏁", "鏆", "宸", "绛", "瑙", "鍊"]
    found = [pattern for pattern in patterns if pattern in text]
    if found:
        fail(f"{label} contains mojibake patterns: {found}")


def main() -> None:
    print("=" * 80)
    print("P7-1 V1 DASHBOARD-LED PRODUCT ACCEPTANCE")
    print(f"Run ID: {RUN_ID}")
    print("=" * 80)

    check_ports_without_kill()

    backend_proc = None
    frontend_proc = None
    pw = None
    browser = None

    api_evidence: dict[str, Any] = {"run_id": RUN_ID}
    network_log: list[dict[str, str]] = []

    try:
        backend_proc = start_backend(
            port=BACKEND_PORT,
            project_root=project_root,
            extra_env={
                "RESEARCH_CONVERSATION_MODE": "deterministic",
                "SERENITY_EXECUTION_MODE": "stub",
            },
        )
        frontend_proc = start_frontend(port=FRONTEND_PORT, project_root=project_root)

        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()

        page.on(
            "request",
            lambda req: network_log.append(
                {"url": req.url, "method": req.method, "resource_type": req.resource_type}
            ),
        )

        print("[1/7] Dashboard")
        page.goto(f"{FRONTEND}/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        dashboard_dom = page.content()
        dashboard_text = page.inner_text("body")
        write_dom("p7-1-dashboard-dom.md", dashboard_dom, "P7-1 Dashboard DOM")
        assert_no_mojibake(dashboard_text, "dashboard DOM")
        for text in ["每日工作台", "持仓观察", "策略工作区", "风险守卫状态"]:
            if text not in dashboard_text:
                fail(f"Dashboard missing text: {text}")

        dashboard_api = requests.get(f"{BACKEND}/api/dashboard/today", timeout=10).json()
        risk_guard = dashboard_api.get("risk_guard", {})
        if risk_guard.get("data_state") == "ok":
            fail("risk_guard.data_state must not be ok")
        if risk_guard.get("blocks_count") != 0 or risk_guard.get("downgrades_count") != 0:
            fail("risk_guard counts must be zero")
        api_evidence["dashboard"] = dashboard_api

        print("[2/7] Flow A: friend stock to observation")
        page.goto(f"{FRONTEND}/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("h1:has-text('TraderLens 工作台')", timeout=10000)
        friend_first = f"帮我看看贵州茅台（600519），备注 {RUN_ID}"
        friend_response_1 = post_workbench(page, friend_first)
        page.wait_for_timeout(5000)
        friend_response_2 = post_workbench(page, "加入观察")
        page.wait_for_timeout(5000)
        friend_dom = page.content()
        write_dom("p7-1-workbench-friend-dom.md", friend_dom, "P7-1 Workbench Friend DOM")
        assert_no_mojibake(page.inner_text("body"), "workbench friend DOM")

        friend_conversation_id = (
            friend_response_2.get("conversation_id") or friend_response_1.get("conversation_id")
        )
        if not friend_conversation_id:
            fail("Missing friend flow conversation_id from Workbench response")

        position = poll_observation_position()
        position_id = position.get("position_id")
        if not position_id:
            fail("Observation position has no position_id")

        page.goto(f"{FRONTEND}/observations", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)
        observations_dom = page.content()
        if RUN_ID not in observations_dom and position_id not in observations_dom:
            fail("Observation DOM missing run_id and position_id")
        write_dom("p7-1-observations-dom.md", observations_dom, "P7-1 Observations DOM")

        api_evidence["friend_stock"] = {
            "first_response": friend_response_1,
            "second_response": friend_response_2,
            "conversation_id": friend_conversation_id,
            "position": position,
        }

        print("[3/7] Flow B: strategy idea")
        page.goto(f"{FRONTEND}/workbench", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector("input[placeholder='输入消息...']", state="visible", timeout=10000)
        strategy_message = f"[{RUN_ID}] 下午两点半买入，第二天早上卖出"
        strategy_response = post_workbench(page, strategy_message)
        page.wait_for_timeout(5000)
        strategy_dom = page.content()
        write_dom("p7-1-workbench-strategy-dom.md", strategy_dom, "P7-1 Workbench Strategy DOM")
        assert_no_mojibake(page.inner_text("body"), "workbench strategy DOM")

        strategy_conversation_id = strategy_response.get("conversation_id")
        response_workflow_type = strategy_response.get("workflow_type")
        if not strategy_conversation_id:
            fail("Missing strategy conversation_id from Workbench response")
        if response_workflow_type != "strategy_idea":
            fail(f"Expected response.workflow_type=strategy_idea, got {response_workflow_type}")

        route_decision = read_route_decision(strategy_conversation_id)
        route_workflow_kind = route_decision.get("workflow_kind")
        if route_workflow_kind != response_workflow_type:
            fail(
                f"route_decision.workflow_kind {route_workflow_kind} "
                f"!= response.workflow_type {response_workflow_type}"
            )

        idea = poll_strategy_idea()
        idea_id = idea.get("idea_id")
        detail = requests.get(f"{BACKEND}/api/strategy-ideas/{idea_id}", timeout=10).json()
        candidate_api = requests.get(
            f"{BACKEND}/api/strategy-ideas?candidate_status=candidate_unapproved",
            timeout=10,
        ).json()
        strategies_api = requests.get(f"{BACKEND}/api/strategies", timeout=10).json()

        if detail.get("decision") != "rejected":
            fail(f"Expected rejected strategy decision, got {detail.get('decision')}")
        if detail.get("candidate_status") != "candidate_unapproved":
            fail(f"Expected candidate_unapproved, got {detail.get('candidate_status')}")
        if strategies_api.get("count") != 0:
            fail(f"Approved strategies count must be 0, got {strategies_api.get('count')}")

        api_evidence["strategy"] = {
            "workbench_response": strategy_response,
            "route_decision": route_decision,
            "idea": idea,
            "detail": detail,
            "candidate_api_contains_idea": any(
                item.get("idea_id") == idea_id for item in candidate_api.get("ideas", [])
            ),
            "strategies_api": strategies_api,
        }

        print("[4/7] Strategy pages")
        for file_name, path, required in [
            ("p7-1-strategy-ideas-dom.md", "/strategy-ideas", idea_id),
            ("p7-1-candidate-dom.md", "/candidate-strategies", idea_id),
            ("p7-1-rejected-dom.md", "/rejected-strategies", idea_id),
            ("p7-1-strategies-dom.md", "/strategies", "0"),
        ]:
            page.goto(f"{FRONTEND}{path}", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(1500)
            dom = page.content()
            if required not in dom:
                fail(f"{path} DOM missing required value {required}")
            write_dom(file_name, dom, f"P7-1 {path} DOM")

        print("[5/7] Network")
        external = [
            req
            for req in network_log
            if not (
                req["url"].startswith(f"{FRONTEND}")
                or req["url"].startswith(f"{BACKEND}")
            )
        ]
        if external:
            fail(f"External network requests found: {external[:3]}")

        api_requests = [
            req for req in network_log if "/api/" in req["url"] and not req["url"].startswith(BACKEND)
        ]
        if api_requests:
            fail(f"API requests not targeting backend: {api_requests[:3]}")

        (DOCS_DIR / "p7-1-network-log.json").write_text(
            json.dumps(network_log, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (DOCS_DIR / "p7-1-api-evidence.json").write_text(
            json.dumps(api_evidence, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("[6/7] Summary")
        summary = {
            "run_id": RUN_ID,
            "friend_conversation_id": friend_conversation_id,
            "position_id": position_id,
            "strategy_conversation_id": strategy_conversation_id,
            "idea_id": idea_id,
            "response_workflow_type": response_workflow_type,
            "route_decision_workflow_kind": route_workflow_kind,
            "strategy_decision": detail.get("decision"),
            "candidate_status": detail.get("candidate_status"),
            "approved_strategies_count": strategies_api.get("count"),
            "risk_guard": risk_guard,
            "network_requests_total": len(network_log),
            "network_requests_external": len(external),
            "evidence_files": [
                "p7-1-dashboard-dom.md",
                "p7-1-workbench-friend-dom.md",
                "p7-1-workbench-strategy-dom.md",
                "p7-1-observations-dom.md",
                "p7-1-strategy-ideas-dom.md",
                "p7-1-candidate-dom.md",
                "p7-1-rejected-dom.md",
                "p7-1-strategies-dom.md",
                "p7-1-network-log.json",
                "p7-1-api-evidence.json",
                "p7-1-verification-summary.json",
            ],
        }
        (DOCS_DIR / "p7-1-verification-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (DOCS_DIR / "p7-1-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        print("[7/7] PASS")
        print(json.dumps(summary, indent=2, ensure_ascii=False))

    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()
        if frontend_proc:
            stop_process(frontend_proc, "Frontend")
        if backend_proc:
            stop_process(backend_proc, "Backend")


if __name__ == "__main__":
    main()
