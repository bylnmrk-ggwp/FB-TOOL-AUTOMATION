import queue
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from pathlib import Path

from src.ui import theme


class LogTab(ttk.Frame):
    MAX_LINES = 2000
    # How often the main thread flushes queued log lines into the widget.
    RENDER_MS = 50

    # The widget keeps MAX_LINES and dies with the app, so anything worth
    # reading after the fact - which page stalled, what the watch heartbeat
    # said at 00:29 - was unrecoverable. Every line now also lands here, one
    # file per day so the set prunes itself by date rather than by size.
    LOG_DIR = Path.home() / ".autoshare" / "logs"

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._line_count = 0
        self._file = None
        self._file_day = None
        self._file_lock = threading.Lock()
        # The manager logs from its worker thread, and Tk is not thread-safe,
        # so write() hands each line to this queue and the main thread renders
        # it in _drain_log. Nothing off the main thread ever touches the Text.
        self._render_queue: queue.Queue = queue.Queue()
        self._drain_after = None
        self._build_ui()
        self._drain_after = self.after(self.RENDER_MS, self._drain_log)

    @property
    def log_path(self) -> Path:
        """Today's log file, whether or not it has been opened yet."""
        return self.LOG_DIR / f"app-{datetime.now():%Y%m%d}.log"

    def _write_to_file(self, stamp: str, message: str):
        """Append one line to today's log. Best-effort: never breaks the UI.

        The manager calls write() from its worker thread, so the handle is
        guarded; a failed open is not retried per line, it just leaves the
        file closed until the day rolls over.
        """
        try:
            with self._file_lock:
                day = datetime.now().strftime("%Y%m%d")
                if self._file is not None and self._file_day != day:
                    self._file.close()
                    self._file = None
                if self._file is None:
                    self.LOG_DIR.mkdir(parents=True, exist_ok=True)
                    self._file = open(self.log_path, "a", encoding="utf-8")
                    self._file_day = day
                self._file.write(f"{stamp} {message}\n")
                self._file.flush()
        except Exception:
            pass

    def close_log_file(self):
        """Release the log file handle on shutdown."""
        with self._file_lock:
            if self._file is not None:
                try:
                    self._file.close()
                except Exception:
                    pass
                self._file = None

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        header_frame = ttk.Frame(self)
        header_frame.pack(fill="x", padx=12, pady=(10, 0))

        ttk.Label(header_frame, text="Log Output",
                  style="Header.TLabel").pack(side="left")

        ttk.Button(header_frame, text="Clear Log",
                   command=self._clear).pack(side="right")

        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True, padx=12, pady=(4, 10))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(text_frame, orient="vertical")
        self.text = tk.Text(
            text_frame, yscrollcommand=scrollbar.set,
            state="disabled", wrap="word",
            font=(theme.MONO_FONT, 10), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white", borderwidth=0,
            padx=10, pady=10)
        scrollbar.config(command=self.text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.text.grid(row=0, column=0, sticky="nsew")

        self.text.tag_config("time", foreground="#6a9955")
        self.text.tag_config("ok", foreground="#4ec9b0")
        self.text.tag_config("error", foreground="#f44747")
        self.text.tag_config("info", foreground="#d4d4d4")

    def apply_theme(self, colors: dict):
        """Re-theme the log console — stays dark in both modes for readability."""
        if theme.current == "dark":
            self.text.configure(bg="#1e1e1e", fg="#d4d4d4")
            self.text.tag_config("info", foreground="#d4d4d4")
        else:
            self.text.configure(bg="#ffffff", fg="#1f2937")
            self.text.tag_config("info", foreground="#374151")

    def write(self, message: str):
        """Record one log line. Safe from any thread.

        Called from the manager's worker thread as well as the main one, so it
        must not touch Tk: it writes the file (its own lock) and queues the
        line. _drain_log renders it on the main thread. Doing the Tk work here
        was a cross-thread call that crashed at shutdown - "main thread is not
        in main loop" - when the worker logged after mainloop() had returned.
        """
        now = datetime.now()
        timestamp = now.strftime("%H:%M:%S")
        stripped = message.strip()

        # To disk first: the widget trims itself and the file is the record
        # that survives the session.
        self._write_to_file(now.strftime("%Y-%m-%d %H:%M:%S"), stripped)

        tag = "info"
        if stripped.startswith("\u2713"):
            tag = "ok"
        elif stripped.startswith("\u2717") or "error" in stripped.lower() or "fail" in stripped.lower():
            tag = "error"

        self._render_queue.put((timestamp, stripped, tag))

    def _drain_log(self):
        """Flush queued log lines into the Text. Main thread only.

        The one place the Text is touched after construction, so every render
        happens on the thread that owns the Tcl interpreter. Stops rescheduling
        once the widget is gone (app shutting down); the file still has the
        record.
        """
        pending = []
        while True:
            try:
                pending.append(self._render_queue.get_nowait())
            except queue.Empty:
                break
        try:
            if pending:
                self.text.config(state="normal")
                for timestamp, stripped, tag in pending:
                    self.text.insert("end", f"[{timestamp}] ", "time")
                    self.text.insert("end", f"{stripped}\n", tag)
                    self._line_count += 1
                if self._line_count > self.MAX_LINES:
                    excess = self._line_count - self.MAX_LINES
                    self.text.delete("1.0", f"{excess + 1}.0")
                    self._line_count = self.MAX_LINES
                self.text.see("end")
                self.text.config(state="disabled")
        except tk.TclError:
            self._drain_after = None
            return
        self._drain_after = self.after(self.RENDER_MS, self._drain_log)

    def destroy(self):
        """Cancel the drain loop before teardown so no callback fires into a
        dead widget."""
        after = getattr(self, "_drain_after", None)
        if after is not None:
            try:
                self.after_cancel(after)
            except Exception:
                pass
            self._drain_after = None
        super().destroy()

    def _clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self._line_count = 0
