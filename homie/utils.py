"""System utilities for resource monitoring."""

import socket
import subprocess
from dataclasses import dataclass
from typing import Optional

import psutil


@dataclass
class SystemStats:
    """System resource statistics."""

    hostname: str
    cpu_count: int
    cpu_percent_used: float
    ram_total_gb: float
    ram_free_gb: float
    gpu_name: Optional[str] = None
    gpu_memory_total_gb: Optional[float] = None
    gpu_memory_free_gb: Optional[float] = None


def get_local_ip() -> str:
    """Get the local IP address for LAN communication."""
    try:
        # Connect to a public DNS to determine local IP (doesn't actually send data)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_hostname() -> str:
    """Get the system hostname."""
    return socket.gethostname()


def get_cpu_count() -> int:
    """Get number of CPU cores."""
    return psutil.cpu_count(logical=True) or 1


def get_cpu_percent() -> float:
    """Get CPU usage percentage (0-100)."""
    return psutil.cpu_percent(interval=0.1)


def get_ram_total_gb() -> float:
    """Get total RAM in GB."""
    return psutil.virtual_memory().total / (1024**3)


def get_ram_free_gb() -> float:
    """Get available RAM in GB."""
    return psutil.virtual_memory().available / (1024**3)


def get_gpu_info() -> tuple[Optional[str], Optional[float], Optional[float]]:
    """
    Get GPU information using nvidia-smi.
    Returns: (gpu_name, total_memory_gb, free_memory_gb) or (None, None, None)
    """
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().split("\n")[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name = parts[0]
                total_mb = float(parts[1])
                free_mb = float(parts[2])
                return name, total_mb / 1024, free_mb / 1024
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return None, None, None


def get_system_stats() -> SystemStats:
    """Get comprehensive system statistics."""
    gpu_name, gpu_total, gpu_free = get_gpu_info()

    return SystemStats(
        hostname=get_hostname(),
        cpu_count=get_cpu_count(),
        cpu_percent_used=get_cpu_percent(),
        ram_total_gb=get_ram_total_gb(),
        ram_free_gb=get_ram_free_gb(),
        gpu_name=gpu_name,
        gpu_memory_total_gb=gpu_total,
        gpu_memory_free_gb=gpu_free,
    )
