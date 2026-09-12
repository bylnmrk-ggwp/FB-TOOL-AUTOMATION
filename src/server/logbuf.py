"""The server's log: a ring of recent lines plus the daily file LogTab writes.

manager.log is called from the worker thread and the bridge writes here
too, so one lock guards both the ring and the file handle. The level rule,
the file name and the line format are LogTab.write's, copied rather than
imported: pulling src.ui.log_tab in would drag tkinter into a headless
server, and the two must agree regardless, because the Tk app and the
server append to the same app-YYYYMMDD.log.
"""
import threading
from collections import deque
from datetime import datetime
from pathlib import Path


class LogRing:
    MAX_LINES = 2000
    # Must stay equal to LogTab.LOG_DIR - both write app-YYYYMMDD.log here.
    LOG_DIR = Path.home() / ".autoshare" / "logs"

    def __init__(self, maxlen: int = MAX_LINES, log_dir: Path | None = None):
        self._lines: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._log_dir = Path(log_dir) if log_dir is not None else self.LOG_DIR
        self._file = None
        self._file_day = None
        self._on_line = None

    @property
    def log_path(self) -> Path:
        """Today's log file, whether or not it has been opened yet."""
        return self._log_dir / f"app-{datetime.now():%Y%m%d}.log"

    @staticmethod
    def level_of(text: str) -> str:
        """LogTab.write's icon-to-level rule, on an already stripped line."""
        if text.startswith("✓"):
            return "ok"
        lowered = text.lower()
        if text.startswith("✗") or "error" in lowered or "fail" in lowered:
            return "error"
        return "info"

    def set_on_line(self, cb) -> None:
        """cb(entry) runs after every write(), on the writer's thread."""
        with self._lock:
            self._on_line = cb

    def write(self, message: str) -> dict:
        """Thread-safe. Records one line and returns it as the entry the
        ring keeps: {"stamp": "HH:MM:SS", "text": ..., "level": ...}."""
        now = datetime.now()
        text = str(message).strip()
        entry = {"stamp": now.strftime("%H:%M:%S"), "text": text,
                 "level": self.level_of(text)}
        with self._lock:
            # To disk first, as LogTab does: the ring trims itself and the
            # file is the record that survives the session.
            self._write_to_file(now.strftime("%Y-%m-%d %H:%M:%S"), text)
            self._lines.append(entry)
            cb = self._on_line
        if cb is not None:
            # Outside the lock so a callback that logs cannot deadlock, and
            # swallowed so a broken subscriber never takes the worker thread
            # down with a log line.
            try:
                cb(entry)
            except Exception:
                pass
        return entry

    def tail(self, n: int = 500) -> list[dict]:
        """The last n entries, oldest first."""
        if n <= 0:
            return []
        with self._lock:
            lines = list(self._lines)
        return lines[-n:]

    def _write_to_file(self, stamp: str, text: str) -> None:
        """Append one line to today's log. Best-effort: never breaks a
        write(). Caller holds the lock. A failed open is not retried per
        line, it just leaves the file closed until the day rolls over."""
        try:
            day = datetime.now().strftime("%Y%m%d")
            if self._file is not None and self._file_day != day:
                self._file.close()
                self._file = None
            if self._file is None:
                self._log_dir.mkdir(parents=True, exist_ok=True)
                self._file = open(self.log_path, "a", encoding="utf-8")
                self._file_day = day
            self._file.write(f"{stamp} {text}\n")
            self._file.flush()
        except Exception:
            pass

    def close(self) -> None:
        """Release the log file handle on shutdown. A later write() reopens
        it, the same way a day roll-over does."""
        with self._lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None
