"""
Runtime Process Helpers

Shared utilities for runtime verification scripts:
- Port cleanup with ownership verification
- HTTP health check with PID validation
- Backend/Frontend process management
- Process health monitoring
- Log capture

Used by: verify_p2_*, verify_p3_* scripts
"""

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional

import requests


def get_port_owner_pid(port: int) -> Optional[int]:
    """
    Get PID of process owning the specified port.
    
    Returns None if port is not in use.
    Uses PowerShell Get-NetTCPConnection.
    """
    command = (
        f"Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue "
        "| Select-Object -ExpandProperty OwningProcess -Unique"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    if result.returncode != 0 or not result.stdout.strip():
        return None
    
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def get_process_command_line(pid: int) -> Optional[str]:
    """Get command line of process by PID."""
    command = f"Get-WmiObject Win32_Process -Filter \"ProcessId = {pid}\" | Select-Object -ExpandProperty CommandLine"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    
    if result.returncode != 0:
        return None
    
    return result.stdout.strip() or None


def get_parent_pid(pid: int) -> Optional[int]:
    """Get parent PID for a process."""
    command = f"Get-WmiObject Win32_Process -Filter \"ProcessId = {pid}\" | Select-Object -ExpandProperty ParentProcessId"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def is_descendant_process(parent_pid: int, child_pid: int) -> bool:
    """Return True when child_pid belongs to parent_pid's process tree."""
    current_pid = child_pid
    visited: set[int] = set()

    while current_pid and current_pid not in visited:
        if current_pid == parent_pid:
            return True
        visited.add(current_pid)
        current_pid = get_parent_pid(current_pid)

    return False


def release_port(port: int) -> None:
    """
    Kill process using the specified port.
    
    Only kills the specific PID owning the port, not all python.exe/node.exe.
    """
    owner_pid = get_port_owner_pid(port)
    
    if owner_pid is None:
        return
    
    print(f"[INFO] Port {port} is owned by PID {owner_pid}")
    
    # Get command line for logging
    cmdline = get_process_command_line(owner_pid)
    if cmdline:
        print(f"[INFO] Process command: {cmdline[:100]}...")
    
    # Kill specific PID
    subprocess.run(
        ["taskkill", "/F", "/PID", str(owner_pid)],
        capture_output=True,
        check=False,
    )
    
    print(f"[OK] Killed PID {owner_pid} on port {port}")
    time.sleep(2)
    
    # Verify port is free
    if get_port_owner_pid(port) is not None:
        raise RuntimeError(f"Port {port} still in use after killing PID {owner_pid}")


def wait_for_http(
    url: str,
    timeout_seconds: int = 60,
    process: Optional[subprocess.Popen] = None,
    process_name: str = "process",
    expected_port: Optional[int] = None,
    port_owner_validator: Optional[Callable[[int], bool]] = None,
) -> bool:
    """
    Wait for HTTP endpoint to respond with 200.
    
    If process is provided, checks process.poll() after each attempt.
    If expected_port is provided, verifies the port owner is accepted by
    port_owner_validator. Without a custom validator, the owner must match the
    process PID.
    If process died, prints stderr/stdout tail and returns False.
    
    Returns True if endpoint is ready, False if timeout or process died.
    """
    for attempt in range(timeout_seconds):
        time.sleep(1)
        
        # Check if process died
        if process and process.poll() is not None:
            print(f"[FAIL] {process_name} process died during startup (exit code {process.poll()})")
            
            # Print stderr tail
            if process.stderr:
                try:
                    stderr_lines = process.stderr.readlines()
                    if stderr_lines:
                        print(f"\n{process_name} stderr (last 20 lines):")
                        for line in stderr_lines[-20:]:
                            print(f"  {line.rstrip()}")
                except:
                    pass
            
            # Print stdout tail
            if process.stdout:
                try:
                    stdout_lines = process.stdout.readlines()
                    if stdout_lines:
                        print(f"\n{process_name} stdout (last 20 lines):")
                        for line in stdout_lines[-20:]:
                            print(f"  {line.rstrip()}")
                except:
                    pass
            
            return False
        
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                # Double-check process is still alive
                if process and process.poll() is not None:
                    print(f"[FAIL] {process_name} died immediately after responding")
                    return False
                
                # Verify port ownership if expected_port provided
                if expected_port and process:
                    port_owner = get_port_owner_pid(expected_port)
                    if port_owner is None:
                        print(f"[FAIL] Port {expected_port} has no listener after {url} returned 200")
                        return False

                    owner_ok = (
                        port_owner_validator(port_owner)
                        if port_owner_validator
                        else port_owner == process.pid
                    )

                    if not owner_ok:
                        print(f"[FAIL] Port {expected_port} is owned by PID {port_owner}, not {process.pid} or its expected child")
                        if port_owner:
                            cmdline = get_process_command_line(port_owner)
                            print(f"[FAIL] Port owner command: {cmdline}")
                        return False
                
                print(f"[OK] {process_name} ready after {attempt + 1} seconds")
                if expected_port and process:
                    print(f"[OK] Port {expected_port} ownership verified")
                return True
        except requests.exceptions.RequestException:
            pass
    
    print(f"[FAIL] {process_name} did not respond to {url} within {timeout_seconds} seconds")
    return False


def start_backend(
    port: int = 8010,
    project_root: Optional[Path] = None,
    timeout_seconds: int = 60,
    extra_env: Optional[dict[str, str]] = None,
) -> subprocess.Popen:
    """
    Start backend server on specified port.
    
    Verifies:
    - Process stays alive during startup
    - /health returns 200
    - Port owner PID belongs to the started Python process tree
    
    Returns: Popen process if successful
    Exits with code 1 if startup fails
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent
    
    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    
    env = os.environ.copy()
    
    # Load .env.local if it exists
    env_local = Path(project_root) / ".env.local"
    if env_local.exists():
        with open(env_local, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    env[key.strip()] = value.strip()
    
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONPATH"] = str(project_root)
    if extra_env:
        env.update(extra_env)
    
    print(f"Starting backend on port {port}...")
    print(f"  Python: {venv_python}")
    print(f"  Module: backend.app.main:app")
    
    process = subprocess.Popen(
        [
            str(venv_python),
            "-m",
            "uvicorn",
            "backend.app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
        ],
        cwd=project_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    
    print(f"[INFO] Started backend process PID {process.pid}")
    
    # Wait for health check
    health_url = f"http://localhost:{port}/health"
    
    def backend_owner_validator(port_owner_pid: int) -> bool:
        return port_owner_pid == process.pid or is_descendant_process(process.pid, port_owner_pid)

    if not wait_for_http(
        health_url,
        timeout_seconds,
        process,
        "Backend",
        expected_port=port,
        port_owner_validator=backend_owner_validator,
    ):
        process.kill()
        sys.exit(1)
    
    return process


def start_frontend(
    port: int = 3010,
    project_root: Optional[Path] = None,
    timeout_seconds: int = 90,
) -> subprocess.Popen:
    """
    Start frontend dev server on specified port.
    
    Enforces exact port (no auto-increment to 3001/3004).
    Verifies port owner belongs to the started npm/cmd process tree.
    
    Returns: Popen process if successful
    Exits with code 1 if startup fails
    """
    if project_root is None:
        project_root = Path(__file__).parent.parent
    
    frontend_dir = project_root / "frontend"
    
    print(f"Starting frontend on port {port}...")
    print(f"  Directory: {frontend_dir}")
    
    process = subprocess.Popen(
        ["cmd", "/c", "npm", "run", "dev", "--", "--port", str(port)],
        cwd=frontend_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    
    print(f"[INFO] Started frontend process PID {process.pid}")
    
    # Wait for frontend
    frontend_url = f"http://localhost:{port}"
    
    def frontend_owner_validator(port_owner_pid: int) -> bool:
        return port_owner_pid == process.pid or is_descendant_process(process.pid, port_owner_pid)

    if not wait_for_http(
        frontend_url,
        timeout_seconds,
        process,
        "Frontend",
        expected_port=port,
        port_owner_validator=frontend_owner_validator,
    ):
        process.kill()
        sys.exit(1)
    
    return process


def stop_process(
    process: subprocess.Popen,
    name: str = "process",
    save_log: Optional[Path] = None,
    release_ports: Optional[list[int]] = None,
) -> None:
    """
    Stop process gracefully, then forcefully.
    
    Optionally saves stdout to log file.
    """
    try:
        if process.poll() is None:
            process.terminate()

        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass

        if release_ports:
            for port in release_ports:
                if get_port_owner_pid(port) is not None:
                    release_port(port)

        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                check=False,
            )

        try:
            stdout, stderr = process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", ""
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()

        if save_log:
            save_log.parent.mkdir(parents=True, exist_ok=True)
            with open(save_log, "w", encoding="utf-8") as f:
                if stdout:
                    f.write(stdout)
                if stderr:
                    f.write(stderr)
            print(f"[OK] Saved {name} log to {save_log}")
        
        print(f"[OK] {name} process stopped")
    except Exception as e:
        print(f"[WARN] Error stopping {name}: {e}")


def check_and_release_ports(ports: list[int]) -> None:
    """
    Check and release multiple ports.
    Verifies each port is free after release.
    """
    print(f"Checking ports {ports}...")
    for port in ports:
        owner = get_port_owner_pid(port)
        if owner:
            print(f"[WARN] Port {port} is in use, releasing...")
            release_port(port)
        else:
            print(f"[OK] Port {port} is free")
    
    # Final verification
    for port in ports:
        owner = get_port_owner_pid(port)
        if owner:
            raise RuntimeError(f"Port {port} still in use by PID {owner} after release")
    
    print(f"[OK] All ports {ports} are available")
    print()


def get_process_output_tail(process: subprocess.Popen, lines: int = 50) -> list[str]:
    """
    Get last N lines from process stdout/stderr.
    """
    output = []
    
    if process.stdout:
        try:
            all_lines = process.stdout.readlines()
            output.extend(all_lines[-lines:])
        except:
            pass
    
    if process.stderr:
        try:
            all_lines = process.stderr.readlines()
            output.extend(all_lines[-lines:])
        except:
            pass
    
    return output
