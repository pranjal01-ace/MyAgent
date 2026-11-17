"""
System Information and Resource Usage Tools.

Provides safe diagnostic metrics about host OS, CPU, RAM, disk, and hardware.
"""

import sys
import platform
import asyncio
from typing import Dict, Any
import psutil

from backend.tools.base import BaseTool
from backend.tools.schemas import PermissionLevel, ToolResult, ToolContext


class GetSystemInfoTool(BaseTool):
    """Returns comprehensive host hardware, operating system, and environment specifications."""

    name = "get_system_info"
    description = "Returns host OS, CPU specs, RAM usage, drive storage stats, and environment versions."
    category = "system"
    version = "2.0"
    permission_level = PermissionLevel.READ_ONLY
    requires_confirmation = False
    cacheable = True
    cache_ttl = 30  # Dynamic metrics refreshed after 30 seconds
    timeout_seconds = 6.0

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        def _gather_info():
            import time
            import subprocess
            import shutil

            uname = platform.uname()
            mem = psutil.virtual_memory()

            # CPU
            cpu_pct = psutil.cpu_percent(interval=0.1)
            cpu_freq = psutil.cpu_freq()
            freq_ghz = round(cpu_freq.current / 1000, 2) if cpu_freq and cpu_freq.current else None
            phys_cores = psutil.cpu_count(logical=False) or 1
            logical_cores = psutil.cpu_count(logical=True) or 1

            # Disks (All mounted drives)
            drives = []
            try:
                for part in psutil.disk_partitions(all=False):
                    try:
                        usage = psutil.disk_usage(part.mountpoint)
                        drives.append({
                            "drive": part.device or part.mountpoint,
                            "mountpoint": part.mountpoint,
                            "fstype": part.fstype,
                            "total_gb": round(usage.total / (1024 ** 3), 1),
                            "used_gb": round(usage.used / (1024 ** 3), 1),
                            "free_gb": round(usage.free / (1024 ** 3), 1),
                            "percent_used": usage.percent
                        })
                    except (PermissionError, OSError):
                        continue
            except Exception:
                # Fallback to root drive
                try:
                    root_usage = psutil.disk_usage("/")
                    drives.append({
                        "drive": "/",
                        "mountpoint": "/",
                        "fstype": "unknown",
                        "total_gb": round(root_usage.total / (1024 ** 3), 1),
                        "used_gb": round(root_usage.used / (1024 ** 3), 1),
                        "free_gb": round(root_usage.free / (1024 ** 3), 1),
                        "percent_used": root_usage.percent
                    })
                except Exception:
                    pass

            # Uptime
            boot_time = psutil.boot_time()
            uptime_seconds = int(time.time() - boot_time)
            uptime_hours = uptime_seconds // 3600
            uptime_days = uptime_hours // 24
            uptime_str = f"{uptime_days}d {uptime_hours % 24}h" if uptime_days > 0 else f"{uptime_hours}h {int((uptime_seconds % 3600) / 60)}m"

            # Optional Node.js version
            node_version = None
            if shutil.which("node"):
                try:
                    res = subprocess.run(["node", "-v"], capture_output=True, text=True, timeout=2, shell=False)
                    if res.returncode == 0:
                        node_version = res.stdout.strip()
                except Exception:
                    pass

            # Optional GPU
            gpu_info = None
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                gpu_name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(gpu_name, bytes):
                    gpu_name = gpu_name.decode("utf-8")
                gpu_util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                gpu_info = f"{gpu_name} ({gpu_util.gpu}% usage)"
            except Exception:
                pass

            return {
                "cpu": {
                    "processor": uname.processor or platform.processor() or "Unknown CPU",
                    "physical_cores": phys_cores,
                    "logical_cores": logical_cores,
                    "frequency_ghz": freq_ghz,
                    "usage_percent": cpu_pct
                },
                "memory": {
                    "total_gb": round(mem.total / (1024 ** 3), 2),
                    "used_gb": round(mem.used / (1024 ** 3), 2),
                    "available_gb": round(mem.available / (1024 ** 3), 2),
                    "usage_percent": mem.percent
                },
                "drives": drives,
                "os": {
                    "name": uname.system,
                    "release": uname.release,
                    "version": uname.version,
                    "architecture": platform.machine(),
                    "hostname": uname.node
                },
                "uptime": uptime_str,
                "python_version": platform.python_version(),
                "node_version": node_version,
                "gpu": gpu_info,
                # Backward-compatibility top-level keys for Phase 1 contracts
                "cpu_count_logical": logical_cores,
                "cpu_count_physical": phys_cores,
                "processor": uname.processor or platform.processor() or "Unknown CPU",
                "ram_total_gb": round(mem.total / (1024 ** 3), 2),
                "ram_available_gb": round(mem.available / (1024 ** 3), 2),
                "disk_total_gb": drives[0]["total_gb"] if drives else 0.0,
                "disk_free_gb": drives[0]["free_gb"] if drives else 0.0,
                "hostname": uname.node
            }

        data = await asyncio.to_thread(_gather_info)

        # Human-Readable Formatted Message
        drive_lines = []
        for d in data["drives"]:
            drive_lines.append(f"  • {d['drive']} : {d['total_gb']} GB total ({d['free_gb']} GB free, {d['percent_used']}% used)")
        drives_str = "\n".join(drive_lines) if drive_lines else "  • No drives detected"

        cpu = data["cpu"]
        mem = data["memory"]
        os_info = data["os"]
        freq_str = f" @ {cpu['frequency_ghz']} GHz" if cpu['frequency_ghz'] else ""
        gpu_str = f"\n**GPU**: {data['gpu']}" if data['gpu'] else ""
        node_str = f" | Node.js: {data['node_version']}" if data['node_version'] else ""

        formatted_summary = (
            f"### 🖥️ System Information\n\n"
            f"**Operating System**: {os_info['name']} {os_info['release']} ({os_info['architecture']}) | Host: `{os_info['hostname']}`\n"
            f"**CPU**: {cpu['processor']} ({cpu['physical_cores']} cores / {cpu['logical_cores']} threads{freq_str}) | Usage: **{cpu['usage_percent']}%**\n"
            f"**Memory**: {mem['total_gb']} GB RAM | Used: {mem['used_gb']} GB (**{mem['usage_percent']}%**) | Available: {mem['available_gb']} GB\n\n"
            f"**Drives**:\n{drives_str}\n\n"
            f"**Uptime**: {data['uptime']} | **Python**: {data['python_version']}{node_str}{gpu_str}"
        )

        return ToolResult(
            success=True,
            tool=self.name,
            data=data,
            message=formatted_summary
        )


class GetResourceUsageTool(BaseTool):
    """Returns real-time dynamic CPU, memory, disk, and GPU utilization metrics."""

    name = "get_resource_usage"
    description = "Returns current real-time CPU usage, RAM utilization, and disk status."
    category = "system"
    version = "1.0"
    permission_level = PermissionLevel.AUTOMATIC
    requires_confirmation = False
    cacheable = False  # Real-time metrics must never be cached
    timeout_seconds = 5.0

    async def execute(self, arguments: Dict[str, Any], context: ToolContext) -> ToolResult:
        def _gather_usage():
            cpu_pct = psutil.cpu_percent(interval=0.2)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            battery = psutil.sensors_battery()

            usage = {
                "cpu_percent": cpu_pct,
                "ram_percent": mem.percent,
                "ram_used_mb": round(mem.used / (1024 ** 2), 1),
                "ram_available_mb": round(mem.available / (1024 ** 2), 1),
                "ram_total_mb": round(mem.total / (1024 ** 2), 1),
                "disk_percent": disk.percent,
                "disk_used_gb": round(disk.used / (1024 ** 3), 1),
                "disk_free_gb": round(disk.free / (1024 ** 3), 1),
                "battery_percent": battery.percent if battery else None,
                "power_plugged": battery.power_plugged if battery else None
            }

            # Safe GPU check if py3nvml / torch available without blocking
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                gpu_util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                usage["gpu_percent"] = gpu_util.gpu
            except Exception:
                usage["gpu_percent"] = None

            return usage

        data = await asyncio.to_thread(_gather_usage)
        bat_text = f" | Battery: {data['battery_percent']}%" if data['battery_percent'] is not None else ""
        summary = (
            f"CPU: {data['cpu_percent']}% | "
            f"RAM: {data['ram_percent']}% ({data['ram_used_mb']} MB used / {data['ram_total_mb']} MB total) | "
            f"Disk: {data['disk_percent']}% used ({data['disk_free_gb']} GB free){bat_text}"
        )
        return ToolResult(
            success=True,
            tool=self.name,
            data=data,
            message=summary
        )
