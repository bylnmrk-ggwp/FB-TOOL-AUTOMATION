"""
Memory tracking utility for the Facebook automation system.

Provides per-process memory tracking for browser processes spawned by
Playwright. Reports total RSS memory for all Brave/Chromium processes,
and estimates per-context memory when page references are available.

psutil is an optional dependency — if not installed, all methods return 0.
"""
import time

# Optional psutil dependency
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


def _get_process_name_filter() -> list[str]:
    """Return list of browser process name fragments to track."""
    return ["brave", "chromium", "chrome"]


def get_total_browser_memory() -> float:
    """Return total RSS memory in MB of all browser processes.

    Uses a set of seen PIDs to avoid double-counting child processes
    that also match the browser name filter.
    """
    if not HAS_PSUTIL:
        return 0.0
    total = 0.0
    seen_pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pid = proc.info["pid"]
            if pid in seen_pids:
                continue
            name = proc.info["name"].lower()
            if any(b in name for b in _get_process_name_filter()):
                seen_pids.add(pid)
                total += proc.memory_info().rss
                # Include children (utility processes, GPU, etc.) — only if not already counted
                try:
                    for child in proc.children(recursive=True):
                        if child.pid not in seen_pids:
                            seen_pids.add(child.pid)
                            total += child.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            pass
    return total / (1024 * 1024)


def get_browser_process_count() -> int:
    """Return number of browser processes (parent + children)."""
    if not HAS_PSUTIL:
        return 0
    count = 0
    seen: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            name = proc.info["name"].lower()
            pid = proc.info["pid"]
            if any(b in name for b in _get_process_name_filter()) and pid not in seen:
                seen.add(pid)
                count += 1
                try:
                    for child in proc.children(recursive=True):
                        if child.pid not in seen:
                            seen.add(child.pid)
                            count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied, KeyError):
            pass
    return count


def get_system_memory() -> dict:
    """Return system memory info dict with keys: total_gb, used_gb, available_gb, percent."""
    if not HAS_PSUTIL:
        return {"total_gb": 0, "used_gb": 0, "available_gb": 0, "percent": 0}
    mem = psutil.virtual_memory()
    return {
        "total_gb": round(mem.total / (1024 ** 3), 1),
        "used_gb": round(mem.used / (1024 ** 3), 1),
        "available_gb": round(mem.available / (1024 ** 3), 1),
        "percent": mem.percent,
    }


class MemorySnapshot:
    """A point-in-time snapshot of memory usage."""

    def __init__(self):
        self.timestamp = time.monotonic()
        self.browser_mb = get_total_browser_memory()
        self.process_count = get_browser_process_count()
        self.system = get_system_memory()
        self.profile_memory: dict[str, float] = {}  # profile_name → estimated MB
        self.profile_js_heaps: dict[str, float] = {}  # profile_name → JS heap MB

    def record_profile_js(self, profile_name: str, js_heap_mb: float):
        """Record JS heap for a given profile."""
        self.profile_js_heaps[profile_name] = js_heap_mb
        # Estimated total = JS heap + baseline overhead (~135 MB per context)
        self.profile_memory[profile_name] = round(js_heap_mb + 135, 1)


class MemoryTracker:
    """Periodic memory tracker that aggregates data from the driver manager."""

    def __init__(self):
        self._peak_browser_mb: float = 0.0

    def snapshot(self, profile_js_heaps: dict[str, float] | None = None) -> MemorySnapshot:
        """Take a memory snapshot, optionally with per-profile JS heap data."""
        snap = MemorySnapshot()
        if profile_js_heaps:
            for name, heap in profile_js_heaps.items():
                snap.record_profile_js(name, heap)
        if snap.browser_mb > self._peak_browser_mb:
            self._peak_browser_mb = snap.browser_mb
        return snap

    @property
    def peak_mb(self) -> float:
        return self._peak_browser_mb
