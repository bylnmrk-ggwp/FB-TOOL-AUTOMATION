import tkinter as tk
from tkinter import ttk, messagebox, Toplevel, Label, Button, Listbox, Scrollbar
import threading

from src.storage import config_manager as cfg
from src.ui import theme
from src.ui.effects import (attach_listbox_hover, attach_button_hover,
                            wait_for_thread, bind_wrap, FlowFrame)


ROSTER_COLLAPSED = "\u25b8 Account Roster"
ROSTER_EXPANDED = "\u25be Account Roster"


class ProfilesTab(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self._vars = {
            "status": tk.StringVar(value="No profile loaded"),
            "logged_in": tk.BooleanVar(value=False),
        }
        self._rate_limited: set[str] = set()  # profiles currently rate-limited
        self._login_scan_running = False  # True while a login-status scan is in flight
        self._on_relogin_all_cb = None

        self._build_ui()
        self.refresh_profiles()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        card = ttk.Frame(self, style="Card.TFrame")
        card.pack(fill="both", expand=True, padx=10, pady=10)

        inner = ttk.Frame(card)
        inner.pack(fill="both", expand=True, padx=12, pady=10)

        self._header_label = ttk.Label(inner, text="Saved Profiles",
                                       style="Header.TLabel")
        self._header_label.pack(anchor="w", **pad)

        # Profile list
        list_frame = ttk.Frame(inner)
        list_frame.pack(fill="both", expand=True, **pad)

        scrollbar = ttk.Scrollbar(list_frame, orient="vertical")
        self.profile_listbox = tk.Listbox(
            list_frame, height=6, selectmode="single",
            yscrollcommand=scrollbar.set,
            font=(theme.MONO_FONT, 10), borderwidth=0,
            highlightthickness=1, highlightbackground=theme.get()["border"],
            activestyle="none")
        scrollbar.config(command=self.profile_listbox.yview)
        scrollbar.pack(side="right", fill="y")
        self.profile_listbox.pack(side="left", fill="both", expand=True)
        self.profile_listbox.bind("<<ListboxSelect>>", self._on_select)
        self._clear_profile_hover = attach_listbox_hover(self.profile_listbox)

        # Per-profile actions wrap to the pane width: five buttons need
        # ~800px in one line, and the profiles pane is often narrower.
        btn_frame = FlowFrame(inner)
        btn_frame.pack(fill="x", **pad)

        self.add_btn = btn_frame.add(ttk.Button(
            btn_frame, text="+ Add Profile",
            command=self._on_add, style="Accent.TButton"))
        self.scan_btn = btn_frame.add(ttk.Button(
            btn_frame, text="Scan for New Profiles", command=self._on_scan))
        self.fetch_name_btn = btn_frame.add(ttk.Button(
            btn_frame, text="Update FB Name",
            command=self._on_fetch_fb_name, state="disabled"))
        self.launch_btn = btn_frame.add(ttk.Button(
            btn_frame, text="Launch Profile",
            command=self._on_launch, state="disabled"))
        self.delete_btn = btn_frame.add(ttk.Button(
            btn_frame, text="Remove", command=self._on_delete,
            state="disabled"))

        # Bulk operations span the full width on their own rows
        self.bulk_fetch_btn = ttk.Button(inner, text="Update All FB Names",
                                         command=self._on_bulk_fetch_fb_names,
                                         style="Accent.TButton")
        self.bulk_fetch_btn.pack(fill="x", padx=pad["padx"], pady=(6, 2))

        self.check_login_btn = ttk.Button(inner, text="Check Login Status (All Profiles)",
                                          command=self._on_check_login_status,
                                          state="normal",
                                          style="TButton")
        self.check_login_btn.pack(fill="x", padx=pad["padx"], pady=(0, 2))

        self.relogin_btn = ttk.Button(inner, text="Re-login All That Need Login",
                                      command=self._on_relogin_all,
                                      style="Accent.TButton")
        self.relogin_btn.pack(fill="x", padx=pad["padx"], pady=(0, 2))

        self.make_profiles_btn = ttk.Button(
            inner, text="Create Chromium Profiles (for Parallel Login)",
            command=self._on_create_chromium_profiles)
        self.make_profiles_btn.pack(fill="x", padx=pad["padx"], pady=(0, 2))

        # Status
        status_frame = ttk.Frame(inner)
        status_frame.pack(fill="x", **pad)

        self.status_dot = ttk.Label(status_frame, text="\u25cf",
                                    style="StatusDot.TLabel", foreground=theme.get()["muted"])
        self.status_dot.pack(side="left", padx=(0, 6))

        ttk.Label(status_frame, textvariable=self._vars["status"],
                  style="Status.TLabel").pack(side="left")

        # ── Auto Setup section ──────────────────────────────
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=8)

        setup_frame = ttk.Frame(inner)
        setup_frame.pack(fill="x", **pad)

        ttk.Label(setup_frame, text="Auto Setup Profile",
                  style="Heading.TLabel").pack(anchor="w")

        tt = "Check & fix: no friends → auto-add, missing profile pic → auto-assign gender-based images"
        setup_hint = ttk.Label(setup_frame, text=tt,
                               foreground=theme.get()["muted"])
        setup_hint.pack(anchor="w", pady=(2, 6))
        bind_wrap(setup_hint)

        options_frame = ttk.Frame(inner)
        options_frame.pack(fill="x", **pad)
        options_frame.columnconfigure(1, weight=1)
        options_frame.columnconfigure(3, weight=1)

        # Row 0: Per-profile button only (bio removed)
        self.setup_btn = ttk.Button(options_frame, text="Run Auto Setup",
                                    command=self._on_auto_setup,
                                    state="disabled",
                                    style="Accent.TButton")
        self.setup_btn.grid(row=0, column=0, columnspan=4, sticky="ew", padx=(0, 0))

        # Row 1: Setup All button (friend connection now automatic)
        self.setup_all_btn = ttk.Button(options_frame, text="Setup All Profiles (Auto-Connect Friends)",
                                        command=self._on_auto_setup_all,
                                        state="disabled",
                                        style="Accent.TButton")
        self.setup_all_btn.grid(row=1, column=0, columnspan=4, sticky="ew", padx=(0, 0), pady=(4, 0))

        # Row 2: Accept All Pending Requests button
        self.accept_pending_btn = ttk.Button(options_frame, text="Accept All Pending Friend Requests (All Profiles)",
                                             command=self._on_accept_all_pending,
                                             state="disabled",
                                             style="Accent.TButton")
        self.accept_pending_btn.grid(row=2, column=0, columnspan=4, sticky="ew", padx=(0, 0), pady=(4, 0))

        # Row 3: Check Friendships button
        self.check_friends_btn = ttk.Button(options_frame, text="Check Friendship Status",
                                            command=self._on_check_friendships,
                                            state="normal",  # Always enabled
                                            style="TButton")
        self.check_friends_btn.grid(row=3, column=0, columnspan=4, sticky="ew", padx=(0, 0), pady=(4, 0))

        # Setup status
        self._setup_status_var = tk.StringVar(value="Select a profile to configure")
        ttk.Label(inner, textvariable=self._setup_status_var,
                  style="Status.TLabel").pack(anchor="w", padx=12, pady=(0, 4))

        # -- Account roster ---------------------------------
        # Imported from the account spreadsheet (IMPORT_ACCOUNTS.bat). These
        # are NOT drivable on their own: every action resolves a Brave profile
        # path, so an account is usable only once linked to one of the saved
        # profiles listed above. Collapsed by default so the drivable
        # profiles stay the focus of the tab.
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=8)

        self._roster_open = False
        roster_header = ttk.Frame(inner)
        roster_header.pack(fill="x", padx=12)

        self._roster_toggle = ttk.Button(roster_header,
                                         text=ROSTER_COLLAPSED,
                                         command=self._toggle_roster)
        self._roster_toggle.pack(side="left")

        ttk.Label(roster_header, text="Search:").pack(side="left", padx=(12, 4))
        self._roster_search_var = tk.StringVar()
        roster_search = ttk.Entry(roster_header,
                                  textvariable=self._roster_search_var,
                                  width=24)
        roster_search.pack(side="left")
        roster_search.bind("<KeyRelease>", lambda e: self._render_roster())

        # Show only accounts/profiles a login run has confirmed. On by default
        # and persisted, so the app opens to the usable set; the queue's dot
        # grid reads the same setting.
        self._logged_in_only = tk.BooleanVar(
            value=bool(cfg.get_setting("show_logged_in_only", True)))
        ttk.Checkbutton(roster_header, text="Logged in only",
                        variable=self._logged_in_only,
                        command=self._on_logged_in_only_toggle
                        ).pack(side="left", padx=(12, 0))

        self._roster_count_var = tk.StringVar(value="")
        ttk.Label(roster_header, textvariable=self._roster_count_var,
                  style="Status.TLabel").pack(side="left", padx=(12, 0))

        # Body stays unpacked until the section is expanded.
        self._roster_body = ttk.Frame(inner)

        rl_frame = ttk.Frame(self._roster_body)
        rl_frame.pack(fill="both", expand=True)

        roster_sb = Scrollbar(rl_frame)
        self.roster_listbox = Listbox(
            rl_frame, height=10, font=(theme.MONO_FONT, 9),
            borderwidth=0, highlightthickness=1,
            highlightbackground=theme.get()["border"],
            yscrollcommand=roster_sb.set, activestyle="none",
            selectmode="single")
        roster_sb.config(command=self.roster_listbox.yview)
        roster_sb.pack(side="right", fill="y")
        self.roster_listbox.pack(side="left", fill="both", expand=True)
        self._clear_roster_hover = attach_listbox_hover(self.roster_listbox)
        self.roster_listbox.bind("<<ListboxSelect>>", self._on_roster_select)

        roster_btns = ttk.Frame(self._roster_body)
        roster_btns.pack(fill="x", pady=(6, 0))

        self.link_account_btn = ttk.Button(
            roster_btns, text="Link to Brave Profile...",
            command=self._on_link_account, state="disabled")
        self.link_account_btn.pack(side="left")

        self.unlink_account_btn = ttk.Button(
            roster_btns, text="Unlink",
            command=self._on_unlink_account, state="disabled")
        self.unlink_account_btn.pack(side="left", padx=(6, 0))

        self._roster_status_var = tk.StringVar(value="")
        ttk.Label(roster_btns, textvariable=self._roster_status_var,
                  style="Status.TLabel").pack(side="left", padx=(12, 0))

        # Info
        ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=8)
        info = ("Add Profile → pick your Brave profile → saved as a reference.\n"
                "No files are copied — your existing Facebook session is used directly.\n"
                "Launch → opens Brave with your profile → ready to share.")
        info_label = ttk.Label(inner, text=info,
                               foreground=theme.get()["muted"])
        info_label.pack(anchor="w", **pad)
        bind_wrap(info_label, pad=2 * pad["padx"])

    # ── Properties ─────────────────────────────────────────

    @property
    def selected_profile(self) -> str | None:
        sel = self.profile_listbox.curselection()
        if not sel:
            return None
        display = self.profile_listbox.get(sel[0])
        # Strip rate-limit prefix to get the real profile name
        if display.startswith("\u26a0 "):
            display = display.split(" — ")[0][len("\u26a0 "):]
        return display

    def set_status(self, text: str, logged_in: bool = False):
        self._vars["status"].set(text)
        self._vars["logged_in"].set(logged_in)
        from src.ui import theme
        colors = theme.get()
        color = colors["success"] if logged_in else colors["muted"]
        self.status_dot.config(foreground=color)

    def apply_theme(self, colors: dict):
        """Re-theme raw-tk widgets that aren't driven by ttk styles."""
        self.profile_listbox.configure(
            bg=colors["list_bg"], fg=colors["list_fg"],
            selectbackground=colors["list_select_bg"],
            selectforeground=colors["list_select_fg"],
            highlightbackground=colors["border"],
            highlightcolor=colors["accent"])
        self.status_dot.config(
            foreground=colors["success"] if self._vars["logged_in"].get()
            else colors["muted"])
        if hasattr(self, "_clear_profile_hover"):
            self._clear_profile_hover()

    def set_launch_enabled(self, enabled: bool):
        self.launch_btn.config(state="normal" if enabled else "disabled")

    # -- Account roster -------------------------------------

    def _toggle_roster(self):
        """Expand or collapse the roster.

        Rows load on first expand, so an empty accounts table costs nothing
        at startup and the query is not run until the section is opened.
        """
        self._roster_open = not self._roster_open
        if self._roster_open:
            self._roster_body.pack(fill="both", expand=True, padx=12,
                                   pady=(6, 0))
            self._roster_toggle.config(text=ROSTER_EXPANDED)
            self.refresh_accounts()
        else:
            self._roster_body.pack_forget()
            self._roster_toggle.config(text=ROSTER_COLLAPSED)

    def refresh_accounts(self):
        """Reload the roster from the database and redraw it."""
        from src.storage import database as db
        try:
            self._accounts = db.list_accounts()
            total, linked = db.count_accounts()
        except Exception as e:
            self._accounts = []
            total = linked = 0
            self._roster_status_var.set(f"Could not read accounts: {e}")
        self._roster_count_var.set(f"{total} account(s), {linked} linked")
        self._render_roster()

    def _render_roster(self):
        """Draw the roster, filtered by the search box, into the listbox."""
        accounts = getattr(self, "_accounts", [])
        if getattr(self, "_logged_in_only", None) and self._logged_in_only.get():
            accounts = [a for a in accounts if a.get("status") == "ok"]
        needle = self._roster_search_var.get().strip().lower()
        if needle:
            accounts = [
                a for a in accounts
                if needle in (a.get("facebook_name") or "").lower()
                or needle in (a.get("username") or "").lower()
                or needle in (a.get("gmail") or "").lower()
                or needle in (a.get("linked_profile") or "").lower()
            ]
        self._roster_visible = accounts

        if hasattr(self, "_clear_roster_hover"):
            self._clear_roster_hover()
        self.roster_listbox.delete(0, "end")
        for a in accounts:
            no = a.get("sheet_no")
            no_txt = "" if no is None else str(no)
            name = (a.get("facebook_name") or "")[:24]
            user = (a.get("username") or "")[:30]
            linked = a.get("linked_profile") or "-"
            self.roster_listbox.insert(
                "end", f"{no_txt:>4}  {name:<24}  {user:<30}  {linked}")
        self._clear_roster_hover = attach_listbox_hover(self.roster_listbox)

        if needle:
            self._roster_status_var.set(f"{len(accounts)} match(es)")
        elif not accounts:
            self._roster_status_var.set(
                "No accounts imported - run IMPORT_ACCOUNTS.bat")
        else:
            self._roster_status_var.set("")
        self._on_roster_select()

    @property
    def selected_account(self) -> dict | None:
        """The roster row currently selected, or None."""
        sel = self.roster_listbox.curselection()
        visible = getattr(self, "_roster_visible", [])
        if not sel or sel[0] >= len(visible):
            return None
        return visible[sel[0]]

    def _on_roster_select(self, event=None):
        acct = self.selected_account
        self.link_account_btn.config(state="normal" if acct else "disabled")
        self.unlink_account_btn.config(
            state="normal" if acct and acct.get("linked_profile")
            else "disabled")

    def _pick_saved_profile(self, account_label: str) -> str | None:
        """Modal chooser over the SAVED profiles, the ones that can be driven.

        Mirrors _show_brave_picker, which instead chooses from the Brave
        installation's own profile directories.
        """
        names = cfg.list_profiles()
        if not names:
            messagebox.showinfo(
                "No Profiles",
                "No Brave profiles are saved yet. Add one first.",
                parent=self)
            return None

        picker = Toplevel(self)
        picker.title("Link to Brave Profile")
        picker.geometry("420x340")
        picker.transient(self.winfo_toplevel())
        picker.grab_set()
        picker.configure(bg=theme.get()["bg"])

        result = {"name": None}

        Label(picker, text=f"Link '{account_label}' to:",
              font=(theme.UI_FONT, 11, "bold"),
              wraplength=380).pack(pady=(15, 5))
        Label(picker,
              text="The account will use this Brave profile's session.",
              fg=theme.get()["muted"],
              font=(theme.UI_FONT, 9)).pack(pady=(0, 10))

        lf = tk.Frame(picker)
        lf.pack(fill="both", expand=True, padx=20, pady=5)
        sb = Scrollbar(lf)
        lb = Listbox(lf, height=10, font=(theme.MONO_FONT, 10),
                     yscrollcommand=sb.set, activestyle="none",
                     selectmode="single")
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        attach_listbox_hover(lb)
        for n in names:
            lb.insert("end", n)

        def on_select():
            sel = lb.curselection()
            if not sel:
                return
            result["name"] = names[sel[0]]
            picker.destroy()

        bf = tk.Frame(picker)
        bf.pack(pady=15)
        ok_btn = Button(bf, text="Link", command=on_select, width=12)
        ok_btn.pack(side="left", padx=5)
        cancel_btn = Button(bf, text="Cancel", command=picker.destroy,
                            width=12)
        cancel_btn.pack(side="left", padx=5)
        attach_button_hover(ok_btn)
        attach_button_hover(cancel_btn)

        self.wait_window(picker)
        return result["name"]

    def _on_link_account(self):
        acct = self.selected_account
        if not acct:
            return
        label = acct.get("facebook_name") or acct.get("username") or "account"
        profile = self._pick_saved_profile(label)
        if not profile:
            return
        from src.storage import database as db
        if db.link_account(acct["username"], profile):
            self.refresh_accounts()
            self._roster_status_var.set(f"Linked '{label}' to '{profile}'")
        else:
            self._roster_status_var.set("Link failed - account not found")

    def _on_unlink_account(self):
        acct = self.selected_account
        if not acct or not acct.get("linked_profile"):
            return
        from src.storage import database as db
        if db.link_account(acct["username"], ""):
            self.refresh_accounts()
            self._roster_status_var.set("Unlinked")

    def _on_logged_in_only_toggle(self):
        cfg.save_setting("show_logged_in_only", bool(self._logged_in_only.get()))
        self.refresh_profiles()
        self._render_roster()

    def _visible_profiles(self) -> list[str]:
        """Profile names to list: this browser's, honouring the "logged in
        only" filter.

        Both browsers' profiles live in one saved map, and a Brave profile
        cannot be opened by a Chromium run or the other way round, so listing
        them together only offers profiles that will not work.
        """
        names = cfg.list_profiles_for_browser()
        if getattr(self, "_logged_in_only", None) and self._logged_in_only.get():
            from src.storage import database as db
            ok = db.logged_in_profiles()
            names = [n for n in names if n in ok]
        return names

    def refresh_profiles(self):
        self._apply_browser_labels()
        if hasattr(self, "_clear_profile_hover"):
            self._clear_profile_hover()
        # A refresh now also follows a login scan, which can run while the
        # operator has a profile picked, so put the selection back.
        keep = self.selected_profile
        self.profile_listbox.delete(0, "end")
        names = self._visible_profiles()
        for name in names:
            display = f"\u26a0 {name} — RATE LIMITED" if name in self._rate_limited else name
            self.profile_listbox.insert("end", display)
        if keep in names:
            idx = names.index(keep)
            self.profile_listbox.selection_set(idx)
            self.profile_listbox.see(idx)
        self._update_buttons()

    def mark_rate_limited(self, profile_name: str):
        """Mark a profile as rate-limited by Facebook."""
        self._rate_limited.add(profile_name)
        self.refresh_profiles()
        self.set_status(f"\u26a0 '{profile_name}' is rate-limited by Facebook")

    # ── Event handlers ────────────────────────────────────

    def set_on_launch_profile(self, callback):
        self._on_launch_profile_cb = callback

    def set_on_auto_setup(self, callback):
        self._on_auto_setup_cb = callback

    def set_on_auto_setup_all(self, callback):
        self._on_auto_setup_all_cb = callback

    def set_on_accept_all_pending(self, callback):
        self._on_accept_all_pending_cb = callback

    def set_on_check_login_status(self, callback):
        self._on_check_login_status_cb = callback

    def set_on_relogin_all(self, callback):
        """callback(usernames) - log every account that needs it back in."""
        self._on_relogin_all_cb = callback

    def set_relogin_enabled(self, enabled: bool):
        self.relogin_btn.config(state="normal" if enabled else "disabled")

    def set_check_login_enabled(self, enabled: bool):
        """Enable or disable the Check Login Status button."""
        self._login_scan_running = not enabled
        self.check_login_btn.config(state="normal" if enabled else "disabled")

    def mark_login_status(self, profile_name: str, logged_in: bool):
        """Update the status line for a profile from a login check result."""
        if logged_in:
            self.set_status(f"'{profile_name}' logged in", logged_in=True)
        else:
            self.set_status(f"'{profile_name}' needs login", logged_in=False)

    def set_auto_setup_status(self, text: str):
        """Update the auto setup status label."""
        self._setup_status_var.set(text)

    def set_auto_setup_enabled(self, enabled: bool):
        """Enable or disable all auto setup buttons."""
        state = "normal" if enabled else "disabled"
        self.setup_btn.config(state=state)
        self.setup_all_btn.config(state=state)
        self.accept_pending_btn.config(state=state)

    def _on_select(self, event=None):
        self._update_buttons()

    def _update_buttons(self):
        has_sel = self.selected_profile is not None
        profiles = cfg.list_profiles()
        has_profiles = len(profiles) > 0
        # Respect running/disabled state from setup operations
        setup_running = self.setup_btn.cget("state") == "disabled" and has_sel and \
                        self._setup_status_var.get().startswith("Running")
        
        # Check if bulk fetch is running
        bulk_running = hasattr(self, '_bulk_fetch_running') and self._bulk_fetch_running
        
        self.launch_btn.config(state="normal" if has_sel and not setup_running and not bulk_running else "disabled")
        self.fetch_name_btn.config(state="normal" if has_sel and not setup_running and not bulk_running else "disabled")
        self.delete_btn.config(state="normal" if has_sel and not bulk_running else "disabled")
        self.setup_btn.config(state="normal" if has_sel and not setup_running and not bulk_running else "disabled")
        self.setup_all_btn.config(state="normal" if has_profiles and not setup_running and not bulk_running else "disabled")
        self.accept_pending_btn.config(state="normal" if has_profiles and not setup_running and not bulk_running else "disabled")
        self.add_btn.config(state="normal" if not bulk_running else "disabled")
        self.scan_btn.config(state="normal" if not bulk_running else "disabled")
        self.bulk_fetch_btn.config(state="normal" if has_profiles and not bulk_running else "disabled")
        self.check_login_btn.config(
            state="normal" if (not bulk_running and not self._login_scan_running)
            else "disabled")
        
        if has_sel:
            self._setup_status_var.set(f"Ready — will run on '{self.selected_profile}'")
        elif has_profiles:
            self._setup_status_var.set(f"{len(profiles)} profile(s) — click 'Setup All Profiles'")
        else:
            self._setup_status_var.set("No profiles — add one first")

    def _on_auto_setup(self):
        """Trigger the auto-setup flow for the selected profile."""
        name = self.selected_profile
        if not name:
            return
        if not hasattr(self, "_on_auto_setup_cb"):
            return

        # target_friends = self._setup_friends_var.get()  # DISABLED
        target_friends = 0  # Disabled for now
        # Bio removed - not needed
        bio = None

        parts = [f"Auto-setup for '{name}'"]
        # parts.append(f"friends≥{target_friends}")  # DISABLED
        # Pinterest query removed - now built-in with PINOY/PINAY

        self._setup_status_var.set(f"Running: {' | '.join(parts)}...")
        self.setup_btn.config(state="disabled")
        self.launch_btn.config(state="disabled")

        self._on_auto_setup_cb(
            name,
            target_friends=target_friends,
            pinterest_query=None,  # Always None - built-in searches
            bio=bio or None,
        )

    def _on_auto_setup_all(self):
        """Trigger auto-setup on every saved profile."""
        if not hasattr(self, "_on_auto_setup_all_cb"):
            return
        profiles = cfg.list_profiles()
        if not profiles:
            return

        # Target friends feature is DISABLED for now
        target_friends = 0
        
        # Bio removed - not needed
        bio = None
        
        # ALWAYS connect friends - automatic part of setup process
        connect_friends = True  # Always True, not from checkbox anymore

        self._setup_status_var.set(f"Running auto-setup on {len(profiles)} profile(s)...")
        self.setup_btn.config(state="disabled")
        self.setup_all_btn.config(state="disabled")
        self.launch_btn.config(state="disabled")

        self._on_auto_setup_all_cb(
            target_friends=target_friends,
            pinterest_query=None,  # Always None - built-in searches
            bio=bio or None,
            connect_friends=connect_friends,  # Always True
        )

    def _on_accept_all_pending(self):
        """Trigger the accept all pending friend requests operation."""
        if not hasattr(self, "_on_accept_all_pending_cb"):
            return
        profiles = cfg.list_profiles()
        if not profiles:
            return

        self._setup_status_var.set(f"Checking {len(profiles)} profile(s) for pending friend requests...")
        self.setup_btn.config(state="disabled")
        self.setup_all_btn.config(state="disabled")
        self._on_accept_all_pending_cb()

    def _on_check_login_status(self):
        """Live-check which profiles are logged in to Facebook."""
        if not hasattr(self, "_on_check_login_status_cb") or not self._on_check_login_status_cb:
            return
        profiles = cfg.list_profiles()
        if not profiles:
            self.set_auto_setup_status("No profiles to check")
            return
        self.set_status("Checking login status...")
        self.set_auto_setup_status(f"Checking login status for {len(profiles)} profile(s)...")
        self._login_scan_running = True
        self.check_login_btn.config(state="disabled")
        self._on_check_login_status_cb()

    def _needs_login(self) -> list[dict]:
        """Roster rows we could actually drive but whose session is not live:
        a Brave profile this PC has saved, not disabled, status not 'ok'."""
        from src.storage import database as db
        rows = []
        for a in db.list_accounts():
            profile = a.get("linked_profile") or ""
            if not profile or not cfg.get_profile_path(profile):
                continue
            if (a.get("status") or "") in ("ok", "disabled"):
                continue
            sheet = (a.get("sheet_status") or "").strip().upper()
            if sheet == "DISABLED":
                continue
            # Exact match: "NOT LOGGED IN" contains the same words.
            if sheet == "LOGGED IN":
                continue
            rows.append(a)
        return rows

    def _on_relogin_all(self, confirm: bool = True):
        """Re-login every account that needs it. Sequential on the worker -
        Brave's profile lock allows nothing else - in batches with a pause."""
        targets = self._needs_login()
        if not targets:
            self.set_auto_setup_status("Every account with a profile is already logged in")
            return
        if confirm and not messagebox.askyesno(
                "Re-login accounts",
                f"Log {len(targets)} account(s) back in?\n\n"
                "Close every Brave window first. They run a few at a time "
                "with a pause between, so this takes a while.",
                parent=self):
            return
        self.set_relogin_enabled(False)
        self.set_status(f"Logging {len(targets)} account(s) back in...")
        self.set_auto_setup_status(f"Re-login: 0/{len(targets)}")
        cb = getattr(self, "_on_relogin_all_cb", None)
        if cb:
            cb([a["username"] for a in targets])

    def _on_create_chromium_profiles(self, confirm: bool = True):
        """Give every roster account its own Chromium profile directory.

        This is what makes a parallel login possible: Brave keeps all profiles
        in one User Data tree and binds the cookie key to it, so only one can
        be driven at a time. A Chromium profile is a directory of its own, so
        a wave of them opens together.

        No browser is touched - it only creates directories and links them -
        but a 260-row roster is enough filesystem work to freeze the window,
        so it runs on a thread.
        """
        from src.core import browser_choice
        if browser_choice.current_browser() != browser_choice.CHROMIUM:
            messagebox.showinfo(
                "Chromium is not the selected browser",
                "Profiles here are Brave profiles, which live in one shared "
                "User Data tree.\n\nSwitch the browser to Chromium first, then "
                "create the per-account profiles that allow parallel logins.",
                parent=self)
            return
        if confirm and not messagebox.askyesno(
                "Create Chromium profiles",
                "Create a Chromium profile for every roster account that has "
                "none?\n\nExisting profiles keep their sessions - this only "
                "adds what is missing.",
                parent=self):
            return

        self.make_profiles_btn.config(state="disabled")
        self.set_auto_setup_status("Creating Chromium profiles...")

        def work():
            from src.core import chromium_profiles
            try:
                counts = chromium_profiles.provision_all(log=self._write_log)
                done = (f"Chromium profiles: {counts['created']} created, "
                        f"{counts['already']} already there, "
                        f"{counts['skipped']} skipped")
            except Exception as e:  # noqa: BLE001 - reported in the UI, never raised
                done = f"Creating profiles failed: {type(e).__name__}: {e}"
            self.after(0, finish, done)

        def finish(message: str):
            self.make_profiles_btn.config(state="normal")
            self.set_auto_setup_status(message)
            self.refresh_profiles()
            self.refresh_accounts()

        threading.Thread(target=work, name="chromium-profiles", daemon=True).start()

    def _write_log(self, message: str):
        """Send one line to the Log tab when the window has wired one up."""
        callback = getattr(self, "_log_callback", None)
        if callback:
            callback(message)

    def _on_check_friendships(self):
        """Check and display friendship status between all profiles."""
        from src.storage.database import are_friends, get_friend_count_for_profile
        
        profiles = cfg.list_profiles()
        if not profiles:
            self._setup_status_var.set("❌ No profiles found!")
            return
        
        # Calculate statistics
        total_possible = len(profiles) * (len(profiles) - 1) // 2
        actual_friendships = 0
        
        # Count actual friendships
        for i, profile1 in enumerate(profiles):
            for profile2 in profiles[i+1:]:
                if are_friends(profile1, profile2):
                    actual_friendships += 1
        
        # Build report
        report_lines = []
        report_lines.append("="*60)
        report_lines.append(f"FRIENDSHIP STATUS - {len(profiles)} PROFILES")
        report_lines.append("="*60)
        report_lines.append("")
        
        # Summary
        if total_possible > 0:
            percentage = (actual_friendships * 100) // total_possible
            report_lines.append(f"Completion: {actual_friendships}/{total_possible} ({percentage}%)")
        else:
            report_lines.append(f"Completion: N/A")
        report_lines.append("")
        
        # Individual counts
        all_complete = True
        for profile in profiles:
            friend_count = get_friend_count_for_profile(profile)
            max_friends = len(profiles) - 1
            
            if friend_count == max_friends:
                status = "✅"
            elif friend_count >= max_friends * 0.7:
                status = "🟡"
                all_complete = False
            else:
                status = "❌"
                all_complete = False
            
            percentage = (friend_count * 100 // max_friends) if max_friends > 0 else 0
            # Truncate long names
            display_name = profile if len(profile) <= 30 else profile[:27] + "..."
            report_lines.append(f"{status} {display_name}: {friend_count}/{max_friends} ({percentage}%)")
        
        report_lines.append("")
        
        if all_complete and actual_friendships == total_possible:
            report_lines.append("🎉 ALL PROFILES ARE FRIENDS!")
            self._setup_status_var.set(f"✅ All {len(profiles)} profiles are friends with each other!")
        else:
            missing = total_possible - actual_friendships
            report_lines.append(f"⚠️  {missing} friendships missing")
            report_lines.append("💡 Click 'Accept All Pending Friend Requests' to complete")
            self._setup_status_var.set(f"⚠️  {actual_friendships}/{total_possible} friendships complete ({missing} missing)")
        
        report_lines.append("="*60)
        
        # Write to log
        if hasattr(self, "_log_callback") and self._log_callback:
            for line in report_lines:
                self._log_callback(line)

    def _browser_name(self) -> str:
        """Whichever browser the automation drives, for button and dialog text:
        the tab used to say Brave everywhere and now adds Chromium profiles."""
        from src.core import browser_choice
        return browser_choice.current_browser().title()

    def _apply_browser_labels(self):
        name = self._browser_name()
        try:
            self._header_label.config(text=f"Saved {name} Profiles")
            self.add_btn.config(text=f"+ Add {name} Profile")
        except Exception:
            pass

    def _on_add_chromium(self):
        """Create one Chromium profile directory for an account.

        Nothing to pick from: a Chromium profile does not exist until it is
        created, and it is named for the account that will use it.
        """
        from tkinter import simpledialog
        from src.core import chromium_profiles
        username = simpledialog.askstring(
            "Add Chromium profile",
            "Account this profile logs in as (the roster username):",
            parent=self)
        username = (username or "").strip()
        if not username:
            return
        path = chromium_profiles.ensure_profile(username)
        cfg.save_profile(username, str(path))
        try:
            from src.storage import database as db
            db.link_account(username, username)
        except Exception:
            pass    # an account not on the roster yet still gets its profile
        self.refresh_profiles()
        self.refresh_accounts()
        self.set_status(f"Chromium profile ready for {username}")

    def _on_add(self):
        from src.core import browser_choice
        if browser_choice.current_browser() == browser_choice.CHROMIUM:
            self._on_add_chromium()
            return
        # Show Brave profile picker directly
        brave_profiles = cfg.list_brave_profiles()
        if not brave_profiles:
            messagebox.showerror(
                "No Brave Profiles",
                "No Brave profiles found.\n\n"
                "Make sure Brave Browser is installed at its default location."
            )
            return

        selected_brave = self._show_brave_picker(brave_profiles)
        if selected_brave is None:
            return

        brave_name = selected_brave["name"]

        # Show "Fetching..." dialog while we get the Facebook name
        fetch_dialog = Toplevel(self)
        fetch_dialog.title("Fetching Facebook Name")
        fetch_dialog.geometry("350x100")
        fetch_dialog.resizable(False, False)
        fetch_dialog.transient(self)
        fetch_dialog.grab_set()
        Label(fetch_dialog, text=f"Fetching Facebook name for profile '{brave_name}'...",
              font=(theme.UI_FONT, 10), wraplength=320).pack(pady=(20, 5))
        progress = ttk.Progressbar(fetch_dialog, mode="indeterminate", length=280)
        progress.pack(pady=5)
        progress.start(15)

        result = {"fb_name": None}

        def _fetch_in_thread():
            try:
                from src.core.facebook_automation import fetch_facebook_name_sync
                result["fb_name"] = fetch_facebook_name_sync(selected_brave["full_path"])
            except Exception as e:
                print(f"[fetch_thread] Error: {e}", flush=True)

        thread = threading.Thread(target=_fetch_in_thread, daemon=True)
        thread.start()
        # Pump the event loop instead of joining, so the progressbar above
        # actually animates. 60s cap covers browser launch + Facebook load.
        wait_for_thread(fetch_dialog, thread, timeout=60)

        fetch_dialog.destroy()

        fb_name = result["fb_name"]
        
        # Extract the Brave profile number/name
        import os
        import re
        brave_dir = os.path.basename(selected_brave["full_path"])
        match = re.search(r'Profile\s+(\d+)', brave_dir, re.IGNORECASE)
        if match:
            brave_short = match.group(1)
        elif brave_dir.lower() == "default":
            brave_short = "Default"
        else:
            brave_short = brave_name
        
        if fb_name:
            # Use format: "1 - Meiko kirigaya"
            name = f"{brave_short} - {fb_name}"
        else:
            # Use Brave name if Facebook name not found
            name = brave_short

        # Ensure unique name
        names = cfg.list_profiles()
        if name in names:
            counter = 2
            while f"{name} ({counter})" in names:
                counter += 1
            name = f"{name} ({counter})"

        # Save the Brave profile path reference
        cfg.save_profile(name, selected_brave["full_path"])

        if fb_name:
            msg = f"Profile saved as:\n'{name}'\n\nFacebook: {fb_name}\nBrave: {brave_short}"
        else:
            msg = f"Profile saved as:\n'{name}'\n\n(Could not fetch Facebook name — not logged in?)"

        messagebox.showinfo("Profile Added", msg)

        self.refresh_profiles()
        self.profile_listbox.selection_set("end")
        self._update_buttons()

    def _show_brave_picker(self, brave_profiles: list[dict]) -> dict | None:
        """Show a dialog to pick a Brave profile. Returns the selected profile dict or None."""
        picker = Toplevel(self)
        picker.title("Select Brave Profile")
        picker.geometry("500x350")
        picker.resizable(False, False)
        picker.transient(self)
        picker.grab_set()

        result = {"selected": None}

        Label(picker, text="Select a Brave profile to use:",
              font=(theme.UI_FONT, 11, "bold")).pack(pady=(15, 5))
        Label(picker, text="Your Facebook session will be used directly from this profile.",
              fg=theme.get()["muted"], font=(theme.UI_FONT, 9)).pack(pady=(0, 10))

        list_frame = tk.Frame(picker)
        list_frame.pack(fill="both", expand=True, padx=20, pady=5)

        sb = Scrollbar(list_frame)
        lb = Listbox(list_frame, height=10, font=(theme.MONO_FONT, 10),
                     yscrollcommand=sb.set, activestyle="none",
                     selectmode="single")
        sb.config(command=lb.yview)
        sb.pack(side="right", fill="y")
        lb.pack(side="left", fill="both", expand=True)
        attach_listbox_hover(lb)

        for p in brave_profiles:
            # Show profile name first (e.g. "1", "2", "3") since that's what will be used
            label = p["name"]
            if p["email"]:
                label = f"{p['name']}  <{p['email']}>  ({p['dir_name']})"
            elif p["name"] != p["dir_name"]:
                label = f"{p['name']}  ({p['dir_name']})"
            lb.insert("end", label)

        def on_select():
            sel = lb.curselection()
            if not sel:
                return
            result["selected"] = brave_profiles[sel[0]]
            picker.destroy()

        def on_cancel():
            picker.destroy()

        btn_frame = tk.Frame(picker)
        btn_frame.pack(pady=15)
        select_btn = Button(btn_frame, text="Select", command=on_select, width=12)
        select_btn.pack(side="left", padx=5)
        cancel_btn = Button(btn_frame, text="Cancel", command=on_cancel, width=12)
        cancel_btn.pack(side="left", padx=5)
        attach_button_hover(select_btn)
        attach_button_hover(cancel_btn)

        self.wait_window(picker)
        return result["selected"]

    def _on_launch(self):
        name = self.selected_profile
        if not name:
            return
        if hasattr(self, "_on_launch_profile_cb"):
            self._on_launch_profile_cb(name)

    def _on_scan(self):
        """Scan the selected browser for new profiles and auto-add them."""
        new_names = cfg.auto_sync_profiles()
        self.refresh_profiles()
        if new_names:
            self.set_status(f"Found {len(new_names)} new profile(s): {', '.join(new_names)}")
            messagebox.showinfo(
                "Profiles Found",
                f"Auto-detected {len(new_names)} new profile(s):\n\n" +
                "\n".join(f"  - {n}" for n in new_names) +
                "\n\nThey are ready to use."
            )
        else:
            self.set_status("No new profiles found — every profile of this browser is already in the list.")

    def _on_delete(self):
        name = self.selected_profile
        if not name:
            return
        ok = messagebox.askyesno("Remove Profile",
                                 f"Remove profile '{name}' from the list?\n"
                                 "The original Brave profile is not affected.",
                                 parent=self)
        if not ok:
            return
        cfg.delete_profile(name)
        self.refresh_profiles()

    def _on_fetch_fb_name(self):
        """Fetch and update the Facebook name for the selected profile."""
        old_name = self.selected_profile
        if not old_name:
            return

        profile_path = cfg.get_profile_path(old_name)
        if not profile_path:
            messagebox.showerror("Error", f"Profile path not found for '{old_name}'")
            return

        # Show "Fetching..." dialog
        fetch_dialog = Toplevel(self)
        fetch_dialog.title("Fetching Facebook Name")
        fetch_dialog.geometry("350x100")
        fetch_dialog.resizable(False, False)
        fetch_dialog.transient(self)
        fetch_dialog.grab_set()
        Label(fetch_dialog, text=f"Fetching Facebook name for '{old_name}'...",
              font=(theme.UI_FONT, 10), wraplength=320).pack(pady=(20, 5))
        progress = ttk.Progressbar(fetch_dialog, mode="indeterminate", length=280)
        progress.pack(pady=5)
        progress.start(15)

        result = {"fb_name": None, "error": None}

        def _fetch_in_thread():
            try:
                from src.core.facebook_automation import fetch_facebook_name_sync
                result["fb_name"] = fetch_facebook_name_sync(profile_path)
            except Exception as e:
                result["error"] = str(e)
                print(f"[fetch_thread] Error: {e}", flush=True)

        thread = threading.Thread(target=_fetch_in_thread, daemon=True)
        thread.start()
        wait_for_thread(fetch_dialog, thread, timeout=60)

        fetch_dialog.destroy()

        if result["error"]:
            messagebox.showerror("Error", f"Failed to fetch Facebook name:\n{result['error']}")
            return

        fb_name = result["fb_name"]
        if not fb_name:
            messagebox.showwarning(
                "Not Found",
                f"Could not fetch Facebook name for '{old_name}'.\n\n"
                "Possible reasons:\n"
                "• Not logged into Facebook on this profile\n"
                "• Facebook changed their page structure\n"
                "• Network or browser issue"
            )
            return

        # Extract the Brave profile number/name from the path
        # e.g., "C:/.../User Data/Profile 1" -> "Profile 1"
        import os
        brave_dir = os.path.basename(profile_path)
        
        # Extract just the number if it's like "Profile 1" -> "1"
        # or keep it as-is if it's "Default"
        import re
        match = re.search(r'Profile\s+(\d+)', brave_dir, re.IGNORECASE)
        if match:
            brave_short = match.group(1)
        elif brave_dir.lower() == "default":
            brave_short = "Default"
        else:
            brave_short = brave_dir
        
        # Create new name: "1 - Meiko kirigaya" format
        new_name = f"{brave_short} - {fb_name}"
        
        # Ensure uniqueness
        all_names = cfg.list_profiles()
        if new_name in all_names and new_name != old_name:
            counter = 2
            while f"{new_name} ({counter})" in all_names:
                counter += 1
            new_name = f"{new_name} ({counter})"

        # If the name is the same, just show the info
        if new_name == old_name:
            messagebox.showinfo(
                "Already Updated",
                f"Profile name is already up-to-date:\n'{new_name}'"
            )
            return

        # Rename the profile
        cfg.save_profile(new_name, profile_path)
        cfg.delete_profile(old_name)

        # Update facebook_urls mapping if it exists
        config = cfg._load_config()
        if "facebook_urls" in config and old_name in config["facebook_urls"]:
            config["facebook_urls"][new_name] = config["facebook_urls"].pop(old_name)
            cfg._save_config(config)

        messagebox.showinfo(
            "Name Updated",
            f"Profile renamed:\n\nOld: '{old_name}'\nNew: '{new_name}'\n\n"
            f"Facebook name: {fb_name}"
        )

        self.refresh_profiles()
        # Select the renamed profile
        try:
            idx = cfg.list_profiles().index(new_name)
            self.profile_listbox.selection_clear(0, "end")
            self.profile_listbox.selection_set(idx)
            self._update_buttons()
        except (ValueError, IndexError):
            pass

    def _on_bulk_fetch_fb_names(self):
        """Fetch and update Facebook names for ALL profiles that don't have one yet."""
        profiles = cfg.list_profiles()
        if not profiles:
            messagebox.showinfo("No Profiles", "No profiles to update.")
            return
        
        # Check which profiles need updating (don't have " - " in their name)
        profiles_to_update = []
        profiles_already_named = []
        
        for profile_name in profiles:
            if " - " in profile_name:
                # Already has Facebook name format
                profiles_already_named.append(profile_name)
            else:
                # Needs Facebook name
                profiles_to_update.append(profile_name)
        
        if not profiles_to_update:
            messagebox.showinfo(
                "All Up-to-Date",
                f"All {len(profiles)} profile(s) already have Facebook names!\n\n"
                "No updates needed.",
                parent=self
            )
            return
        
        # Show summary and confirm
        summary_msg = f"Found {len(profiles)} total profile(s):\n\n"
        summary_msg += f"✓ Already have names: {len(profiles_already_named)}\n"
        summary_msg += f"⟳ Need update: {len(profiles_to_update)}\n\n"
        
        if profiles_already_named:
            summary_msg += "Profiles that will be SKIPPED:\n"
            for name in profiles_already_named[:3]:
                summary_msg += f"  • {name}\n"
            if len(profiles_already_named) > 3:
                summary_msg += f"  ... and {len(profiles_already_named) - 3} more\n"
            summary_msg += "\n"
        
        summary_msg += "Profiles that will be UPDATED:\n"
        for name in profiles_to_update[:3]:
            summary_msg += f"  • {name}\n"
        if len(profiles_to_update) > 3:
            summary_msg += f"  ... and {len(profiles_to_update) - 3} more\n"
        
        summary_msg += f"\nEstimated time: {len(profiles_to_update) * 1.5:.0f}-{len(profiles_to_update) * 2:.0f} minutes\n\n"
        summary_msg += "Continue?"
        
        confirm = messagebox.askyesno(
            "Bulk Update Facebook Names",
            summary_msg,
            parent=self
        )
        
        if not confirm:
            return
        
        # Create progress dialog
        progress_dialog = Toplevel(self)
        progress_dialog.title("Bulk Updating Facebook Names")
        progress_dialog.geometry("450x220")
        progress_dialog.resizable(False, False)
        progress_dialog.transient(self)
        progress_dialog.grab_set()
        
        Label(progress_dialog, text="Fetching Facebook names...",
              font=(theme.UI_FONT, 11, "bold")).pack(pady=(15, 5))
        
        status_var = tk.StringVar(value="Starting...")
        status_label = Label(progress_dialog, textvariable=status_var,
                           font=(theme.UI_FONT, 9), fg=theme.get()["muted"])
        status_label.pack(pady=5)
        
        progress_bar = ttk.Progressbar(progress_dialog, mode="determinate", length=400)
        progress_bar.pack(pady=10)
        progress_bar["maximum"] = len(profiles_to_update)
        progress_bar["value"] = 0
        
        results_text = tk.Text(progress_dialog, height=6, width=50, font=(theme.MONO_FONT, 8))
        results_text.pack(pady=5, padx=10, fill="both", expand=True)
        
        # Show skipped profiles
        if profiles_already_named:
            results_text.insert("end", f"⊘ Skipping {len(profiles_already_named)} profile(s) with names:\n")
            for name in profiles_already_named[:3]:
                results_text.insert("end", f"  • {name}\n")
            if len(profiles_already_named) > 3:
                results_text.insert("end", f"  ... and {len(profiles_already_named) - 3} more\n")
            results_text.insert("end", f"\n{'='*50}\n")
            results_text.insert("end", f"Updating {len(profiles_to_update)} profile(s):\n\n")
        
        # Disable all buttons during bulk operation
        self._bulk_fetch_running = True
        self._update_buttons()
        
        results = {
            "success": [],
            "failed": [],
            "skipped": profiles_already_named,  # Add pre-skipped profiles
        }
        
        # Tk is not thread-safe: the worker below must not touch widgets
        # directly. These marshal every mutation onto the main thread, which
        # is free to repaint because _check_thread polls with after().
        def _ui(fn):
            try:
                progress_dialog.after(0, fn)
            except tk.TclError:
                pass  # dialog already closed

        def _status(text):
            _ui(lambda t=text: status_var.set(t))

        def _append(text):
            def apply(t=text):
                results_text.insert("end", t)
                results_text.see("end")
            _ui(apply)

        def _progress(value):
            _ui(lambda v=value: progress_bar.configure(value=v))

        def _bulk_fetch_thread():
            import os
            import re
            from src.core.facebook_automation import fetch_facebook_name_sync
            
            for i, old_name in enumerate(profiles_to_update):
                try:
                    # Update status
                    _status(f"Processing {i+1}/{len(profiles_to_update)}: {old_name}")
                    _append(f"[{i+1}/{len(profiles_to_update)}] {old_name}...")
                    
                    profile_path = cfg.get_profile_path(old_name)
                    if not profile_path:
                        _append(" ✗ Path not found\n")
                        results["failed"].append((old_name, "Path not found"))
                        _progress(i + 1)
                        continue
                    
                    # Fetch Facebook name
                    fb_name = fetch_facebook_name_sync(profile_path)
                    
                    if not fb_name:
                        _append(" ✗ Not logged in or failed\n")
                        results["failed"].append((old_name, "Could not fetch name"))
                        _progress(i + 1)
                        continue
                    
                    # Extract Brave profile info
                    brave_dir = os.path.basename(profile_path)
                    match = re.search(r'Profile\s+(\d+)', brave_dir, re.IGNORECASE)
                    if match:
                        brave_short = match.group(1)
                    elif brave_dir.lower() == "default":
                        brave_short = "Default"
                    else:
                        brave_short = brave_dir
                    
                    # Create new name
                    new_name = f"{brave_short} - {fb_name}"
                    
                    # Check if already has this name
                    if new_name == old_name:
                        _append(f" ✓ Already correct\n")
                        results["skipped"].append((old_name, "Already up-to-date"))
                        _progress(i + 1)
                        continue
                    
                    # Ensure uniqueness
                    all_names = cfg.list_profiles()
                    if new_name in all_names:
                        counter = 2
                        while f"{new_name} ({counter})" in all_names:
                            counter += 1
                        new_name = f"{new_name} ({counter})"
                    
                    # Rename the profile
                    cfg.save_profile(new_name, profile_path)
                    cfg.delete_profile(old_name)
                    
                    # Update facebook_urls mapping
                    config = cfg._load_config()
                    if "facebook_urls" in config and old_name in config["facebook_urls"]:
                        config["facebook_urls"][new_name] = config["facebook_urls"].pop(old_name)
                        cfg._save_config(config)
                    
                    _append(f" ✓ → {new_name}\n")
                    results["success"].append((old_name, new_name))
                    
                except Exception as e:
                    _append(f" ✗ Error: {e}\n")
                    results["failed"].append((old_name, str(e)))
                
                _progress(i + 1)
            
            # Show completion
            _status("Completed!")
            _append(f"\n{'='*50}\n")
            _append(f"✓ Success: {len(results['success'])}\n")
            _append(f"⊘ Skipped: {len(results['skipped'])}\n")
            _append(f"✗ Failed: {len(results['failed'])}\n")
        
        def _on_complete():
            # Re-enable buttons
            self._bulk_fetch_running = False
            self._update_buttons()
            
            # Refresh profile list
            self.refresh_profiles()
            
            # Close dialog after a moment
            progress_dialog.after(2000, progress_dialog.destroy)
            
            # Show summary
            skipped_with_names = len(profiles_already_named)
            skipped_already_correct = len(results['skipped']) - skipped_with_names
            
            summary = (
                f"Bulk update completed!\n\n"
                f"✓ Successfully updated: {len(results['success'])}\n"
                f"⊘ Skipped (already had names): {skipped_with_names}\n"
            )
            
            if skipped_already_correct > 0:
                summary += f"⊘ Skipped (already correct): {skipped_already_correct}\n"
            
            summary += f"✗ Failed: {len(results['failed'])}\n"
            
            if results["failed"]:
                summary += "\n\nFailed profiles:\n"
                for name, reason in results["failed"][:5]:  # Show first 5
                    summary += f"  • {name}: {reason}\n"
                if len(results["failed"]) > 5:
                    summary += f"  ... and {len(results['failed']) - 5} more"
            
            messagebox.showinfo("Bulk Update Complete", summary, parent=self)
        
        # Run in thread
        thread = threading.Thread(target=_bulk_fetch_thread, daemon=True)
        thread.start()
        
        # Monitor thread completion
        def _check_thread():
            if thread.is_alive():
                progress_dialog.after(100, _check_thread)
            else:
                _on_complete()
        
        _check_thread()

