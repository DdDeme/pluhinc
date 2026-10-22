"""Small helpers that read system stats straight from /proc and /sys (no extra packages)."""
import shutil
import socket
import subprocess
import time


def cpu_temp():
    """CPU temperature in C, or None."""
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except (OSError, ValueError):
        return None


def memory():
    """(used_mb, total_mb, fraction_used)."""
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.split()[0])  # kB
        total = info["MemTotal"] / 1024.0
        used = total - info["MemAvailable"] / 1024.0
        return used, total, (used / total if total else 0.0)
    except (OSError, ValueError, KeyError):
        return 0.0, 0.0, 0.0


def disk(path="/"):
    """(used_gb, total_gb, fraction_used)."""
    try:
        usage = shutil.disk_usage(path)
        return usage.used / 1e9, usage.total / 1e9, usage.used / usage.total
    except OSError:
        return 0.0, 0.0, 0.0


def uptime():
    try:
        with open("/proc/uptime") as f:
            seconds = int(float(f.read().split()[0]))
    except (OSError, ValueError):
        return "n/a"
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes = rest // 60
    if days:
        return f"{days}d {hours:02d}h"
    return f"{hours}h {minutes:02d}m"


_ip_cache = (-1e9, "")


def ip_address():
    """First IP address, refreshed at most every 5 seconds."""
    global _ip_cache
    now = time.monotonic()
    if now - _ip_cache[0] > 5:
        try:
            out = subprocess.run(
                ["hostname", "-I"], capture_output=True, text=True, timeout=1
            ).stdout.split()
            addr = out[0] if out else "no network"
        except Exception:
            addr = "no network"
        _ip_cache = (now, addr)
    return _ip_cache[1]


def hostname():
    return socket.gethostname()


class CpuMeter:
    """CPU load in percent, measured between calls to percent()."""

    def __init__(self):
        self.last = 0.0
        self._prev = self._read()

    @staticmethod
    def _read():
        with open("/proc/stat") as f:
            values = [int(v) for v in f.readline().split()[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return idle, sum(values)

    def percent(self):
        try:
            idle, total = self._read()
        except (OSError, ValueError):
            return self.last
        prev_idle, prev_total = self._prev
        self._prev = (idle, total)
        delta = total - prev_total
        if delta > 0:
            self.last = 100.0 * (1.0 - (idle - prev_idle) / delta)
        return self.last
