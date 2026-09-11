import tkinter as tk
from tkinter import ttk
from pathlib import Path

from src.ui import theme
from src.ui import effects
from src.ui.profiles_tab import ProfilesTab
from src.ui.share_tab import ShareTab
from src.ui.queue_tab import QueueTab
from src.ui.log_tab import LogTab
from src.ui.memory_monitor import MemoryMonitorTab
from src.ui.scroll_container import ScrollFrame


class MainWindow(tk.Tk):
    def __init__(self, driver_manager=None):
        # Must precede Tk(): Windows fixes a process's DPI mode at its first
        # window. See theme.enable_dpi_awareness for what it changes.
        theme.enable_dpi_awareness()
        super().__init__()
        self.manager = driver_manager

        # Tk scales point-sized fonts to the screen DPI by itself; pixel
        # geometry it does not, so the window is sized in 96-DPI units and
        # multiplied by the measured ratio to keep its physical size.
        self._dpi = self.winfo_fpixels("1i") / 96.0
        px = self.px

        self.title("FB TOOL AUTOMATION")
        self.minsize(px(1100), px(700))
        self.geometry(f"{px(1280)}x{px(860)}")

        # Resolve best available fonts for this system (Poppins → Segoe UI)
        theme.resolve_fonts(self)

        # Restore saved theme preference
        from src.storage import config_manager as cfg
        saved = cfg.get_setting("ui_theme", "light")
        theme.set_mode(saved)

        self._apply_theme()
        self._build_ui()
        self._start_queue_polling()

    def px(self, n: int) -> int:
        """Scale a 96-DPI pixel measure to the running display."""
        return int(round(n * self._dpi))

    # ── Theme ──────────────────────────────────────────────

    def _apply_theme(self):
        c = theme.get()
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=c["bg"], foreground=c["fg"],
                        font=theme.font("body"))
        style.configure("TFrame", background=c["bg"])
        style.configure("TLabel", background=c["bg"], foreground=c["fg"])

        # ── Buttons ──────────────────────────────────────
        # Ghost by default: a secondary button carries no resting fill or
        # border, so a screen full of them reads as a list of actions rather
        # than a wall of boxes. Only hover and press draw a surface.
        style.configure("TButton", background=c["secondary"],
                        foreground=c["secondary_fg"],
                        borderwidth=1, relief="flat", focusthickness=0,
                        bordercolor=c["border"], lightcolor=c["border"],
                        darkcolor=c["border"],
                        padding=(12, 6))
        style.map("TButton",
                  background=[("pressed", c["btn_pressed"]),
                              ("active", c["btn_hover"]),
                              ("disabled", c["disabled_bg"])],
                  foreground=[("disabled", c["disabled_fg"]),
                              ("active", c["fg"])],
                  bordercolor=[("active", c["secondary_border"]),
                               ("disabled", c["disabled_bg"])],
                  lightcolor=[("active", c["secondary_border"]),
                              ("disabled", c["disabled_bg"])],
                  darkcolor=[("active", c["secondary_border"]),
                             ("disabled", c["disabled_bg"])],
                  relief=[("pressed", "flat"), ("!pressed", "flat")],
                  cursor=[("!disabled", "hand2")])

        style.configure("Accent.TButton", background=c["accent"],
                        foreground="white", borderwidth=0, relief="flat",
                        focusthickness=0, padding=(14, 7))
        style.map("Accent.TButton",
                  background=[("pressed", c["accent_pressed"]),
                              ("active", c["accent_hover"]),
                              ("disabled", c["accent_disabled"])],
                  foreground=[("disabled", c["disabled_fg"])],
                  relief=[("pressed", "flat"), ("!pressed", "flat")],
                  cursor=[("!disabled", "hand2")])

        style.configure("Timeline.TButton", background=c["timeline"],
                        foreground="white", borderwidth=0, relief="flat",
                        focusthickness=0, padding=(14, 7))
        style.map("Timeline.TButton",
                  background=[("pressed", c["timeline_pressed"]),
                              ("active", c["timeline_hover"]),
                              ("disabled", c["timeline_disabled"])],
                  foreground=[("disabled", c["disabled_fg"])],
                  relief=[("pressed", "flat"), ("!pressed", "flat")],
                  cursor=[("!disabled", "hand2")])

        style.configure("Header.TButton", background=c["toolbar_bg"],
                        foreground=c["muted"],
                        borderwidth=0, relief="flat", focusthickness=0,
                        padding=(10, 5))
        style.map("Header.TButton",
                  background=[("pressed", c["header_pressed"]),
                              ("active", c["header_hover"])],
                  foreground=[("active", c["fg"])],
                  cursor=[("!disabled", "hand2")])

        # ── Inputs ───────────────────────────────────────
        style.configure("TEntry", fieldbackground=c["input_bg"],
                        foreground=c["input_fg"], insertcolor=c["input_fg"],
                        bordercolor=c["border"], lightcolor=c["border"],
                        darkcolor=c["border"],
                        borderwidth=1, relief="solid", padding=(8, 5))
        style.map("TEntry",
                  bordercolor=[("focus", c["accent"])],
                  lightcolor=[("focus", c["accent"])],
                  darkcolor=[("focus", c["accent"])],
                  fieldbackground=[("disabled", c["disabled_bg"])])

        style.configure("TCombobox", fieldbackground=c["input_bg"],
                        foreground=c["input_fg"], arrowcolor=c["muted"],
                        bordercolor=c["border"], lightcolor=c["border"],
                        darkcolor=c["border"],
                        borderwidth=1, padding=(6, 4))
        style.map("TCombobox",
                  fieldbackground=[("readonly", c["input_bg"])],
                  bordercolor=[("focus", c["accent"])],
                  lightcolor=[("focus", c["accent"])],
                  darkcolor=[("focus", c["accent"])])


        # ── Shell ────────────────────────────────────────
        # Top bar, rail, drawer and status bar are flat regions separated by
        # fill, never by borders. Section navigation is text: the active
        # section is carried by colour and weight alone, like the tabs were.
        style.configure("TopBar.TFrame", background=c["toolbar_bg"])
        style.configure("Wordmark.TLabel", background=c["toolbar_bg"],
                        foreground=c["heading"],
                        font=theme.font("title", "bold"))
        style.configure("Nav.TButton", background=c["toolbar_bg"],
                        foreground=c["muted"], borderwidth=0, relief="flat",
                        focusthickness=0, font=theme.font("body"),
                        padding=(theme.SPACE["md"], theme.SPACE["sm"]))
        style.map("Nav.TButton",
                  background=[("pressed", c["header_pressed"]),
                              ("active", c["header_hover"])],
                  foreground=[("active", c["fg"])],
                  cursor=[("!disabled", "hand2")])
        style.configure("NavActive.TButton", background=c["toolbar_bg"],
                        foreground=c["accent"], borderwidth=0, relief="flat",
                        focusthickness=0, font=theme.font("body", "bold"),
                        padding=(theme.SPACE["md"], theme.SPACE["sm"]))
        style.map("NavActive.TButton",
                  background=[("pressed", c["toolbar_bg"]),
                              ("active", c["toolbar_bg"])],
                  foreground=[("active", c["accent"])])
        style.configure("Drawer.TFrame", background=c["surface"])
        style.configure("DrawerToggle.TButton", background=c["surface"],
                        foreground=c["muted"], borderwidth=0, relief="flat",
                        focusthickness=0, font=theme.font("small", "bold"),
                        padding=(theme.SPACE["md"], theme.SPACE["xs"]))
        style.map("DrawerToggle.TButton",
                  background=[("pressed", c["border"]),
                              ("active", c["border"])],
                  foreground=[("active", c["fg"])],
                  cursor=[("!disabled", "hand2")])
        style.configure("StatusBar.Horizontal.TProgressbar",
                        troughcolor=c["track"], background=c["accent"],
                        bordercolor=c["track"], lightcolor=c["accent"],
                        darkcolor=c["accent"], borderwidth=0, thickness=6)

        # ── Labels ───────────────────────────────────────
        # Section headings differ from body text by weight, not by size, so a
        # screen of stacked sections keeps one type scale.
        style.configure("Heading.TLabel", font=theme.font("body", "bold"),
                        foreground=c["heading"])
        style.configure("Header.TLabel", font=theme.font("body", "bold"),
                        foreground=c["heading"])
        style.configure("Status.TLabel", foreground=c["status"])
        style.configure("Muted.TLabel", foreground=c["muted"])
        style.configure("StatusDot.TLabel", font=(theme.UI_FONT, 14))
        # Labels placed on a Card.TFrame: a ttk label defaults to the page
        # background, which draws a box of the wrong colour on a card.
        style.configure("CardMuted.TLabel", background=c["card"],
                        foreground=c["muted"])
        style.configure("CardValue.TLabel", background=c["card"],
                        foreground=c["heading"],
                        font=theme.font("display", "bold"))

        # ── Frames ───────────────────────────────────────
        # One boundary per section. A card is separated from the page by its
        # own fill, so it carries no border as well.
        style.configure("Card.TFrame", background=c["card"], relief="flat",
                        borderwidth=0)
        style.configure("StatusBar.TFrame", background=c["status_bg"],
                        relief="flat", borderwidth=0)
        style.configure("StatusBar.TLabel",
                        font=theme.font("small"),
                        background=c["status_bg"], foreground=c["status"])

        # ── Separator / scrollbar / progress ────────────
        style.configure("TSeparator", background=c["border"])

        # ── Paned window (rail | content) ────────────────
        style.configure("TPanedwindow", background=c["bg"])
        style.configure("Sash", sashthickness=8, gripcount=0,
                        background=c["bg"])
        style.configure("SectionTitle.TLabel",
                        font=theme.font("small", "bold"),
                        foreground=c["muted"])

        # clam's scrollbar layout includes two stepper arrows, which is where
        # the blocky look came from - colour alone cannot remove them. Replace
        # the layout with trough + thumb only.
        for orient, side in (("Vertical", "left"), ("Horizontal", "top")):
            try:
                style.layout(f"{orient}.TScrollbar", [
                    (f"{orient}.Scrollbar.trough", {"sticky": "nswe",
                                                    "children": [
                        (f"{orient}.Scrollbar.thumb",
                         {"expand": "1", "sticky": "nswe"}),
                    ]}),
                ])
            except tk.TclError:
                pass
            # clam sizes the whole bar from arrowsize even with the arrows
            # gone from the layout (arrowsize=0 collapses it to 1px), so this
            # is the thumb width, not a leftover.
            style.configure(f"{orient}.TScrollbar", gripcount=0,
                            background=c["scroll_thumb"],
                            troughcolor=c["bg"], bordercolor=c["bg"],
                            lightcolor=c["scroll_thumb"],
                            darkcolor=c["scroll_thumb"],
                            arrowsize=8,
                            borderwidth=0, relief="flat")
            style.map(f"{orient}.TScrollbar",
                      background=[("active", c["scroll_thumb_hover"])],
                      lightcolor=[("active", c["scroll_thumb_hover"])],
                      darkcolor=[("active", c["scroll_thumb_hover"])])

        style.configure("Horizontal.TProgressbar", troughcolor=c["track"],
                        background=c["accent"], bordercolor=c["track"],
                        lightcolor=c["accent"], darkcolor=c["accent"],
                        borderwidth=0)

        # Window background
        self.configure(bg=c["bg"])

    def _toggle_theme(self):
        mode = theme.toggle()
        from src.storage import config_manager as cfg
        cfg.save_setting("ui_theme", mode)
        self._apply_theme()
        self.theme_btn.config(text="Dark" if mode == "light" else "Light")
        self._retheme_tabs()
        self._show_section(self._section)  # nav styles are theme-bound

    def _retheme_tabs(self):
        """Push the active palette into raw-tk widgets in every tab."""
        for tab in (self.profiles_tab, self.queue_tab, self.share_tab,
                    self.memory_tab, self.log_tab, self._rail):
            apply_theme = getattr(tab, "apply_theme", None)
            if callable(apply_theme):
                try:
                    apply_theme(theme.get())
                except Exception:
                    pass

    # ── UI Build ──────────────────────────────────────────────

    SECTIONS = (("queue", "Queue"), ("compose", "Compose"),
                ("monitor", "Monitor"))

    def _build_ui(self):
        S = theme.SPACE
        px = self.px

        # ── Status bar (bottom, packed first so it always owns the strip) ──
        statusbar = ttk.Frame(self, style="StatusBar.TFrame")
        statusbar.pack(side="bottom", fill="x")
        self._sb_left = ttk.Label(statusbar, text="Ready",
                                  style="StatusBar.TLabel")
        self._sb_left.pack(side="left", padx=S["lg"], pady=S["xs"] - 1)
        self._sb_right = ttk.Label(statusbar, text="",
                                   style="StatusBar.TLabel")
        self._sb_right.pack(side="right", padx=S["lg"], pady=S["xs"] - 1)
        # Run progress lives here, not at the bottom of a scroll surface, so
        # it is visible from every section for the whole run. Hidden until a
        # run starts.
        self._sb_progress = ttk.Progressbar(
            statusbar, style="StatusBar.Horizontal.TProgressbar",
            orient="horizontal", mode="determinate", length=px(160))
        self._sb_progress_text = ttk.Label(statusbar, text="",
                                           style="StatusBar.TLabel")
        self._progress_shown = False
        self._ram_text = ""

        # ── Top bar: wordmark · section nav · session actions ─────────────
        topbar = ttk.Frame(self, style="TopBar.TFrame")
        topbar.pack(side="top", fill="x")
        ttk.Label(topbar, text="AutoShare", style="Wordmark.TLabel").pack(
            side="left", padx=(S["lg"], S["xl"]), pady=S["sm"])
        nav = ttk.Frame(topbar, style="TopBar.TFrame")
        nav.pack(side="left")
        self._nav_buttons = {}
        for key, label in self.SECTIONS:
            btn = ttk.Button(nav, text=label, style="Nav.TButton",
                             command=lambda k=key: self._show_section(k))
            btn.pack(side="left")
            self._nav_buttons[key] = btn

        self.theme_btn = ttk.Button(
            topbar, text="Dark" if theme.current == "light" else "Light",
            command=self._toggle_theme, style="Header.TButton")
        self.theme_btn.pack(side="right", padx=(0, S["md"]))
        # Log Out closes every profile's browser mid-run; it does not sit
        # flush against the theme toggle.
        self.logout_btn = ttk.Button(topbar, text="Log Out",
                                     command=self._on_logout,
                                     style="Header.TButton")
        self.logout_btn.pack(side="right", padx=(0, S["lg"]))

        # ── Log drawer (above the status bar, below the body) ─────────────
        # A drawer with a toggle that is always on screen, replacing a pane
        # that could be dragged to zero height with no way to restore it.
        from src.storage import config_manager as cfg
        drawer = ttk.Frame(self, style="Drawer.TFrame")
        drawer.pack(side="bottom", fill="x")
        strip = ttk.Frame(drawer, style="Drawer.TFrame")
        strip.pack(fill="x")
        self._drawer_btn = ttk.Button(strip, style="DrawerToggle.TButton",
                                      command=self._toggle_drawer)
        self._drawer_btn.pack(side="left")
        self._drawer_body = ttk.Frame(drawer, height=px(220))
        self._drawer_body.pack_propagate(False)
        self.log_tab = LogTab(self._drawer_body)
        self.log_tab.pack(fill="both", expand=True)
        self._drawer_open = None
        self._set_drawer(cfg.get_setting("ui_log_open", "1") == "1")

        # ── Body: profiles rail | content ─────────────────────────────────
        self.body = ttk.PanedWindow(self, orient="horizontal")
        self.body.pack(fill="both", expand=True, padx=S["sm"], pady=S["xs"])

        # The rail hosts ProfilesTab as-is for now; Phase B turns it into the
        # selection model every action reads.
        self._rail = ScrollFrame(self.body)
        self.profiles_tab = ProfilesTab(self._rail.interior)
        self.profiles_tab.pack(fill="both", expand=True)
        self.body.add(self._rail, weight=0)

        content = ttk.Frame(self.body)
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)
        self.body.add(content, weight=1)

        # One frame per section, stacked in the same cell and raised.
        self.queue_tab = QueueTab(content)
        self.share_tab = ShareTab(content)
        self.memory_tab = MemoryMonitorTab(content, manager=self.manager)
        self._sections = {"queue": self.queue_tab,
                          "compose": self.share_tab,
                          "monitor": self.memory_tab}
        for frame in self._sections.values():
            frame.grid(row=0, column=0, sticky="nsew")
        self._section = None
        self._show_section("queue")

        # One app-wide mousewheel router serving every scrollable pane
        effects.install_wheel_router(self)

        # Auto-load saved groups from database on startup
        self.after(200, self._load_saved_groups)

        # Rail width: the saved value, else a share of the window. Set once
        # the pane is laid out, since sashpos() clamps to the current size.
        self._rail_done = False
        self.after(120, self._init_rail)
        self.body.bind("<ButtonRelease-1>", self._save_rail_width)

        # Connect tab callbacks to manager methods
        self._connect_callbacks()
        # The shell's RAM readout rides on the monitor's own poll.
        self.memory_tab.set_on_stats(self._on_memory_stats)

        # Raw-tk widgets build with light defaults — sync them with the
        # saved theme immediately (previously only done on toggle, which
        # left white listboxes/text areas when starting in dark mode).
        self._retheme_tabs()

    # ── Shell behaviour ───────────────────────────────────────

    def _show_section(self, key: str):
        self._section = key
        for k, btn in self._nav_buttons.items():
            btn.configure(style="NavActive.TButton" if k == key
                          else "Nav.TButton")
        self._sections[key].tkraise()
        # Per-section refresh, as the tab-change handler used to do.
        try:
            if key == "queue":
                self.queue_tab.refresh_profiles()
            elif key == "monitor":
                self.memory_tab._refresh_now()
        except Exception:
            pass

    def _set_drawer(self, open_: bool):
        if open_ == self._drawer_open:
            return
        self._drawer_open = open_
        if open_:
            self._drawer_body.pack(fill="x")
            self._drawer_btn.configure(text="▾  Log")
        else:
            self._drawer_body.pack_forget()
            self._drawer_btn.configure(text="▸  Log")

    def _toggle_drawer(self):
        self._set_drawer(not self._drawer_open)
        from src.storage import config_manager as cfg
        cfg.save_setting("ui_log_open", "1" if self._drawer_open else "0")

    def _init_rail(self, attempts: int = 0):
        """Place the rail sash once the body has a real width."""
        if self._rail_done:
            return
        w = self.body.winfo_width()
        if w < self.px(500):
            if attempts < 25:  # keep trying for ~3s, then give up gracefully
                self.after(120, lambda: self._init_rail(attempts + 1))
            else:
                self._rail_done = True
            return
        from src.storage import config_manager as cfg
        try:
            saved = int(cfg.get_setting("ui_rail_width", "0"))
        except (TypeError, ValueError):
            saved = 0
        # Phase A hosts the whole ProfilesTab in the rail, and its button
        # grid clips below ~380 (96-DPI) px. The Phase B rail is a plain
        # selection list and narrows this range.
        lo, hi = self.px(380), self.px(620)
        width = saved if lo <= saved <= hi else max(lo, min(hi, w * 30 // 100))
        try:
            self.body.sashpos(0, width)
        except Exception:
            pass
        self._rail_done = True

    def _save_rail_width(self, _event=None):
        if not self._rail_done:
            return
        try:
            pos = self.body.sashpos(0)
        except Exception:
            return
        from src.storage import config_manager as cfg
        cfg.save_setting("ui_rail_width", str(pos))

    def _set_progress(self, done: int, total: int):
        """Drive the status-bar progress bar; hide it when no run is on."""
        show = total > 0 and done < total
        if show:
            self._sb_progress.configure(maximum=total, value=done)
            self._sb_progress_text.configure(text=f"{done}/{total}")
            if not self._progress_shown:
                self._sb_progress_text.pack(side="right",
                                            padx=(0, theme.SPACE["lg"]))
                self._sb_progress.pack(side="right",
                                       padx=(0, theme.SPACE["sm"]))
                self._progress_shown = True
        elif self._progress_shown:
            self._sb_progress.pack_forget()
            self._sb_progress_text.pack_forget()
            self._progress_shown = False

    def _on_memory_stats(self, stats: dict):
        system = stats.get("system_memory", {}) or {}
        total = system.get("total_gb", 0) or 0
        used = system.get("used_gb", 0) or 0
        procs = stats.get("process_count", None)
        if not stats.get("has_psutil") or total <= 0:
            text = ""
        else:
            text = f"RAM {used:.1f}/{total:.1f} GB"
            if isinstance(procs, int):
                text += f"   •   {procs} proc"
        if text != self._ram_text:
            self._ram_text = text
            self._update_status_counts()

    def _connect_callbacks(self):
        """Connect UI callbacks to manager methods."""
        if not self.manager:
            return

        from src.storage import config_manager as cfg
        
        # Share tab
        self.share_tab.set_on_share(self.manager.share)
        self.share_tab.set_on_timeline(self.manager.share_to_timeline)
        self.share_tab.set_on_join_group(self.manager.join_group)
        self.share_tab.set_on_fetch_groups(self.manager.fetch_my_groups_bulk)
        self.share_tab.set_on_load_groups(self._load_saved_groups)
        self.share_tab.set_on_share_selected(self.manager.share_to_groups)
        self.share_tab.set_on_bulk_share(self.manager.share_to_groups_bulk)
        self.share_tab.set_on_post_timeline(self.manager.post_to_timeline)
        self.share_tab.set_on_fetch_one_profile(self.manager.fetch_my_groups)
        # MainWindow owns config access, so it feeds the picker its choices.
        self.share_tab.set_profiles(cfg.list_profiles())

        # Queue tab
        self.queue_tab.set_on_run_queue(self.manager.run_queue)
        self.queue_tab.set_on_watch_url(self.manager.watch_url)
        self.queue_tab.set_on_stop_watch(self.manager.stop_watch)
        
        # Profiles tab
        self.profiles_tab._log_callback = self.log_tab.write
        self.profiles_tab.set_on_launch_profile(self.manager.start_profile)
        self.profiles_tab.set_on_auto_setup(self.manager.auto_setup_profile)
        self.profiles_tab.set_on_auto_setup_all(self.manager.auto_setup_all_profiles)
        self.profiles_tab.set_on_accept_all_pending(self.manager.accept_all_pending_requests)
        self.profiles_tab.set_on_check_login_status(self.manager.check_login_status)

    # ── Queue Polling ─────────────────────────────────────

    def _start_queue_polling(self):
        self._poll_id = None
        self._sheet_watcher = None
        self._poll_queue()

    def start_sheet_sync(self):
        """Keep the account roster current with the Google Sheet.

        Started by app.run(), not here, so verify.py and screenshot builds
        never touch the network. The watcher thread only fetches and parses;
        every database write happens in _poll_queue on this thread.
        """
        if self._sheet_watcher is not None:
            return
        from src.storage.roster_sheet import SheetWatcher
        self._sheet_watcher = SheetWatcher()
        self._sheet_watcher.start()
        self.log_tab.write("Roster sync: watching the Google Sheet "
                           f"(every {self._sheet_watcher.interval:.0f}s)")

    def _drain_sheet_events(self):
        watcher = self._sheet_watcher
        if watcher is None:
            return
        from src.storage import roster_sheet
        while True:
            try:
                kind, payload = watcher.events.get_nowait()
            except Exception:
                return
            if kind == "rows":
                try:
                    inserted, updated = roster_sheet.apply(payload)
                except Exception as e:
                    self.log_tab.write(f"Roster sync failed to apply: {e}")
                    continue
                self.log_tab.write(f"Roster synced from sheet: {inserted} new, "
                                   f"{updated} refreshed ({len(payload)} rows)")
                try:
                    self.profiles_tab.refresh_accounts()
                except Exception:
                    pass
            elif kind == "error":
                self.log_tab.write(f"Roster sync: {payload}")

    def destroy(self):
        """Cancel the pending poll before tearing down.

        _poll_queue reschedules itself every 100ms, so without this a
        callback survives the window and fires into a dead interpreter:
        Tcl reports 'invalid command name "..._poll_queue"' on every exit.
        """
        poll_id = getattr(self, "_poll_id", None)
        if poll_id is not None:
            try:
                self.after_cancel(poll_id)
            except Exception:
                pass
            self._poll_id = None
        watcher = getattr(self, "_sheet_watcher", None)
        if watcher is not None:
            watcher.stop()
        super().destroy()

    def _poll_queue(self):
        if not self.manager:
            self._update_status_counts()
            self._poll_id = self.after(100, self._poll_queue)
            return

        result = self.manager.poll_result()
        while result:
            self._handle_result(result)
            result = self.manager.poll_result()

        self._drain_sheet_events()
        self._update_status_counts()
        self._poll_id = self.after(100, self._poll_queue)

    def _update_status_counts(self):
        """Refresh the profile / queue counters in the status bar."""
        try:
            n_queue = len(self.queue_tab._items)
        except Exception:
            n_queue = 0
        # Profiles reflects what is on screen: with the logged-in-only filter
        # on it is the confirmed set (4), not every registered Brave profile
        # (140). logged_in_count() returns (active, shown) from that same set.
        try:
            n_active, n_profiles = self.queue_tab.logged_in_count()
        except Exception:
            n_active = n_profiles = 0
        text = (f"Profiles: {n_profiles}   •   Active: {n_active}"
                f"   •   Queue: {n_queue}")
        if self._ram_text:
            text += f"   •   {self._ram_text}"
        if self._sb_right.cget("text") != text:
            self._sb_right.config(text=text)
        # Profiles and Queue now share a tab — refresh the queue's
        # status dot grid when the profile count changes (add/delete)
        # instead of waiting for a tab switch that no longer happens.
        if getattr(self, "_last_profile_count", None) != n_profiles:
            self._last_profile_count = n_profiles
            try:
                self.queue_tab.refresh_profiles()
            except Exception:
                pass

    def _load_saved_groups(self):
        """Load groups from SQLite database and display in the share tab."""
        try:
            from src.storage import database as db
            groups = db.get_profile_groups()
            self.share_tab.set_groups_list(groups)
            self.share_tab.set_groups_status(f"{len(groups)} group(s) loaded from database")
            self.log_tab.write(f"Loaded {len(groups)} group(s) from database")
        except Exception as e:
            self.share_tab.set_groups_status(f"Load failed: {e}")
            self.log_tab.write(f"Failed to load groups from database: {e}")

    def _set_activity(self, text: str):
        """Update the live activity line in the status bar (left side)."""
        text = text.strip()
        if len(text) > 110:
            text = text[:107] + "..."
        if self._sb_left.cget("text") != text:
            self._sb_left.config(text=text)

    def _handle_result(self, result: dict):
        rtype = result.get("type")
        ok = result.get("ok", False)

        # Keep "what is the app doing" visible on either tab
        if isinstance(rtype, str) and "progress" in rtype:
            msg = result.get("message", "")
            pname = result.get("profile_name", "")
            live = f"{pname}: {msg}" if pname and msg else (msg or pname)
            if live:
                self._set_activity(live)

        if rtype == "login_result":
            if ok:
                profile_name = result.get("profile_name", "")
                needs_login = result.get("needs_login", False)

                # Update profile status indicators in Queue tab
                self.queue_tab.update_profile_status(profile_name, not needs_login)

                if needs_login:
                    self.profiles_tab.set_status(
                        f"Profile '{profile_name}' needs login", logged_in=False)
                    self.log_tab.write(f"Profile '{profile_name}' — not logged in")
                else:
                    self.profiles_tab.set_status(
                        f"Logged in as '{profile_name}'", logged_in=True)
                    self.share_tab.set_status("Ready to share")
                    self.share_tab.set_share_enabled(
                        bool(self.share_tab.post_url and self.share_tab.group_name))
                    self.log_tab.write(f"Profile '{profile_name}' ready")
            else:
                self.profiles_tab.set_status("Profile setup failed", logged_in=False)
                err = result.get("error", "Unknown error")
                self.log_tab.write(f"Profile error: {err}")

        elif rtype == "share_result":
            # During bulk share, just log — don't toggle buttons
            is_bulk_item = result.get("total", 0) > 1
            group = result.get("group_name", self.share_tab.group_name)

            if ok:
                msg = result.get("message", "Shared successfully")
                self.log_tab.write(f"{msg}")
                if not is_bulk_item:
                    self.share_tab.add_recent_share(True, group, msg)
                    self.share_tab.clear_group_name()
                    self.share_tab.set_share_enabled(False)
                    self.profiles_tab.set_status("Shared successfully", logged_in=True)
            else:
                err = result.get("error", result.get("message", "Unknown error"))
                self.log_tab.write(f"Share failed: {err}")
                if not is_bulk_item:
                    self.share_tab.add_recent_share(False, group, err)

            if not is_bulk_item:
                self.share_tab.set_share_enabled(True)
                self.share_tab.set_status("Ready" if ok else "Failed")

        elif rtype == "share_bulk_result":
            self.share_tab.share_selected_btn.config(state="normal")
            self.share_tab.bulk_share_btn.config(state="normal")
            msg = result.get("message", "Done")
            self.share_tab.set_status(msg)
            self.log_tab.write(f"\n{'='*50}")
            self.log_tab.write(msg)
            self.log_tab.write(f"{'='*50}")

        elif rtype == "share_bulk_profile_progress":
            pname = result.get("profile_name", "")
            msg = result.get("message", "")
            ok = result.get("ok", False)
            icon = "OK" if ok else "FAIL"
            self.log_tab.write(f"{icon} {msg}")

        elif rtype == "share_bulk_profile_result":
            pname = result.get("profile_name", "")
            msg = result.get("message", "")
            ok = result.get("ok", False)
            icon = "OK" if ok else "FAIL"
            self.log_tab.write(f"{icon} {pname}: {msg}")

        elif rtype == "share_progress":
            msg = result.get("message", "")
            current = result.get("current", 0)
            total = result.get("total", 1)
            self.share_tab.set_status(f"Sharing {current}/{total}...")
            self.log_tab.write(msg)

        elif rtype == "join_group_result":
            self.share_tab.join_btn.config(state="normal")
            if ok:
                msg = result.get("message", "Joined successfully")
                self.share_tab.set_status(msg)
                self.log_tab.write(f"{msg}")
            else:
                err = result.get("error", result.get("message", "Unknown error"))
                self.share_tab.set_status(f"Failed: {err}")
                self.log_tab.write(f"Join group failed: {err}")

        elif rtype == "join_group_progress":
            current = result.get("current", 0)
            total = result.get("total", 1)
            msg = result.get("message", "")
            pname = result.get("profile_name", "")
            self.share_tab.update_join_progress(current, total, f"{pname}: {msg}")
            self.log_tab.write(msg)

        elif rtype == "join_group_profile_progress":
            pname = result.get("profile_name", "")
            msg = result.get("message", "")
            ok = result.get("ok", False)
            icon = "\u2713" if ok else "\u2717"
            self.log_tab.write(f"{icon} {msg}")

        elif rtype == "join_group_item_result":
            current = result.get("current", 0)
            total = result.get("total", 1)
            url = result.get("url", "")
            pname = result.get("profile_name", "")
            msg = result.get("message", result.get("error", ""))
            icon = "\u2713" if ok else "\u2717"
            self.share_tab.update_join_progress(current, total,
                                                f"{icon} {current}/{total}: {msg}")
            self.log_tab.write(f"{icon} {pname} [{current}/{total}] {url}: {msg}")

        elif rtype == "join_group_bulk_result":
            self.share_tab.join_btn.config(state="normal")
            msg = result.get("message", "Done")
            self.share_tab.set_status(msg)
            self.share_tab.update_join_progress(0, 0, msg)
            self.log_tab.write(f"\n{'='*50}")
            self.log_tab.write(msg)
            # Log per-profile summary
            for pr in result.get("profile_results", []):
                pname = pr.get("profile_name", "?")
                if pr.get("ok"):
                    s = pr.get("success", 0)
                    f = pr.get("failed", 0)
                    sk = pr.get("skipped", 0)
                    parts = []
                    if s:
                        parts.append(f"{s} joined")
                    if f:
                        parts.append(f"{f} failed")
                    if sk:
                        parts.append(f"{sk} skipped")
                    self.log_tab.write(f"  {pname}: {', '.join(parts) if parts else 'done'}")
                else:
                    err = pr.get("error", "skipped")
                    self.log_tab.write(f"  {pname}: {err}")
            self.log_tab.write(f"{'='*50}")

        elif rtype == "fetch_groups_bulk_result":
            self.share_tab.fetch_groups_btn.config(state="normal")
            if ok:
                groups = result.get("groups", [])
                total = result.get("total_groups", len(groups))
                self.share_tab.set_groups_list(groups)
                self.share_tab.set_groups_status(f"{total} unique group(s) found")
                self.share_tab.set_status(f"Found {total} group(s)")
                self.log_tab.write(f"\n{'='*50}")
                self.log_tab.write(f"My Groups — {total} unique group(s):")
                for g in groups:
                    profiles = ", ".join(g.get("profiles", []))
                    self.log_tab.write(f"  {g['name']:<40} [{profiles}]")
                self.log_tab.write(f"{'='*50}")
            else:
                err = result.get("error", "Unknown error")
                self.share_tab.set_groups_status(f"Failed: {err}")
                self.share_tab.set_status(f"Fetch groups failed: {err}")
                self.log_tab.write(f"Fetch groups failed: {err}")

        elif rtype == "fetch_groups_profile_progress":
            msg = result.get("message", "")
            self.log_tab.write(msg)

        elif rtype == "batch_progress":
            current = result.get("current", 0)
            total = result.get("total", 1)
            message = result.get("message", "")
            self.queue_tab.update_progress(current, total)
            self._set_progress(current, total)
            self.queue_tab.set_status(message)
            self.log_tab.write(message)

        elif rtype == "batch_item_result":
            pname = result.get("profile_name", "")
            msg = result.get("message", "")
            is_rate_limited = result.get("rate_limited", False)
            needs_login = result.get("needs_login", False)
            if is_rate_limited:
                icon = "\u26a0"  # warning triangle
                self.log_tab.write(f"{icon} {pname}: {msg}")
                self.profiles_tab.mark_rate_limited(pname)
                self.queue_tab.mark_profile_rate_limited(pname)
            elif needs_login:
                # Detected logged-out mid-batch (e.g. 'See more on Facebook' overlay)
                self.log_tab.write(f"\u2717 {pname}: {msg}")
                self.profiles_tab.mark_login_status(pname, False)
                self.queue_tab.update_profile_status(pname, False)
            else:
                icon = "\u2713" if ok else "\u2717"
                self.log_tab.write(f"{icon} {pname}: {msg}")

        elif rtype == "login_scan_progress":
            pname = result.get("profile_name", "")
            msg = result.get("message", "")
            logged_in = result.get("logged_in")
            if pname and logged_in is not None:
                self.queue_tab.update_profile_status(pname, logged_in)
                self.profiles_tab.mark_login_status(pname, logged_in)
            self.log_tab.write(msg)

        elif rtype == "login_scan_result":
            self.profiles_tab.set_check_login_enabled(True)
            if not result.get("ok", False):
                err = result.get("error", "Unknown error")
                self.profiles_tab.set_status(f"Login check failed: {err}", logged_in=False)
                self.log_tab.write(f"Login check failed: {err}")
            else:
                results = result.get("results", [])
                removed_profiles = result.get("removed_profiles", [])
                # The scan rewrote account statuses: the "logged in only"
                # filter and the active count must re-read them.
                self.profiles_tab.refresh_profiles()
                self.queue_tab.refresh_profiles()
                if removed_profiles:
                    self.log_tab.write(
                        f"Auto-removed {len(removed_profiles)} disabled profile(s): "
                        + ", ".join(removed_profiles))
                logged_in_count = result.get("logged_in_count", 0)
                total = result.get("total", 0)
                needs = [r.get("profile_name") for r in results
                         if not r.get("logged_in")]
                needs = [n for n in needs if n]
                if needs:
                    names = ", ".join(needs)
                    if len(names) > 90:
                        names = names[:87] + "..."
                    self.profiles_tab.set_status(
                        f"⚠️ {len(needs)} profile(s) need login: {names}",
                        logged_in=False)
                    self.profiles_tab.set_auto_setup_status(
                        f"❌ Need re-login ({len(needs)}): {names[:90]}")
                    self.log_tab.write(
                        f"Login check done — {logged_in_count}/{total} logged in; "
                        f"need re-login: {names}")
                else:
                    self.profiles_tab.set_status(
                        f"✅ All {total} profile(s) logged in", logged_in=True)
                    self.profiles_tab.set_auto_setup_status(
                        f"✅ All {total} profile(s) logged in")
                    self.log_tab.write(
                        f"Login check done — {logged_in_count}/{total} logged in")

        elif rtype == "auto_setup_result":
            profile_name = result.get("profile_name", "")
            if ok:
                setup_result = result.get("result", {})
                fb = setup_result.get("friends_before", 0)
                fa = setup_result.get("friends_added", 0)
                pic = setup_result.get("profile_pic_set", False) or setup_result.get("had_profile_pic", False)
                bio_ok = setup_result.get("bio_updated", False) or setup_result.get("had_bio", False)
                pins = setup_result.get("pinterest_images_downloaded", 0)

                self.profiles_tab.set_auto_setup_status(f"Done — {profile_name}: +{fa} friends")
                self.profiles_tab.set_auto_setup_enabled(True)
                self.profiles_tab.set_launch_enabled(True)

                msg = (f"✅ Auto-setup complete for '{profile_name}'\n"
                       f"   Friends: {fb} → +{fa} added\n"
                       f"   Profile pic: {'✅' if pic else '❌'}\n"
                       f"   Bio: {'✅' if bio_ok else '❌'}\n"
                       f"   Pinterest images: {pins}")
                self.log_tab.write(msg)
            else:
                err = result.get("error", "Unknown error")
                needs_login = result.get("needs_login", False)
                if needs_login:
                    self.profiles_tab.set_auto_setup_status(
                        f"❌ '{profile_name}' not logged in — log in first")
                else:
                    self.profiles_tab.set_auto_setup_status(f"❌ Auto-setup failed: {err}")
                self.profiles_tab.set_auto_setup_enabled(True)
                self.profiles_tab.set_launch_enabled(True)
                self.log_tab.write(f"❌ Auto-setup failed for '{profile_name}': {err}")

        elif rtype == "auto_setup_images_preview":
            profile_name = result.get("profile_name", "")
            images = result.get("images", [])
            needs_pic = result.get("needs_pic", True)
            self.log_tab.write(f"🖼️ Showing image preview for '{profile_name}' — {len(images)} image(s)")

            # Show the image picker dialog on the UI thread
            from src.ui.image_picker import ImagePickerDialog
            dialog = ImagePickerDialog(
                self, profile_name, images,
                needs_pic=needs_pic,
            )
            # This blocks the UI thread until the dialog is closed
            picker_result = dialog.show()

            if picker_result:
                self.manager.send_user_response(picker_result)
                if picker_result.get("cancel"):
                    self.log_tab.write(f"  User cancelled image selection — using defaults")
                else:
                    pp = picker_result.get("profile_pic") or "(default)"
                    self.log_tab.write(f"  Selected — {Path(pp).name if pp != '(default)' else pp}")
            else:
                # Dialog was closed without result — send cancel
                self.manager.send_user_response({"cancel": True})

        elif rtype == "auto_setup_all_progress":
            current = result.get("current", 0)
            total = result.get("total", 0)
            pname = result.get("profile_name", "")
            msg = result.get("message", "")
            ok = result.get("ok", False)

            icon = "✅" if ok else "❌"
            log_msg = f"[{current}/{total}] {icon} {msg}"
            self.log_tab.write(log_msg)

            if pname:
                self.profiles_tab.set_auto_setup_status(
                    f"[{current}/{total}] {icon} {pname}")

        elif rtype == "auto_setup_all_result":
            total = result.get("total", 0)
            success_count = result.get("success_count", 0)
            ok = result.get("ok", False)

            if ok:
                self.profiles_tab.set_auto_setup_status(
                    f"Done — {success_count}/{total} profile(s) successful")
                self.log_tab.write(
                    f"✅ Auto-setup ALL complete: {success_count}/{total} successful")
            else:
                err = result.get("error", "Unknown error")
                self.profiles_tab.set_auto_setup_status(f"❌ {err}")
                self.log_tab.write(f"❌ Auto-setup ALL failed: {err}")

            self.profiles_tab.set_auto_setup_enabled(True)
            self.profiles_tab.set_launch_enabled(True)

        elif rtype == "batch_result":
            total = result.get("total", 0)
            self.queue_tab.set_running(False)
            self.queue_tab.update_progress(total, total)
            self._set_progress(total, total)
            self.queue_tab.set_status(f"Done — {total} item(s) processed")
            self.queue_tab.clear_all()
            self.log_tab.write(f"Batch complete: {total} item(s) processed")
            self._set_activity("Ready")

        elif rtype == "fetch_groups_result":
            self.share_tab.set_fetch_one_enabled(True)
            pname = result.get("profile_name", "")
            if ok:
                groups = result.get("groups", [])
                count = result.get("count", len(groups))
                self.share_tab.set_groups_list(groups)
                self.share_tab.set_groups_status(
                    f"{count} group(s) for '{pname}'")
                self.share_tab.set_status(f"Found {count} group(s)")
                self.log_tab.write(f"\n{'='*50}")
                self.log_tab.write(f"Groups for '{pname}' — {count}:")
                for g in groups:
                    self.log_tab.write(f"  {g.get('name', '?')}")
                self.log_tab.write(f"{'='*50}")
            else:
                err = result.get("error", "Unknown error")
                self.share_tab.set_groups_status(f"Failed: {err}")
                self.share_tab.set_status(f"Fetch groups failed: {err}")
                self.log_tab.write(f"Fetch groups failed: {err}")

        elif rtype == "logout_result":
            self.logout_btn.config(state="normal")
            self._set_activity("Ready")
            self.log_tab.write("Logged out — browser closed, credentials cleared.")
            self.share_tab.set_status("Logged out")

    # ── App lifecycle ─────────────────────────────────────

    def _on_logout(self):
        """Confirm, then close the browser and clear saved credentials."""
        from tkinter import messagebox
        if not messagebox.askyesno(
                "Confirm Logout",
                "Close the browser and clear saved credentials?",
                parent=self):
            return
        self.logout_btn.config(state="disabled")
        self._set_activity("Logging out...")
        if self.manager:
            self.manager.logout()

