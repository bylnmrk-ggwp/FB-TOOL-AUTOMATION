import tkinter as tk
from tkinter import ttk
from datetime import datetime

from src.ui import theme


class LogTab(ttk.Frame):
    MAX_LINES = 2000

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self._line_count = 0
        self._build_ui()

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
        timestamp = datetime.now().strftime("%H:%M:%S")
        tag = "info"
        stripped = message.strip()

        if stripped.startswith("\u2713"):
            tag = "ok"
        elif stripped.startswith("\u2717") or "error" in stripped.lower() or "fail" in stripped.lower():
            tag = "error"

        self.text.config(state="normal")
        self.text.insert("end", f"[{timestamp}] ", "time")
        self.text.insert("end", f"{stripped}\n", tag)
        self.text.see("end")
        self.text.config(state="disabled")

        self._line_count += 1
        if self._line_count > self.MAX_LINES:
            excess = self._line_count - self.MAX_LINES
            self.text.config(state="normal")
            self.text.delete("1.0", f"{excess + 1}.0")
            self.text.config(state="disabled")
            self._line_count = self.MAX_LINES

    def _clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self._line_count = 0
