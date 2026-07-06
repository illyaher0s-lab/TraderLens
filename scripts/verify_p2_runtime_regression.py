#!/usr/bin/env python3
"""
P2 Runtime Regression Gate

统一入口，顺序执行全部 P2 运行时验收脚本：
- P2-1A: Workbench → Observations (买入验证)
- P2-1B: Observations UX (展示验证)
- P2-1C: Daily Signal Generation (信号生成验证)
- P2-1D: Sell Close P&L Review (完整买入卖出链路)

任一子脚本失败，整体失败。

PASS 标准：
- 全部 4 个子脚本 exit code 0
- 所有 API 请求使用 localhost:8010
- Backend log 无 500/Traceback/sqlite/ERROR
- 不允许 fixture/直接 DB insert
- 必须真实浏览器交互

证据文件：
- docs/verification/p2-runtime-regression-summary.json
- docs/verification/p2-runtime-regression-log.txt
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Fix Windows GBK encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

print("=" * 100)
print("P2 Runtime Regression Gate")
print("=" * 100)
print()
print(f"PROJECT_ROOT: {PROJECT_ROOT}")
print(f"Start time: {datetime.now().isoformat()}")
print()


def run_verification_script(script_name: str, script_path: Path) -> dict:
    """
    运行单个验收脚本并收集结果。
    
    Returns:
        dict with keys: name, exit_code, duration, stdout, stderr, run_id
    """
    print(f"{'=' * 100}")
    print(f"Running: {script_name}")
    print(f"{'=' * 100}")
    print()
    
    start_time = time.time()
    
    try:
        result = subprocess.run(
            [str(PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"), str(script_path)],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',  # Replace undecodable bytes
            timeout=300,  # 5 minutes max per script
        )
        
        duration = time.time() - start_time
        
        # Extract run_id from stdout
        run_id = None
        for line in result.stdout.split('\n'):
            if 'Run ID:' in line:
                run_id = line.split('Run ID:')[-1].strip()
                break
        
        return {
            "name": script_name,
            "script_path": str(script_path.relative_to(PROJECT_ROOT)),
            "exit_code": result.returncode,
            "duration": round(duration, 2),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "run_id": run_id,
            "success": result.returncode == 0,
        }
        
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return {
            "name": script_name,
            "script_path": str(script_path.relative_to(PROJECT_ROOT)),
            "exit_code": -1,
            "duration": round(duration, 2),
            "stdout": "",
            "stderr": "TIMEOUT: Script exceeded 300 seconds",
            "run_id": None,
            "success": False,
        }
    except Exception as e:
        duration = time.time() - start_time
        return {
            "name": script_name,
            "script_path": str(script_path.relative_to(PROJECT_ROOT)),
            "exit_code": -1,
            "duration": round(duration, 2),
            "stdout": "",
            "stderr": f"ERROR: {str(e)}",
            "run_id": None,
            "success": False,
        }


def check_api_evidence() -> dict:
    """检查 API 证据文件中的 localhost:8010 请求。"""
    # 明确列出所有 runtime network evidence 文件
    evidence_files = [
        "p2-1a-workbench-network-log.json",
        "p2-1a-observations-network-log.json",
        "p2-1b-observations-network-log.json",
        "p2-1c-workbench-network-log.json",
        "p2-1c-observations-network-log.json",
        "p2-1d-buy-workbench-network-log.json",
        "p2-1d-sell-workbench-network-log.json",
    ]
    
    api_check = {
        "files": {},
        "all_passed": True,
        "summary": {
            "total_files": len(evidence_files),
            "passed_files": 0,
            "failed_files": 0,
        }
    }
    
    for filename in evidence_files:
        filepath = PROJECT_ROOT / "docs" / "verification" / filename
        
        file_check = {
            "exists": False,
            "readable": False,
            "api_call_count": 0,
            "localhost_8010_api_call_count": 0,
            "non_8010_calls": [],
            "passed": False,
            "error": None,
        }
        
        # Check file exists
        if not filepath.exists():
            file_check["error"] = "File not found"
            api_check["files"][filename] = file_check
            api_check["all_passed"] = False
            api_check["summary"]["failed_files"] += 1
            continue
        
        file_check["exists"] = True
        
        # Try to read and parse JSON
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            file_check["readable"] = True
            
            # Check each request/response in the log
            # Support two formats:
            # 1. Array format: [{"url": "...", "method": "..."}, ...]
            # 2. Object format: {"requests": [...], "response": {...}}
            entries = []
            if isinstance(data, list):
                entries = data
            elif isinstance(data, dict):
                # P2-1D format
                if "requests" in data:
                    entries = data["requests"]
                # Also check response if it has a URL
                if "response" in data and isinstance(data["response"], dict):
                    if "url" in data["response"]:
                        entries.append(data["response"])
            
            for entry in entries:
                url = entry.get("url", "")
                
                # Count API calls
                if "/api/" in url:
                    file_check["api_call_count"] += 1
                    
                    if ":8010" in url and "localhost" in url:
                        file_check["localhost_8010_api_call_count"] += 1
                    else:
                        file_check["non_8010_calls"].append(url)
            
            # Validate: at least one API call, and all are localhost:8010
            if file_check["api_call_count"] == 0:
                file_check["error"] = "No /api/ requests found"
                file_check["passed"] = False
                api_check["all_passed"] = False
                api_check["summary"]["failed_files"] += 1
            elif len(file_check["non_8010_calls"]) > 0:
                file_check["error"] = f"Found {len(file_check['non_8010_calls'])} non-localhost:8010 API calls"
                file_check["passed"] = False
                api_check["all_passed"] = False
                api_check["summary"]["failed_files"] += 1
            else:
                file_check["passed"] = True
                api_check["summary"]["passed_files"] += 1
            
        except json.JSONDecodeError as e:
            file_check["error"] = f"JSON parse error: {str(e)}"
            api_check["all_passed"] = False
            api_check["summary"]["failed_files"] += 1
        except Exception as e:
            file_check["error"] = f"Read error: {str(e)}"
            api_check["all_passed"] = False
            api_check["summary"]["failed_files"] += 1
        
        api_check["files"][filename] = file_check
    
    return api_check


def check_backend_logs() -> dict:
    """检查 backend log 是否包含错误。"""
    log_files = [
        "p2-1a-backend-log.txt",
        "p2-1b-backend-log.txt",
        "p2-1c-backend-log.txt",
        "p2-1d-backend-log.txt",
    ]
    
    error_patterns = ["500", "Traceback", "sqlite", "Internal Server Error", "ERROR:"]
    
    log_check = {
        "checked_files": [],
        "clean": True,
        "errors_found": [],
    }
    
    for filename in log_files:
        filepath = PROJECT_ROOT / "docs" / "verification" / filename
        if not filepath.exists():
            continue
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            log_check["checked_files"].append(filename)
            
            for pattern in error_patterns:
                if pattern in content:
                    log_check["clean"] = False
                    log_check["errors_found"].append({
                        "file": filename,
                        "pattern": pattern,
                    })
        except Exception as e:
            print(f"WARNING: Could not check {filename}: {e}")
    
    return log_check


def main():
    overall_start = time.time()
    
    # Define verification scripts in order
    scripts = [
        ("P2-1A: Workbench → Observations", PROJECT_ROOT / "scripts" / "verify_p2_1a_workbench_to_observations.py"),
        ("P2-1B: Observations UX", PROJECT_ROOT / "scripts" / "verify_p2_1b_observations_ux.py"),
        ("P2-1C: Daily Signal Generation", PROJECT_ROOT / "scripts" / "verify_p2_1c_observation_daily_signal.py"),
        ("P2-1D: Sell Close P&L Review", PROJECT_ROOT / "scripts" / "verify_p2_1d_sell_close_review.py"),
    ]
    
    results = []
    all_passed = True
    
    # Run each script
    for script_name, script_path in scripts:
        result = run_verification_script(script_name, script_path)
        results.append(result)
        
        # Print summary
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print()
        print(f"{status}: {script_name}")
        print(f"   Exit code: {result['exit_code']}")
        print(f"   Duration: {result['duration']}s")
        print(f"   Run ID: {result['run_id']}")
        print()
        
        # Fail fast
        if not result["success"]:
            all_passed = False
            print(f"❌ FAIL: {script_name} failed with exit code {result['exit_code']}")
            print("Aborting regression gate...")
            break
    
    overall_duration = time.time() - overall_start
    
    # Check API evidence
    print()
    print("Checking API evidence...")
    api_check = check_api_evidence()
    print(f"   Total files: {api_check['summary']['total_files']}")
    print(f"   Passed files: {api_check['summary']['passed_files']}")
    print(f"   Failed files: {api_check['summary']['failed_files']}")
    
    if not api_check["all_passed"]:
        all_passed = False
        print("   ❌ API evidence check failed:")
        for filename, file_check in api_check["files"].items():
            if not file_check["passed"]:
                print(f"      - {filename}:")
                print(f"        exists: {file_check['exists']}")
                print(f"        readable: {file_check['readable']}")
                print(f"        api_call_count: {file_check['api_call_count']}")
                print(f"        error: {file_check['error']}")
                if file_check["non_8010_calls"]:
                    print(f"        non_8010_calls: {file_check['non_8010_calls'][:3]}")  # Show first 3
    else:
        print("   ✅ All API evidence files passed")
        # Print summary of API call counts
        for filename, file_check in api_check["files"].items():
            print(f"      {filename}: {file_check['api_call_count']} API calls")
    
    # Check backend logs
    print()
    print("Checking backend logs...")
    log_check = check_backend_logs()
    print(f"   Checked files: {len(log_check['checked_files'])}")
    print(f"   Clean (no errors): {log_check['clean']}")
    
    if not log_check["clean"]:
        all_passed = False
        print("   ❌ Found errors in backend logs:")
        for error in log_check["errors_found"]:
            print(f"      - {error['file']}: pattern '{error['pattern']}'")
    
    # Generate summary
    summary = {
        "timestamp": datetime.now().isoformat(),
        "overall_success": all_passed,
        "overall_duration": round(overall_duration, 2),
        "scripts": results,
        "api_check": api_check,
        "log_check": log_check,
    }
    
    summary_path = PROJECT_ROOT / "docs" / "verification" / "p2-runtime-regression-summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print()
    print(f"✅ Saved summary to {summary_path.relative_to(PROJECT_ROOT)}")
    
    # Generate detailed log
    log_path = PROJECT_ROOT / "docs" / "verification" / "p2-runtime-regression-log.txt"
    with open(log_path, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write("P2 Runtime Regression Gate - Detailed Log\n")
        f.write("=" * 100 + "\n")
        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
        f.write(f"Overall Success: {all_passed}\n")
        f.write(f"Overall Duration: {overall_duration:.2f}s\n")
        f.write("\n")
        
        for result in results:
            f.write("=" * 100 + "\n")
            f.write(f"Script: {result['name']}\n")
            f.write("=" * 100 + "\n")
            f.write(f"Exit Code: {result['exit_code']}\n")
            f.write(f"Duration: {result['duration']}s\n")
            f.write(f"Run ID: {result['run_id']}\n")
            f.write(f"Success: {result['success']}\n")
            f.write("\n")
            f.write("STDOUT:\n")
            f.write(result['stdout'])
            f.write("\n\n")
            if result['stderr']:
                f.write("STDERR:\n")
                f.write(result['stderr'])
                f.write("\n\n")
    
    print(f"✅ Saved detailed log to {log_path.relative_to(PROJECT_ROOT)}")
    
    # Final summary
    print()
    print("=" * 100)
    if all_passed:
        print("✅ P2 RUNTIME REGRESSION GATE PASSED")
    else:
        print("❌ P2 RUNTIME REGRESSION GATE FAILED")
    print("=" * 100)
    print()
    print("Summary:")
    for result in results:
        status = "✅" if result["success"] else "❌"
        print(f"  {status} {result['name']}: exit code {result['exit_code']}, {result['duration']}s, run_id={result['run_id']}")
    print()
    print(f"Overall duration: {overall_duration:.2f}s")
    print()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
