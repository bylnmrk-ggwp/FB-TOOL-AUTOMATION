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
        super().__init__()
        self.manager = driver_manager

        self.title("FB TOOL AUTOMATION")
        self.minsize(1100, 700)
        self.geometry("1280x860")

        # Resolve best available fonts for this system (Poppins → Segoe UI)
        theme.resolve_fonts(self)

        # Restore saved theme preference
        from src.storage import config_manager as cfg
        saved = cfg.get_setting("ui_theme", "light")
        theme.set_mode(saved)

        self._apply_theme()
        self._build_ui()
        self._start_queue_polling()

    # ── Theme ──────────────────────────────────────────────

    def _apply_theme(self):
        c = theme.get()
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=c["bg"], foreground=c["fg"],
                        font=(theme.UI_FONT, 10))
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

        style.configure("TSpinbox", fieldbackground=c["input_bg"],
                        foreground=c["input_fg"], arrowcolor=c["muted"],
                        buttonbackground=c["input_bg"],
                        bordercolor=c["border"], lightcolor=c["border"],
                        darkcolor=c["border"],
                        borderwidth=1, padding=(6, 4))
        style.map("TSpinbox",
                  bordercolor=[("focus", c["accent"])],
                  lightcolor=[("focus", c["accent"])],
                  darkcolor=[("focus", c["accent"])])

        # ── Notebook tabs ────────────────────────────────
        # Tabs read as text, not as boxes: clam's default tab layout draws a
        # raised border on every state, so the border element is dropped from
        # the layout and selection is carried by colour and weight alone.
        style.configure("TNotebook", background=c["bg"], borderwidth=0,
                        tabmargins=(8, 4, 8, 0),
                        bordercolor=c["bg"], lightcolor=c["bg"],
                        darkcolor=c["bg"])
        try:
            style.layout("TNotebook.Tab", [
                ("Notebook.tab", {"sticky": "nswe", "children": [
                    ("Notebook.padding", {"side": "top", "sticky": "nswe",
                                          "children": [
                        ("Notebook.label", {"side": "top", "sticky": ""}),
                    ]}),
                ]}),
            ])
        except tk.TclError:
            pass
        style.configure("TNotebook.Tab", background=c["bg"],
                        foreground=c["muted"], padding=(14, 9), borderwidth=0,
                        focuscolor=c["bg"], font=(theme.UI_FONT, 10),
                        bordercolor=c["bg"], lightcolor=c["bg"],
                        darkcolor=c["bg"])
        style.map("TNotebook.Tab",
                  background=[("selected", c["bg"]), ("active", c["bg"])],
                  foreground=[("selected", c["accent"]), ("active", c["fg"])],
                  bordercolor=[("selected", c["bg"]), ("active", c["bg"])],
                  lightcolor=[("selected", c["bg"]), ("active", c["bg"])],
                  darkcolor=[("selected", c["bg"]), ("active", c["bg"])],
                  font=[("selected", (theme.UI_FONT, 10, "bold"))])

        # ── Labels ───────────────────────────────────────
        # Section headings differ from body text by weight, not by size, so a
        # screen of stacked sections keeps one type scale.
        style.configure("Heading.TLabel", font=(theme.UI_FONT, 10, "bold"),
                        foreground=c["heading"])
        style.configure("Header.TLabel", font=(theme.UI_FONT, 10, "bold"),
                        foreground=c["heading"])
        style.configure("Status.TLabel", foreground=c["status"])
        style.configure("Success.TLabel", foreground=c["success"])
        style.configure("Error.TLabel", foreground=c["error"])
        style.configure("Muted.TLabel", foreground=c["muted"])
        style.configure("StatusDot.TLabel", font=(theme.UI_FONT, 14))
        # Labels placed on a Card.TFrame: a ttk label defaults to the page
        # background, which draws a box of the wrong colour on a card.
        style.configure("Card.TLabel", background=c["card"])
        style.configure("CardMuted.TLabel", background=c["card"],
                        foreground=c["muted"])
        style.configure("CardValue.TLabel", background=c["card"],
                        foreground=c["heading"],
                        font=(theme.UI_FONT, 18, "bold"))

        # ── Frames ───────────────────────────────────────
        # One boundary per section. A card is separated from the page by its
        # own fill, so it carries no border as well.
        style.configure("Card.TFrame", background=c["card"], relief="flat",
                        borderwidth=0)
        # Header.TFrame still backs the action strip overlaid on the tab row;
        # AppTitle/AppSubtitle went with the title band that used to carry them.
        style.configure("Header.TFrame", background=c["bg"])
        style.configure("StatusBar.TFrame", background=c["status_bg"],
                        relief="flat", borderwidth=0)
        style.configure("StatusBar.TLabel",
                        font=(theme.UI_FONT, 9),
                        background=c["status_bg"], foreground=c["status"])

        # ── Separator / scrollbar / progress ────────────
        style.configure("TSeparator", background=c["border"])

        # ── Paned windows (2-tab consolidated layout) ────
        style.configure("TPanedwindow", background=c["bg"])
        style.configure("Sash", sashthickness=8, gripcount=0,
                        background=c["bg"])
        style.configure("SectionTitle.TLabel",
                        font=(theme.UI_FONT, 9, "bold"),
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

    def _retheme_tabs(self):
        """Push the active palette into raw-tk widgets in every tab."""
        for tab in (self.profiles_tab, self.queue_tab, self.share_tab,
                    self.memory_tab, self.log_tab, self._profiles_scroll):
            apply_theme = getattr(tab, "apply_theme", None)
            if callable(apply_theme):
                try:
                    apply_theme(theme.get())
                except Exception:
                    pass

    # ── UI Build ──────────────────────────────────────────────

    def _build_ui(self):
        # ── Bottom status bar ───────────────────────────────
        statusbar = ttk.Frame(self, style="StatusBar.TFrame")
        statusbar.pack(side="bottom", fill="x")
        self._sb_left = ttk.Label(statusbar, text="Ready",
                                  style="StatusBar.TLabel")
        self._sb_left.pack(side="left", padx=16, pady=3)
        self._sb_right = ttk.Label(statusbar, text="",
                                   style="StatusBar.TLabel")
        self._sb_right.pack(side="right", padx=16, pady=3)

        # There is no title band: the OS title bar already names the app, so a
        # second copy of the name plus a tagline was ~100px of pure chrome.
        # The notebook starts at the top of the window instead.
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(4, 8))

        # Session-level actions share the tab strip's row rather than owning a
        # band of their own. They are placed over the notebook (not packed
        # beside it) because the tab strip belongs to the notebook itself and
        # the strip's right-hand side is otherwise dead space.
        self._topbar = ttk.Frame(self)
        self._topbar.place(in_=self.notebook, relx=1.0, x=-10, y=6,
                           anchor="ne")

        self.logout_btn = ttk.Button(self._topbar, text="Log Out",
                                     command=self._on_logout,
                                     style="Header.TButton")
        self.logout_btn.pack(side="left")

        self.theme_btn = ttk.Button(
            self._topbar,
            text="Dark" if theme.current == "light" else "Light",
            command=self._toggle_theme,
            style="Header.TButton")
        self.theme_btn.pack(side="left")

        # ── Tab 1: Workspace — Profiles | Queue, Log strip below ──
        self.workspace_pane = ttk.PanedWindow(self.notebook, orient="vertical")
        self.work_hpane = ttk.PanedWindow(self.workspace_pane,
                                          orient="horizontal")
        self.workspace_pane.add(self.work_hpane, weight=4)

        # Profiles pane scrolls when the pane is shorter than its content
        self._profiles_scroll = ScrollFrame(self.work_hpane)
        self.profiles_tab = ProfilesTab(self._profiles_scroll.interior)
        self.profiles_tab.pack(fill="both", expand=True)
        self.work_hpane.add(self._profiles_scroll, weight=45)

        self.queue_tab = QueueTab(self.work_hpane)
        self.work_hpane.add(self.queue_tab, weight=55)

        self.log_tab = LogTab(self.workspace_pane)
        self.workspace_pane.add(self.log_tab, weight=1)

        self.notebook.add(self.workspace_pane, text="  Workspace  ")

        # ── Tab 2: Share Center — Share form, Memory strip below ──
        self.share_pane = ttk.PanedWindow(self.notebook, orient="vertical")
        self.share_tab = ShareTab(self.share_pane)
        self.share_pane.add(self.share_tab, weight=3)
        self.memory_tab = MemoryMonitorTab(self.share_pane,
                                           manager=self.manager)
        self.share_pane.add(self.memory_tab, weight=1)
        self.notebook.add(self.share_pane, text="  Share Center  ")

        # Bind AFTER both tabs exist so the event never fires mid-build
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

        # One app-wide mousewheel router serving every scrollable pane
        effects.install_wheel_router(self)

        # Auto-load saved groups from database on startup
        self.after(200, self._load_saved_groups)

        # Position pane sashes once the window is mapped
        self._sashes_done = False
        self.after(120, self._init_sashes)

        # Connect tab callbacks to manager methods
        self._connect_callbacks()

        # Raw-tk widgets build with light defaults — sync them with the
        # saved theme immediately (previously only done on toggle, which
        # left white listboxes/text areas when starting in dark mode).
        self._retheme_tabs()

    def _init_sashes(self, attempts: int = 0):
        """Set initial sash positions — pane weights only govern how extra
        space is distributed on resize, not the starting split.

        sashpos() clamps against the pane's CURRENT size, so this must not
        run until the panes are actually laid out (they report ~1px before
        then, which would collapse the top pane to nothing).
        """
        if self._sashes_done:
            return
        h_ws = self.workspace_pane.winfo_height()
        w_hp = self.work_hpane.winfo_width()
        if h_ws < 300 or w_hp < 500:
            if attempts < 25:  # keep trying for ~3s, then give up gracefully
                self.after(120, lambda: self._init_sashes(attempts + 1))
            else:
                self._sashes_done = True
            return
        try:
            # Profiles pane needs ~620px before its button grid clips
            self.work_hpane.sashpos(0, min(620, max(380, w_hp // 2)))
            # ~260px log strip below the Profiles | Queue pair
            self.workspace_pane.sashpos(0, max(400, h_ws - 260))
        except Exception:
            pass
        self._sashes_done = True
        self._init_share_sash()

    def _init_share_sash(self):
        """Position the Share Center sash. The share pane is unmapped until
        its tab is first selected (height 1), so retry from _on_tab_change."""
        if getattr(self, "_share_sash_done", False):
            return
        h_sh = self.share_pane.winfo_height()
        if h_sh < 300:
            return  # tab not visible yet — _on_tab_change retries
        try:
            # ~310px memory strip under the share form
            self.share_pane.sashpos(0, max(380, h_sh - 310))
            self._share_sash_done = True
        except Exception:
            self._share_sash_done = True
    
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
        self._poll_queue()

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
                if removed_profiles:
                    self.profiles_tab.refresh_profiles()
                    self.queue_tab.refresh_profiles()
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

    def _on_tab_change(self, event=None):
        try:
            sel = self.nametowidget(self.notebook.select())
            if sel is self.workspace_pane:
                self.queue_tab.refresh_profiles()
            elif sel is self.share_pane:
                self.memory_tab._refresh_now()
                # First time the tab shows, its pane finally has a size
                self.after(60, self._init_share_sash)
        except Exception:
            pass

