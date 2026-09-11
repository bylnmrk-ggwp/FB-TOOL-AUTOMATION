"""Memory Monitor tab — live system + browser memory dashboard.

Polls DriverManager.get_memory_stats() once per second and renders:

  - System RAM usage (used / total + level-colored progress bar)
  - Total browser (Brave/Chrome) memory in MB
  - Browser process count
  - Peak browser memory observed since launch
  - Per-profile estimated memory breakdown

Flat design only — solid colors pulled from theme.py. No gradients.
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime

from src.ui import theme
from src.ui.effects import attach_listbox_hover


class MemoryMonitorTab(ttk.Frame):
    """Live memory dashboard for the main window."""

    POLL_MS = 1000

    def __init__(self, parent, manager=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.manager = manager
        self._after_id = None
        self._paused = False
        # The shell reads the same stats for its status-bar readout, so one
        # psutil scan per second serves both surfaces.
        self._on_stats_cb = None
        self._build_ui()
        self.apply_theme(theme.get())
        self._schedule_poll()

    # ── UI construction ─────────────────────────────────

    def _build_ui(self):
        # Memory-level progress bar styles (flat, re-applied on theme change)
        self._configure_bar_styles(theme.get())

        # Header row
        header = ttk.Frame(self)
        header.pack(fill="x", padx=12, pady=(10, 4))
        ttk.Label(header, text="Memory Monitor",
                  style="Header.TLabel").pack(side="left")
        self.pause_btn = ttk.Button(header, text="Pause", width=8,
                                    command=self._toggle_pause)
        self.pause_btn.pack(side="right")
        ttk.Button(header, text="Refresh Now",
                   command=self._refresh_now).pack(side="right", padx=(0, 8))

        # Warning banner (hidden unless psutil is missing)
        self._warn_frame = tk.Frame(self, bd=0)
        self._warn_label = tk.Label(self._warn_frame, anchor="w",
                                    font=(theme.UI_FONT, 9), padx=12, pady=6)
        self._warn_label.pack(fill="x")

        # ── Stat cards ─────────────────────────────────
        self._cards_frame = ttk.Frame(self)
        self._cards_frame.pack(fill="x", padx=12, pady=(4, 0))
        for i in range(4):
            self._cards_frame.columnconfigure(i, weight=1)

        self._ram_value, self._ram_sub = self._make_card(
            self._cards_frame, 0, "System RAM")
        self._browser_value, self._browser_sub = self._make_card(
            self._cards_frame, 1, "Browser Memory")
        self._proc_value, self._proc_sub = self._make_card(
            self._cards_frame, 2, "Processes")
        self._peak_value, self._peak_sub = self._make_card(
            self._cards_frame, 3, "Peak Browser")

        # RAM progress bar (inside the System RAM card)
        self._ram_bar = ttk.Progressbar(
            self._ram_card, style="MemOK.Horizontal.TProgressbar",
            maximum=100, value=0)
        self._ram_bar.pack(fill="x", pady=(6, 2))

        # ── Per-profile breakdown ───────────────────────
        list_card = ttk.Frame(self, style="Card.TFrame", padding=10)
        list_card.pack(fill="both", expand=True, padx=12, pady=(8, 4))
        # The card fill is an explicit override, so apply_theme must
        # re-apply it: the style alone would leave a page-coloured box on
        # the card after a theme switch.
        self._list_heading = ttk.Label(list_card, text="Per-Profile Memory",
                                       style="Heading.TLabel",
                                       background=theme.get()["card"])
        self._list_heading.pack(anchor="w")

        list_wrap = ttk.Frame(list_card)
        list_wrap.pack(fill="both", expand=True, pady=(6, 0))
        scroll = ttk.Scrollbar(list_wrap, orient="vertical")
        self._profile_list = tk.Listbox(
            list_wrap, yscrollcommand=scroll.set, borderwidth=0,
            highlightthickness=1, activestyle="none",
            font=(theme.MONO_FONT, 9))
        scroll.config(command=self._profile_list.yview)
        scroll.pack(side="right", fill="y")
        self._profile_list.pack(side="left", fill="both", expand=True)
        self._clear_profile_hover = attach_listbox_hover(self._profile_list)

        # Footer status
        self._footer = ttk.Label(self, text="Waiting for data…",
                                 style="Muted.TLabel")
        self._footer.pack(anchor="w", padx=14, pady=(0, 8))

    def _make_card(self, parent, col, title):
        """Create a flat stat card; returns (value_label, sub_label)."""
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=4)
        ttk.Label(card, text=title, style="CardMuted.TLabel").pack(anchor="w")
        value = ttk.Label(card, text="—", style="CardValue.TLabel")
        value.pack(anchor="w", pady=(4, 0))
        sub = ttk.Label(card, text="", style="CardMuted.TLabel")
        sub.pack(anchor="w")
        # Keep a handle on the RAM card so the progress bar can be placed in it
        if col == 0:
            self._ram_card = card
        return value, sub

    # ── Theme ──────────────────────────────────────────

    def _configure_bar_styles(self, colors: dict):
        style = ttk.Style(self)
        for name, key in (("MemOK", "success"),
                          ("MemWarn", "warning"),
                          ("MemBad", "error")):
            style.configure(f"{name}.Horizontal.TProgressbar",
                            troughcolor=colors["track"],
                            background=colors[key],
                            bordercolor=colors["track"],
                            lightcolor=colors[key],
                            darkcolor=colors[key],
                            borderwidth=0)

    def apply_theme(self, colors: dict):
        self._configure_bar_styles(colors)
        # Warning banner: warning-coloured text on a quiet surface, not a
        # full-bleed amber slab.
        self._warn_frame.configure(bg=colors["surface"])
        self._warn_label.configure(bg=colors["surface"], fg=colors["warning"])
        self._list_heading.configure(background=colors["card"])
        # Profile list
        self._profile_list.configure(
            bg=colors["list_bg"], fg=colors["list_fg"],
            highlightbackground=colors["border"],
            selectbackground=colors["list_select_bg"],
            selectforeground=colors["list_select_fg"])
        if hasattr(self, "_clear_profile_hover"):
            self._clear_profile_hover()

    # ── Polling ────────────────────────────────────────

    def _schedule_poll(self):
        if self._paused:
            return
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        self._after_id = self.after(self.POLL_MS, self._poll)

    def _poll(self):
        self._after_id = None
        if not self._paused:
            self._refresh()
        self._schedule_poll()

    def _refresh_now(self):
        self._refresh()

    def _toggle_pause(self):
        self._paused = not self._paused
        self.pause_btn.config(text="Resume" if self._paused else "Pause")
        if not self._paused:
            self._refresh()
            self._schedule_poll()

    def destroy(self):
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        super().destroy()

    # ── Data rendering ─────────────────────────────────

    def set_on_stats(self, callback):
        """Receive every stats dict this monitor renders."""
        self._on_stats_cb = callback

    def _refresh(self):
        if self.manager is None:
            self._show_unavailable("Driver manager not connected")
            return
        try:
            stats = self.manager.get_memory_stats()
        except Exception:
            self._show_unavailable("Could not read memory stats")
            return
        self._render(stats)
        if self._on_stats_cb:
            try:
                self._on_stats_cb(stats)
            except Exception:
                pass

    def _render(self, stats: dict):
        system = stats.get("system_memory", {}) or {}
        has_psutil = stats.get("has_psutil", False)

        total_gb = system.get("total_gb", 0) or 0
        used_gb = system.get("used_gb", 0) or 0
        percent = system.get("percent", 0) or 0

        # ── System RAM ──────────────────────────────
        if has_psutil and total_gb > 0:
            self._ram_value.config(text=f"{used_gb:.1f} / {total_gb:.1f} GB")
            self._ram_sub.config(text=f"{percent:.0f}% used")
            self._ram_bar.config(value=min(percent, 100))
            bar_style = "MemOK.Horizontal.TProgressbar"
            if percent >= 90:
                bar_style = "MemBad.Horizontal.TProgressbar"
            elif percent >= 70:
                bar_style = "MemWarn.Horizontal.TProgressbar"
            self._ram_bar.config(style=bar_style)
        else:
            self._ram_value.config(text="—")
            self._ram_sub.config(text="psutil not installed" if not has_psutil
                                 else "no data")
            self._ram_bar.config(value=0)

        # ── Browser memory / processes / peak ────────
        browser_mb = stats.get("browser_mb", 0) or 0
        self._browser_value.config(
            text=f"{browser_mb:,.1f} MB" if has_psutil else "—")
        self._browser_sub.config(text="total browser RSS" if has_psutil
                                 else "requires psutil")

        proc_count = stats.get("process_count", 0) or 0
        self._proc_value.config(text=str(proc_count) if has_psutil else "—")
        self._proc_sub.config(text="browser processes" if has_psutil
                              else "requires psutil")

        peak = stats.get("peak_browser_mb", 0) or 0
        self._peak_value.config(text=f"{peak:,.1f} MB" if has_psutil else "—")
        self._peak_sub.config(text="peak since launch" if has_psutil
                              else "requires psutil")

        # ── Warning banner ───────────────────────────
        if not has_psutil:
            self._show_warning(
                "psutil not installed — install with:  pip install psutil")
        else:
            self._hide_warning()

        # ── Per-profile breakdown ─────────────────────
        if hasattr(self, "_clear_profile_hover"):
            self._clear_profile_hover()
        self._profile_list.delete(0, "end")
        profile_memory = stats.get("profile_memory", {}) or {}
        if profile_memory:
            for name, mb in sorted(profile_memory.items(),
                                   key=lambda kv: kv[1], reverse=True):
                self._profile_list.insert("end", f"{name:<22} {mb:>10.1f} MB")
        else:
            self._profile_list.insert("end", "  No active browser profiles")

        # ── Footer ────────────────────────────────────
        batch = "  •  batch running" if stats.get("batch_running") else ""
        ts = datetime.now().strftime("%H:%M:%S")
        self._footer.config(text=f"Updated {ts}{batch}")

    def _show_unavailable(self, message: str):
        for value in (self._ram_value, self._browser_value,
                      self._proc_value, self._peak_value):
            value.config(text="—")
        self._ram_bar.config(value=0)
        self._profile_list.delete(0, "end")
        self._profile_list.insert("end", "  —")
        self._footer.config(text=message)
        if self.manager is None:
            self._show_warning("Driver manager not connected — memory data unavailable")
        else:
            self._hide_warning()

    def _show_warning(self, text: str):
        self._warn_label.config(text=f"⚠️  {text}")
        if not self._warn_frame.winfo_ismapped():
            self._warn_frame.pack(fill="x", padx=12, pady=(6, 0),
                                  before=self._cards_frame)

    def _hide_warning(self):
        if self._warn_frame.winfo_ismapped():
            self._warn_frame.pack_forget()
