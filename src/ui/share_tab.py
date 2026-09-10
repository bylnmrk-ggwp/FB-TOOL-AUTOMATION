import json
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path

from src.ui import theme
from src.ui.effects import attach_listbox_hover

SAVED_FILE = Path.home() / ".autoshare" / "saved_shares.json"


class ShareTab(ttk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self._vars = {
            "post_url": tk.StringVar(),
            "group_name": tk.StringVar(),
            "reaction": tk.StringVar(value="none"),
            "status": tk.StringVar(value="Ready"),
            "can_share": tk.BooleanVar(value=False),
        }
        
        # Comment text will be stored in a Text widget instead of StringVar
        self._comment_text_widget = None

        self._recent_shares: list[tuple[str, str, str]] = []
        self._saved_presets: list[dict] = []
        self._on_share_cb = None
        self._on_timeline_cb = None
        self._on_join_group_cb = None
        self._on_fetch_groups_cb = None
        self._on_load_groups_cb = None
        self._on_share_selected_cb = None
        self._on_bulk_share_cb = None

        self._load_saved()
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # ── Scrollable container ──────────────────────────
        self._canvas = tk.Canvas(self, bg=theme.get()["bg"],
                                 highlightthickness=0, borderwidth=0)
        self._vbar = ttk.Scrollbar(self, orient="vertical",
                                   command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vbar.set)
        self._vbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        body = ttk.Frame(self._canvas)
        self._canvas._body_window = self._canvas.create_window(
            (0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind(
            "<Configure>",
            lambda e: self._canvas.itemconfigure(
                self._canvas._body_window, width=e.width))
        # Wheel scrolling is handled by the app-wide router (see effects.py)
        from src.ui.effects import register_wheel_target
        register_wheel_target(self._canvas)

        # ── Share form card ───────────────────────────────
        form_card = ttk.Frame(body, style="Card.TFrame")
        form_card.pack(fill="x", padx=10, pady=(10, 6))

        form = ttk.Frame(form_card)
        form.pack(fill="x", padx=12, pady=10)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        ttk.Label(form, text="Share to Group",
                  style="Header.TLabel").grid(row=0, column=0, columnspan=4,
                                              sticky="w", **pad)
        ttk.Separator(form, orient="horizontal").grid(row=1, column=0,
                                                       columnspan=4,
                                                       sticky="ew", **pad)

        # Row 2: Post URL
        ttk.Label(form, text="Post URL:").grid(row=2, column=0, sticky="w",
                                                pady=4)
        url_entry = ttk.Entry(form, textvariable=self._vars["post_url"])
        url_entry.grid(row=2, column=1, columnspan=3, sticky="ew",
                       padx=(6, 0), pady=4)

        # Row 3: Group + Reaction
        ttk.Label(form, text="Group:").grid(row=3, column=0, sticky="w",
                                            pady=4)
        name_entry = ttk.Entry(form, textvariable=self._vars["group_name"])
        name_entry.grid(row=3, column=1, sticky="ew", padx=(6, 6), pady=4)
        name_entry.bind("<Return>", lambda e: self._on_share())

        ttk.Label(form, text="Reaction:").grid(row=3, column=2, sticky="w",
                                               pady=4, padx=(12, 0))
        self._reaction_dropdown = ttk.Combobox(
            form, textvariable=self._vars["reaction"],
            values=["none", "like", "love", "care", "haha", "wow", "sad", "angry"],
            state="readonly", width=12)
        self._reaction_dropdown.grid(row=3, column=3, sticky="ew",
                                     padx=(6, 0), pady=4)

        # Row 4: Comment (multi-line, one per line)
        ttk.Label(form, text="Comments:").grid(row=4, column=0, sticky="nw",
                                              pady=4)
        
        comment_frame = ttk.Frame(form)
        comment_frame.grid(row=4, column=1, columnspan=3, sticky="ew",
                          padx=(6, 0), pady=4)
        comment_frame.columnconfigure(0, weight=1)
        
        self._comment_text_widget = tk.Text(comment_frame, height=3, width=40,
                                           font=(theme.UI_FONT, 9), wrap="word",
                                           borderwidth=1, relief="solid",
                                           highlightthickness=1,
                                           highlightbackground=theme.get()["border"])
        comment_scroll = ttk.Scrollbar(comment_frame, orient="vertical",
                                      command=self._comment_text_widget.yview)
        self._comment_text_widget.configure(yscrollcommand=comment_scroll.set)
        comment_scroll.grid(row=0, column=1, sticky="ns")
        self._comment_text_widget.grid(row=0, column=0, sticky="ew")
        
        # Add placeholder text
        ttk.Label(comment_frame, text="(One comment per line - will be selected randomly)",
                 foreground=theme.get()["muted"], font=(theme.UI_FONT, 8)).grid(
                     row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # Row 5: Buttons + status
        btn_frame = ttk.Frame(form)
        btn_frame.grid(row=5, column=0, columnspan=4, sticky="ew",
                       pady=(12, 0))
        btn_frame.columnconfigure(5, weight=1)

        self.timeline_btn = ttk.Button(btn_frame, text="Post to Timeline",
                                       command=self._on_share_timeline,
                                       state="disabled",
                                       style="Timeline.TButton")
        self.timeline_btn.grid(row=0, column=0, padx=(0, 8))

        self.share_btn = ttk.Button(btn_frame, text="Share to Group",
                                    command=self._on_share, state="disabled",
                                    style="Accent.TButton")
        self.share_btn.grid(row=0, column=1, padx=(0, 8))

        self.bulk_share_btn = ttk.Button(btn_frame, text="Bulk Share to My Groups",
                                         command=self._on_bulk_share_to_groups,
                                         state="disabled")
        self.bulk_share_btn.grid(row=0, column=2, padx=(0, 8))

        self.save_btn = ttk.Button(btn_frame, text="Save Preset",
                                   command=self._save_preset, state="disabled")
        self.save_btn.grid(row=0, column=3, padx=(0, 12))

        status_lbl = ttk.Label(btn_frame, textvariable=self._vars["status"],
                               style="Status.TLabel")
        status_lbl.grid(row=0, column=5, sticky="w")

        self._vars["post_url"].trace_add("write", self._update_share_state)
        self._vars["group_name"].trace_add("write", self._update_share_state)

        # ── Join Group card ──────────────────────────────
        join_card = ttk.Frame(body, style="Card.TFrame")
        join_card.pack(fill="x", padx=10, pady=(0, 6))

        join_form = ttk.Frame(join_card)
        join_form.pack(fill="x", padx=12, pady=10)
        join_form.columnconfigure(0, weight=1)

        join_header = ttk.Frame(join_form)
        join_header.pack(fill="x")
        ttk.Label(join_header, text="Join Group (Bulk)",
                  style="Header.TLabel").pack(side="left")
        self._join_count_var = tk.StringVar(value="")
        ttk.Label(join_header, textvariable=self._join_count_var,
                  style="Status.TLabel").pack(side="right")

        ttk.Separator(join_form, orient="horizontal").pack(fill="x", pady=(4, 8))

        ttk.Label(join_form, text="Group URLs (one per line):").pack(anchor="w")

        text_frame = ttk.Frame(join_form)
        text_frame.pack(fill="x", pady=(4, 8))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self._urls_text = tk.Text(text_frame, height=5, width=60,
                                  font=(theme.MONO_FONT, 9), wrap="word",
                                  borderwidth=1, relief="solid",
                                  highlightthickness=1,
                                  highlightbackground=theme.get()["border"])
        urls_scroll = ttk.Scrollbar(text_frame, orient="vertical",
                                    command=self._urls_text.yview)
        self._urls_text.configure(yscrollcommand=urls_scroll.set)
        urls_scroll.grid(row=0, column=1, sticky="ns")
        self._urls_text.grid(row=0, column=0, sticky="nsew")

        join_btn_frame = ttk.Frame(join_form)
        join_btn_frame.pack(fill="x")

        self.join_btn = ttk.Button(join_btn_frame, text="Join All Groups",
                                   command=self._on_join,
                                   style="Accent.TButton")
        self.join_btn.pack(side="left")

        self._join_status_var = tk.StringVar(value="")
        ttk.Label(join_btn_frame, textvariable=self._join_status_var,
                  style="Status.TLabel").pack(side="left", padx=(12, 0))

        # ── My Groups card ────────────────────────────────
        groups_card = ttk.Frame(body, style="Card.TFrame")
        groups_card.pack(fill="x", padx=10, pady=(0, 6))

        groups_form = ttk.Frame(groups_card)
        groups_form.pack(fill="x", padx=12, pady=10)
        groups_form.columnconfigure(0, weight=1)

        groups_header = ttk.Frame(groups_form)
        groups_header.pack(fill="x")
        ttk.Label(groups_header, text="My Groups",
                  style="Header.TLabel").pack(side="left")
        self._groups_count_var = tk.StringVar(value="")
        ttk.Label(groups_header, textvariable=self._groups_count_var,
                  style="Status.TLabel").pack(side="right")

        ttk.Separator(groups_form, orient="horizontal").pack(fill="x", pady=(4, 8))

        # ── Groups listbox (multi-select) ──
        groups_list_frame = ttk.Frame(groups_form)
        groups_list_frame.pack(fill="x", pady=(0, 4))
        groups_list_frame.columnconfigure(0, weight=1)
        groups_list_frame.rowconfigure(0, weight=1)

        self._groups_listbox = tk.Listbox(
            groups_list_frame, height=6, font=(theme.MONO_FONT, 9),
            selectmode="multiple", selectbackground=theme.get()["accent"],
            selectforeground="white", activestyle="none",
            borderwidth=1, relief="solid", highlightthickness=1,
            highlightbackground=theme.get()["border"])
        groups_scroll = ttk.Scrollbar(groups_list_frame, orient="vertical",
                                      command=self._groups_listbox.yview)
        self._groups_listbox.configure(yscrollcommand=groups_scroll.set)
        groups_scroll.grid(row=0, column=1, sticky="ns")
        self._groups_listbox.grid(row=0, column=0, sticky="nsew")
        self._clear_groups_hover = attach_listbox_hover(self._groups_listbox)

        # Internal list to map listbox index -> group data
        self._groups_data: list[dict] = []

        # ── Selection buttons row ──
        sel_frame = ttk.Frame(groups_form)
        sel_frame.pack(fill="x", pady=(0, 4))

        ttk.Button(sel_frame, text="Select All",
                   command=self._select_all_groups).pack(side="left")
        ttk.Button(sel_frame, text="Deselect All",
                   command=self._deselect_all_groups).pack(side="left", padx=(6, 0))

        self._sel_count_var = tk.StringVar(value="0 selected")
        ttk.Label(sel_frame, textvariable=self._sel_count_var,
                  style="Status.TLabel").pack(side="left", padx=(12, 0))

        # ── Action buttons row ──
        act_frame = ttk.Frame(groups_form)
        act_frame.pack(fill="x")

        self.send_join_btn = ttk.Button(
            act_frame, text="Send to Join",
            command=self._on_send_to_join)
        self.send_join_btn.pack(side="left")

        self.share_selected_btn = ttk.Button(
            act_frame, text="Share to Selected",
            command=self._on_share_to_selected,
            state="disabled")
        self.share_selected_btn.pack(side="left", padx=(8, 0))

        # ── Fetch / Load buttons row ──
        fetch_frame = ttk.Frame(groups_form)
        fetch_frame.pack(fill="x", pady=(8, 0))

        self.fetch_groups_btn = ttk.Button(
            fetch_frame, text="Fetch My Groups (All Profiles)",
            command=self._on_fetch_groups)
        self.fetch_groups_btn.pack(side="left")

        self.load_groups_btn = ttk.Button(
            fetch_frame, text="Load Saved",
            command=self._on_load_saved_groups)
        self.load_groups_btn.pack(side="left", padx=(8, 0))

        self._groups_status_var = tk.StringVar(value="")
        ttk.Label(fetch_frame, textvariable=self._groups_status_var,
                  style="Status.TLabel").pack(side="left", padx=(12, 0))

        # Bind selection change to update counter
        self._groups_listbox.bind("<<ListboxSelect>>", self._on_groups_select)

        # ── Bottom section: recent + saved ────────────────
        bottom_card = ttk.Frame(body, style="Card.TFrame")
        bottom_card.pack(fill="both", expand=True, padx=10, pady=(6, 10))

        bottom = ttk.Frame(bottom_card)
        bottom.pack(fill="both", expand=True, padx=12, pady=10)
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)
        bottom.rowconfigure(1, weight=1)

        # Recent Shares
        ttk.Label(bottom, text="Recent Shares:",
                  style="Heading.TLabel").grid(row=0, column=0, sticky="w",
                                               **pad)

        recent_frame = ttk.Frame(bottom)
        recent_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        recent_frame.columnconfigure(0, weight=1)
        recent_frame.rowconfigure(0, weight=1)

        r_scroll = ttk.Scrollbar(recent_frame, orient="vertical")
        self.shares_listbox = tk.Listbox(
            recent_frame, yscrollcommand=r_scroll.set,
            height=5, font=(theme.MONO_FONT, 9), borderwidth=0,
            highlightthickness=1, highlightbackground=theme.get()["border"],
            activestyle="none")
        r_scroll.config(command=self.shares_listbox.yview)
        r_scroll.grid(row=0, column=1, sticky="ns")
        self.shares_listbox.grid(row=0, column=0, sticky="nsew")
        self._clear_shares_hover = attach_listbox_hover(self.shares_listbox)

        # Saved Presets
        ttk.Label(bottom, text="Saved Presets:",
                  style="Heading.TLabel").grid(row=0, column=1, sticky="w",
                                               **pad)

        saved_top = ttk.Frame(bottom)
        saved_top.grid(row=0, column=1, sticky="e", **pad)
        ttk.Button(saved_top, text="Delete",
                   command=self._delete_saved).pack(side="right")

        saved_frame = ttk.Frame(bottom)
        saved_frame.grid(row=1, column=1, sticky="nsew", padx=(8, 0))
        saved_frame.columnconfigure(0, weight=1)
        saved_frame.rowconfigure(0, weight=1)

        s_scroll = ttk.Scrollbar(saved_frame, orient="vertical")
        self.saved_listbox = tk.Listbox(
            saved_frame, yscrollcommand=s_scroll.set,
            height=5, font=(theme.MONO_FONT, 9), borderwidth=0,
            highlightthickness=1, highlightbackground=theme.get()["border"],
            activestyle="none")
        s_scroll.config(command=self.saved_listbox.yview)
        s_scroll.grid(row=0, column=1, sticky="ns")
        self.saved_listbox.grid(row=0, column=0, sticky="nsew")
        self._clear_saved_hover = attach_listbox_hover(self.saved_listbox)
        self.saved_listbox.bind("<Double-Button-1>", self._on_saved_select)
        self.saved_listbox.bind("<Button-3>", self._on_saved_right_click)

        self._refresh_saved_listbox()

    # ── Properties ───────────────────────────────────────────


    @property
    def post_url(self):
        return self._vars["post_url"].get().strip()

    @property
    def group_name(self):
        return self._vars["group_name"].get().strip()

    # ── Public API ───────────────────────────────────────────

    def apply_theme(self, colors: dict):
        """Re-theme raw-tk widgets that aren't driven by ttk styles."""
        self._canvas.configure(bg=colors["bg"])
        for w in (self._groups_listbox, self.shares_listbox, self.saved_listbox):
            w.configure(bg=colors["list_bg"], fg=colors["list_fg"],
                        selectbackground=colors["list_select_bg"],
                        selectforeground=colors["list_select_fg"],
                        highlightbackground=colors["border"],
                        highlightcolor=colors["accent"])
        for w in (self._comment_text_widget, self._urls_text):
            w.configure(bg=colors["input_bg"], fg=colors["input_fg"],
                        highlightbackground=colors["border"],
                        highlightcolor=colors["accent"])
        for clear_hover in (self._clear_groups_hover, self._clear_shares_hover,
                            self._clear_saved_hover):
            if callable(clear_hover):
                clear_hover()

    def set_status(self, text: str):
        self._vars["status"].set(text)

    def set_share_enabled(self, enabled: bool):
        self.share_btn.config(state="normal" if enabled else "disabled")

    def set_timeline_enabled(self, enabled: bool):
        self.timeline_btn.config(state="normal" if enabled else "disabled")

    def set_on_share(self, callback):
        self._on_share_cb = callback

    def set_on_timeline(self, callback):
        self._on_timeline_cb = callback

    def set_on_join_group(self, callback):
        self._on_join_group_cb = callback

    def set_on_fetch_groups(self, callback):
        self._on_fetch_groups_cb = callback

    def set_on_load_groups(self, callback):
        self._on_load_groups_cb = callback

    def set_on_share_selected(self, callback):
        self._on_share_selected_cb = callback

    def set_on_bulk_share(self, callback):
        self._on_bulk_share_cb = callback

    def update_join_progress(self, done: int, total: int, last_msg: str = ""):
        self._join_count_var.set(f"{done}/{total}")
        if last_msg:
            self._join_status_var.set(last_msg)

    def add_recent_share(self, ok: bool, group_name: str, detail: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        icon = "\u2713" if ok else "\u2717"
        line = f"{icon} {group_name:<30} {timestamp}  {detail}"
        if hasattr(self, "_clear_shares_hover"):
            self._clear_shares_hover()
        self._recent_shares.append((timestamp, group_name, detail))
        self.shares_listbox.insert(0, line)
        while self.shares_listbox.size() > 100:
            self.shares_listbox.delete(tk.END)
        while len(self._recent_shares) > 100:
            self._recent_shares.pop(0)

    def clear_group_name(self):
        self._vars["group_name"].set("")

    def set_groups_list(self, groups: list[dict]):
        """Display deduplicated groups in the listbox.

        groups: list of dicts with keys: name, url, profiles (list of profile names)
        """
        if hasattr(self, "_clear_groups_hover"):
            self._clear_groups_hover()
        self._groups_listbox.delete(0, tk.END)
        self._groups_data = list(groups)
        for g in groups:
            name = g.get("name", "?")
            profiles = g.get("profiles", [])
            profile_str = ", ".join(profiles) if profiles else "?"
            line = f"{name:<40} [{profile_str}]"
            self._groups_listbox.insert(tk.END, line)
        self._groups_count_var.set(f"{len(groups)} group(s)")
        self._sel_count_var.set("0 selected")

    def set_groups_status(self, text: str):
        self._groups_status_var.set(text)

    def _on_fetch_groups(self):
        self.fetch_groups_btn.config(state="disabled")
        self._groups_status_var.set("Fetching groups...")
        self.set_status("Fetching groups from all profiles...")
        if self._on_fetch_groups_cb:
            self._on_fetch_groups_cb()

    def _on_load_saved_groups(self):
        if self._on_load_groups_cb:
            self._on_load_groups_cb()

    def _on_groups_select(self, event=None):
        sel = self._groups_listbox.curselection()
        count = len(sel)
        total = len(self._groups_data)
        self._sel_count_var.set(f"{count}/{total} selected")
        # Enable share button if post URL is set and groups are selected
        has_post = bool(self.post_url)
        self.share_selected_btn.config(
            state="normal" if (has_post and count > 0) else "disabled")

    def _select_all_groups(self):
        self._groups_listbox.select_set(0, tk.END)
        self._on_groups_select()

    def _deselect_all_groups(self):
        self._groups_listbox.selection_clear(0, tk.END)
        self._on_groups_select()

    def _get_selected_urls(self) -> list[str]:
        """Return URLs of currently selected groups."""
        urls = []
        for idx in self._groups_listbox.curselection():
            if idx < len(self._groups_data):
                url = self._groups_data[idx].get("url", "")
                if url:
                    urls.append(url)
        return urls

    def _get_selected_groups(self) -> list[dict]:
        """Return {name, url, profiles} dicts of currently selected groups."""
        groups = []
        for idx in self._groups_listbox.curselection():
            if idx < len(self._groups_data):
                g = self._groups_data[idx]
                if g.get("name"):
                    groups.append({
                        "name": g["name"],
                        "url": g.get("url", ""),
                        "profiles": g.get("profiles", []),
                    })
        return groups

    def _on_send_to_join(self):
        """Copy selected group URLs into the Join Group text box."""
        urls = self._get_selected_urls()
        if not urls:
            self.set_status("No groups selected")
            return
        self._urls_text.delete("1.0", tk.END)
        self._urls_text.insert("1.0", "\n".join(urls))
        self._join_count_var.set(f"0/{len(urls)}")
        self._join_status_var.set(f"{len(urls)} group(s) loaded")
        self.set_status(f"Sent {len(urls)} group(s) to Join box")

    def _on_share_to_selected(self):
        """Share the current post URL to all selected groups by name."""
        groups = self._get_selected_groups()
        if not groups:
            self.set_status("No groups selected")
            return
        if not self.post_url:
            self.set_status("Enter a Post URL first")
            return
        self.share_selected_btn.config(state="disabled")
        self.set_status(f"Sharing to {len(groups)} group(s)...")
        if self._on_share_selected_cb:
            self._on_share_selected_cb(self.post_url, groups,
                                       self.comment_text, self.reaction)

    # ── Internal: state ──────────────────────────────────────

    def _update_share_state(self, *_):
        group_ready = bool(self.post_url and self.group_name)
        timeline_ready = bool(self.post_url)
        bulk_ready = bool(self.post_url)
        self._vars["can_share"].set(group_ready)
        self.share_btn.config(state="normal" if group_ready else "disabled")
        self.save_btn.config(state="normal" if group_ready else "disabled")
        self.timeline_btn.config(state="normal" if timeline_ready else "disabled")
        self.bulk_share_btn.config(state="normal" if bulk_ready else "disabled")

    @property
    def comment_text(self):
        """Get comment text from the Text widget. Returns all lines as a single string."""
        if self._comment_text_widget:
            return self._comment_text_widget.get("1.0", tk.END).strip()
        return ""
    
    @property
    def comment_lines(self):
        """Get comment text as a list of lines (one per line)."""
        text = self.comment_text
        if not text:
            return []
        return [line.strip() for line in text.splitlines() if line.strip()]

    @property
    def reaction(self):
        val = self._vars["reaction"].get().strip().lower()
        return None if val == "none" else val

    def _on_share(self):
        if not self.post_url or not self.group_name:
            return
        self.set_share_enabled(False)
        self.set_status("Sharing...")
        if self._on_share_cb:
            self._on_share_cb(self.post_url, self.group_name,
                               self.comment_text, self.reaction)

    def _on_share_timeline(self):
        if not self.post_url:
            return
        self.set_timeline_enabled(False)
        self.set_status("Posting to Timeline...")
        if self._on_timeline_cb:
            self._on_timeline_cb(self.post_url,
                                  self.comment_text, self.reaction)

    def _on_bulk_share_to_groups(self):
        """Share the post URL from the form to all selected groups across all profiles."""
        if not self.post_url:
            self.set_status("Enter a Post URL first")
            return
        groups = self._get_selected_groups()
        if not groups:
            self.set_status("Select groups from My Groups first")
            return
        self.bulk_share_btn.config(state="disabled")
        self.share_selected_btn.config(state="disabled")
        self.set_status(f"Bulk sharing to {len(groups)} group(s) across all profiles...")
        if self._on_bulk_share_cb:
            self._on_bulk_share_cb(self.post_url, groups,
                                   self.comment_text, self.reaction)

    def _on_join(self):
        raw = self._urls_text.get("1.0", tk.END).strip()
        if not raw:
            return
        urls = [line.strip() for line in raw.splitlines()
                if line.strip().startswith("http")]
        if not urls:
            return
        self.join_btn.config(state="disabled")
        self._join_count_var.set(f"0/{len(urls)}")
        self._join_status_var.set(f"Joining {len(urls)} group(s)...")
        self.set_status(f"Joining {len(urls)} group(s)...")
        if self._on_join_group_cb:
            self._on_join_group_cb(urls)

    # ── Internal: saved presets ──────────────────────────────

    def _load_saved(self):
        try:
            if SAVED_FILE.exists():
                self._saved_presets = json.loads(SAVED_FILE.read_text())
        except Exception:
            self._saved_presets = []

    def _persist_saved(self):
        SAVED_FILE.parent.mkdir(parents=True, exist_ok=True)
        SAVED_FILE.write_text(json.dumps(self._saved_presets, indent=2))

    def _refresh_saved_listbox(self):
        if hasattr(self, "_clear_saved_hover"):
            self._clear_saved_hover()
        self.saved_listbox.delete(0, tk.END)
        for p in self._saved_presets:
            cmt = p.get("comment", "") or ""
            rxn = p.get("reaction") or ""
            tags = []
            if rxn:
                tags.append(rxn)
            if cmt:
                tags.append("cmt")
            tag_str = f" [{','.join(tags)}]" if tags else ""
            line = f"{p['group']:<25}{tag_str} | {p['url']}"
            self.saved_listbox.insert(tk.END, line)

    def _make_preset(self):
        return {
            "url": self.post_url,
            "group": self.group_name,
            "comment": self.comment_text,
            "reaction": self.reaction,
        }

    def _save_preset(self):
        url = self.post_url
        group = self.group_name
        if not url or not group:
            return
        for p in self._saved_presets:
            if p["url"] == url and p["group"] == group:
                self.set_status("Already saved")
                return
        self._saved_presets.append(self._make_preset())
        self._persist_saved()
        self._refresh_saved_listbox()
        self.set_status(f"Saved: {group}")

    def _on_saved_select(self, event):
        sel = self.saved_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self._load_idx(idx)

    def _on_saved_right_click(self, event):
        idx = self.saved_listbox.nearest(event.y)
        if idx < 0 or idx >= len(self._saved_presets):
            return
        self.saved_listbox.selection_clear(0, tk.END)
        self.saved_listbox.selection_set(idx)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Load", command=lambda: self._load_idx(idx))
        menu.add_command(label="Delete", command=self._delete_saved)
        menu.tk_popup(event.x_root, event.y_root)

    def _load_idx(self, idx: int):
        p = self._saved_presets[idx]
        self._vars["post_url"].set(p["url"])
        self._vars["group_name"].set(p["group"])
        
        # Load comment into Text widget
        if self._comment_text_widget:
            self._comment_text_widget.delete("1.0", tk.END)
            comment = p.get("comment", "")
            if comment:
                self._comment_text_widget.insert("1.0", comment)
        
        self._vars["reaction"].set(p.get("reaction", "none") or "none")
        self.set_status(f"Loaded: {p['group']}")

    def _delete_saved(self):
        sel = self.saved_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        p = self._saved_presets[idx]
        label = f"{p['group']}"
        if not messagebox.askyesno("Delete Preset", f"Delete preset '{label}'?"):
            return
        del self._saved_presets[idx]
        self._persist_saved()
        self._refresh_saved_listbox()
        self.set_status(f"Deleted: {label}")
