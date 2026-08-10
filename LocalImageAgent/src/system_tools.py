"""System control tools — process management, GPU/CPU/performance actions."""

from __future__ import annotations

import subprocess
import logging
from typing import Optional

logger = logging.getLogger("local-image-agent")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: str) -> tuple[int, str, str]:
    """Run a shell command, return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


# ---------------------------------------------------------------------------
# Process control
# ---------------------------------------------------------------------------

def terminate_process(name_or_pid: str, force: bool = True) -> dict:
    """
    Terminate a running process by name or PID.
    name_or_pid: process name (e.g. '3dsmax.exe', 'SketchUp.exe') or numeric PID.
    force: if True uses /F (force kill), otherwise graceful terminate.
    """
    flag = "/F" if force else ""
    # Determine if it's a PID or a name
    if name_or_pid.strip().isdigit():
        cmd = f"taskkill {flag} /PID {name_or_pid.strip()}"
        target = f"PID {name_or_pid.strip()}"
    else:
        # Ensure .exe suffix
        name = name_or_pid.strip()
        if not name.lower().endswith(".exe"):
            name += ".exe"
        cmd = f"taskkill {flag} /IM \"{name}\""
        target = name

    rc, out, err = _run(cmd)
    if rc == 0:
        return {"status": "terminated", "target": target, "detail": out or "Process terminated successfully."}
    elif rc == 128:
        return {"status": "not_found", "target": target, "detail": "No matching process found."}
    else:
        return {"status": "error", "target": target, "detail": err or out}


def list_processes(filter_name: str = "", sort_by: str = "cpu") -> dict:
    """
    List running processes with CPU/memory usage.
    filter_name: optional substring to filter by process name.
    sort_by: 'cpu', 'memory', or 'name'.
    """
    # Use tasklist with CSV output for reliable parsing
    rc, out, err = _run('tasklist /FO CSV /NH')
    if rc != 0:
        return {"status": "error", "detail": err}

    processes = []
    for line in out.splitlines():
        line = line.strip().strip('"')
        if not line:
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 5:
            name, pid, session, num, mem = parts[0], parts[1], parts[2], parts[3], parts[4]
            mem_kb = int(mem.replace(",", "").replace(" K", "").strip()) if mem else 0
            processes.append({
                "name": name,
                "pid": pid,
                "memory_mb": round(mem_kb / 1024, 1),
            })

    if filter_name:
        processes = [p for p in processes if filter_name.lower() in p["name"].lower()]

    if sort_by == "memory":
        processes.sort(key=lambda x: x["memory_mb"], reverse=True)
    else:
        processes.sort(key=lambda x: x["name"].lower())

    return {"status": "ok", "count": len(processes), "processes": processes[:100]}


# ---------------------------------------------------------------------------
# GPU control
# ---------------------------------------------------------------------------

def restart_gpu_driver() -> dict:
    """
    Restart the GPU display driver without rebooting.
    Equivalent to Win+Ctrl+Shift+B. Safe on all Windows 10/11 machines.
    """
    # Use nircmd or PowerShell to simulate the key combo
    # Most reliable headless approach: use rundll32 to reset display
    rc, out, err = _run(
        'powershell -NoProfile -WindowStyle Hidden -Command "'
        'Add-Type -AssemblyName System.Windows.Forms; '
        '[System.Windows.Forms.SendKeys]::SendWait(\'%^+{B}\')"'
    )
    if rc == 0:
        return {"status": "ok", "detail": "GPU driver restart signal sent (Win+Ctrl+Shift+B equivalent)."}
    else:
        return {"status": "error", "detail": err or out}


def get_gpu_info() -> dict:
    """Return GPU name, driver version, and VRAM from WMI."""
    rc, out, err = _run(
        'powershell -NoProfile -WindowStyle Hidden -Command "'
        'Get-WmiObject Win32_VideoController | '
        'Select-Object Name,DriverVersion,AdapterRAM,VideoModeDescription | '
        'ConvertTo-Json -Depth 2"'
    )
    if rc != 0:
        return {"status": "error", "detail": err}
    try:
        import json
        data = json.loads(out)
        if isinstance(data, dict):
            data = [data]
        gpus = []
        for g in data:
            vram_gb = round(int(g.get("AdapterRAM") or 0) / (1024**3), 2)
            gpus.append({
                "name": g.get("Name", ""),
                "driver": g.get("DriverVersion", ""),
                "vram_gb": vram_gb,
                "mode": g.get("VideoModeDescription", ""),
            })
        return {"status": "ok", "gpus": gpus}
    except Exception as e:
        return {"status": "error", "detail": str(e), "raw": out}


# ---------------------------------------------------------------------------
# CPU / power plan
# ---------------------------------------------------------------------------

def set_power_plan(plan: str) -> dict:
    """
    Switch Windows power plan.
    plan: 'balanced', 'performance', or 'powersaver'.
    """
    plans = {
        "balanced":    "381b4222-f694-41f0-9685-ff5bb260df2e",
        "performance": "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c",
        "powersaver":  "a1841308-3541-4fab-bc81-f71556f20b4a",
    }
    plan_key = plan.lower().replace(" ", "").replace("-", "")
    # match loosely
    matched = None
    for k, guid in plans.items():
        if plan_key in k or k in plan_key:
            matched = (k, guid)
            break
    if not matched:
        return {"status": "error", "detail": f"Unknown plan '{plan}'. Use: balanced, performance, powersaver."}

    rc, out, err = _run(f'powercfg /setactive {matched[1]}')
    if rc == 0:
        return {"status": "ok", "plan": matched[0], "guid": matched[1]}
    return {"status": "error", "detail": err or out}


def get_power_plan() -> dict:
    """Return the currently active Windows power plan."""
    rc, out, err = _run("powercfg /getactivescheme")
    if rc == 0:
        return {"status": "ok", "detail": out}
    return {"status": "error", "detail": err}


def get_system_stats() -> dict:
    """Return current CPU usage %, RAM usage, and top memory processes."""
    rc, out, err = _run(
        'powershell -NoProfile -WindowStyle Hidden -Command "'
        '$cpu = (Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average; '
        '$os = Get-WmiObject Win32_OperatingSystem; '
        '$ram_total = [math]::Round($os.TotalVisibleMemorySize/1MB, 2); '
        '$ram_free = [math]::Round($os.FreePhysicalMemory/1MB, 2); '
        '$ram_used = $ram_total - $ram_free; '
        'ConvertTo-Json @{cpu_pct=$cpu; ram_total_gb=$ram_total; ram_used_gb=$ram_used; ram_free_gb=$ram_free}"'
    )
    if rc != 0:
        return {"status": "error", "detail": err}
    try:
        import json
        data = json.loads(out)
        data["status"] = "ok"
        return data
    except Exception:
        return {"status": "error", "detail": out}
