"""
P0-RUNTIME-1B Runtime Smoke Test

从干净终端一条命令完成：
1. 后端启动 + health 检查
2. 前端启动
3. Playwright 浏览器访问 /observations
4. 捕获 console、network、DOM
5. 保存诊断证据

不依赖人工，不截图，不手写，不 fixture。
"""

import sys
import os
import asyncio
import subprocess
import time
import json
from pathlib import Path

# 添加项目根到 sys.path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

print("=== P0-RUNTIME-1B Runtime Smoke Test ===\n")
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
print(f"cwd: {os.getcwd()}")
print(f"sys.path[0]: {sys.path[0]}\n")


# Step 1: 检查 imports
print("Step 1: Import checks")
try:
    import contracts
    print("[OK] contracts import")
except ImportError as e:
    print(f"[FAIL] contracts import: {e}")
    sys.exit(1)

try:
    import backend.app.main
    print("[OK] backend.app.main import")
except ImportError as e:
    print(f"[FAIL] backend.app.main import: {e}")
    sys.exit(1)

from backend.config.runtime_paths import get_live_trade_db_path, get_research_db_path

print(f"[OK] LIVE_TRADE_DB: {get_live_trade_db_path()}")
print(f"[OK] RESEARCH_DB: {get_research_db_path()}\n")


# Step 2: 启动后端
print("Step 2: Starting backend on port 8010")
os.environ["RESEARCH_CONVERSATION_MODE"] = "deterministic"
os.environ["SERENITY_EXECUTION_MODE"] = "stub"

backend_proc = subprocess.Popen(
    [
        str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"),
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8010",
    ],
    cwd=str(PROJECT_ROOT),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
)

print("[OK] Backend process started")

# Step 3: 等待 health endpoint
print("Step 3: Waiting for /api/health/runtime")
import requests

health_url = "http://localhost:8010/api/health/runtime"
max_wait = 30
for i in range(max_wait):
    try:
        response = requests.get(health_url, timeout=2)
        if response.status_code == 200:
            health_data = response.json()
            print(f"[OK] Health check passed: {health_data['status']}")
            
            # 保存 health JSON
            with open(PROJECT_ROOT / "docs" / "verification" / "runtime-health.json", "w") as f:
                json.dump(health_data, f, indent=2)
            print("[OK] Saved: runtime-health.json")
            break
    except Exception as e:
        if i == max_wait - 1:
            print(f"[FAIL] Health check timeout: {e}")
            backend_proc.kill()
            sys.exit(1)
        time.sleep(1)

# Step 4: 检查端口占用
print("\nStep 4: Checking port availability")
import socket

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0

if is_port_in_use(3000):
    print("[FAIL] Port 3000 already in use (frontend_port_already_in_use)")
    print("Please stop existing Next.js dev server before running smoke test")
    backend_proc.kill()
    sys.exit(1)

print("[OK] Port 3000 available")

# Step 5: 启动前端
print("\nStep 5: Starting frontend on port 3000")
frontend_env = os.environ.copy()
frontend_env["NEXT_PUBLIC_API_BASE_URL"] = "http://localhost:8010"

# Windows: use full path to npm
npm_cmd = "C:/Program Files/nodejs/npm.cmd" if os.path.exists("C:/Program Files/nodejs/npm.cmd") else "npm"

frontend_proc = subprocess.Popen(
    [npm_cmd, "run", "dev", "--", "--port", "3000"],
    cwd=str(PROJECT_ROOT / "frontend"),
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env=frontend_env,
    shell=True,  # Windows 需要 shell
)

print("[OK] Frontend process started")
print("Waiting for frontend to be ready...")
time.sleep(15)  # 等待 Next.js 启动

# Step 5: Playwright 访问 /observations
print("\nStep 6: Opening /observations with Playwright")

async def capture_page():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[FAIL] Playwright not installed")
        return False
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 捕获 console
        console_logs = []
        page.on("console", lambda msg: console_logs.append({
            "type": msg.type,
            "text": msg.text
        }))
        
        # 捕获 network
        network_log = []
        page.on("response", lambda response: network_log.append({
            "url": response.url,
            "status": response.status,
            "ok": response.ok,
        }))
        
        try:
            # 访问页面
            await page.goto("http://localhost:3000/observations", wait_until="networkidle", timeout=30000)
            
            # 等待加载
            await page.wait_for_timeout(3000)
            
            # 读取 DOM
            title = await page.locator("h1").first.text_content() if await page.locator("h1").count() > 0 else "NO_TITLE"
            body_text = await page.locator("body").text_content()
            
            # 保存证据
            docs_dir = PROJECT_ROOT / "docs" / "verification"
            
            # DOM
            with open(docs_dir / "runtime-observations-dom.md", "w", encoding="utf-8") as f:
                f.write(f"# Runtime Observations DOM (真实浏览器)\n\n")
                f.write(f"**Title:** {title}\n\n")
                f.write(f"**Body Text (前500字符):**\n\n```\n{body_text[:500]}\n```\n")
            print("[OK] Saved: runtime-observations-dom.md")
            
            # Network log
            with open(docs_dir / "runtime-network-log.json", "w") as f:
                json.dump(network_log, f, indent=2)
            print("[OK] Saved: runtime-network-log.json")
            
            # Startup log
            with open(docs_dir / "runtime-startup-log.txt", "w") as f:
                f.write("=== P0-RUNTIME-1B Startup Log ===\n\n")
                f.write(f"Backend: http://localhost:8010\n")
                f.write(f"Frontend: http://localhost:3000\n")
                f.write(f"Health: {health_data['status']}\n")
                f.write(f"Console logs: {len(console_logs)}\n")
                f.write(f"Network requests: {len(network_log)}\n\n")
                f.write(f"Environment:\n")
                f.write(f"  NEXT_PUBLIC_API_BASE_URL: {os.environ.get('NEXT_PUBLIC_API_BASE_URL', 'NOT_SET')}\n")
            print("[OK] Saved: runtime-startup-log.txt")
            
            # === 严格判定逻辑 ===
            failed = False
            fail_reasons = []
            
            # 1. 检查 /api/observations 请求
            obs_requests = [r for r in network_log if "/api/observations" in r["url"]]
            if not obs_requests:
                failed = True
                fail_reasons.append("No /api/observations requests found in network log")
                print("[FAIL] No /api/observations requests found")
            else:
                print(f"[OK] Found {len(obs_requests)} /api/observations requests")
                
                for req in obs_requests:
                    print(f"  - {req['url']}: HTTP {req['status']}")
                    
                    # 检查是否使用 8010 端口
                    if not req['url'].startswith("http://localhost:8010"):
                        failed = True
                        fail_reasons.append(f"Request to wrong port: {req['url']} (expected http://localhost:8010)")
                        print(f"[FAIL] Wrong API base: {req['url']}")
                    
                    # 检查 HTTP 状态
                    if req['status'] != 200:
                        failed = True
                        fail_reasons.append(f"HTTP {req['status']} for {req['url']} (expected 200)")
                        print(f"[FAIL] HTTP {req['status']} (expected 200)")
            
            # 2. 检查页面内容
            bad_patterns = [
                "加载失败",
                "API request failed",
                "localhost:8000",
                "HTTP 404",
                "加载中",
            ]
            
            for pattern in bad_patterns:
                if pattern in body_text:
                    failed = True
                    fail_reasons.append(f"Page contains: {pattern}")
                    print(f"[FAIL] Page contains: {pattern}")
            
            # 保存失败原因
            if failed:
                with open(docs_dir / "runtime-startup-log.txt", "a") as f:
                    f.write(f"\n=== FAIL REASONS ===\n")
                    for reason in fail_reasons:
                        f.write(f"  - {reason}\n")
            
            await browser.close()
            
            if failed:
                print("\n[FAIL] Runtime smoke test failed (see reasons above)")
                return False
            else:
                print("\n[PASS] Runtime smoke test completed")
                print("[PASS] /api/observations uses canonical API base http://localhost:8010")
                print("[PASS] /api/observations returned HTTP 200")
                return True
            
        except Exception as e:
            print(f"[FAIL] Page load error: {e}")
            await browser.close()
            return False

success = asyncio.run(capture_page())

# Cleanup
print("\nCleaning up processes...")
backend_proc.kill()
frontend_proc.kill()

if success:
    print("\n[PASS] Runtime smoke test completed")
    sys.exit(0)
else:
    print("\n[FAIL] Runtime smoke test failed")
    sys.exit(1)
