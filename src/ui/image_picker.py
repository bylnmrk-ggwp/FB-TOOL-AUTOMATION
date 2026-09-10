import os
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from src.ui import theme

# Try to load PIL for thumbnail generation; fall back gracefully
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ImagePickerDialog:
    """Modal dialog for previewing downloaded Pinterest images and picking which
    to use as profile picture.

    Shows image thumbnails in a scrollable grid. The user selects an image
    via combobox dropdown, then clicks "Apply" to confirm.
    """

    def __init__(self, parent, profile_name: str, images: list[str],
                 needs_pic: bool = True):
        self._result: dict | None = None  # set when user clicks Apply

        self._dialog = tk.Toplevel(parent)
        self._dialog.title(f"Select Profile Picture — {profile_name}")
        self._dialog.geometry("700x520")
        self._dialog.resizable(True, True)
        self._dialog.minsize(500, 400)
        self._dialog.transient(parent)
        self._dialog.grab_set()

        self._images = images
        self._profile_name = profile_name
        self._needs_pic = needs_pic
        self._thumb_refs: list[tk.PhotoImage | ImageTk.PhotoImage] = []  # keep refs alive

        self._build_ui()
        self._center_on_parent(parent)

    # ── Result ────────────────────────────────────────────────

    @property
    def result(self) -> dict | None:
        """Return {'profile_pic': path, 'cancel': bool} or None."""
        return self._result

    # ── UI ─────────────────────────────────────────────────────

    def _build_ui(self):
        pad = {"padx": 12, "pady": 4}

        # Header
        header = ttk.Frame(self._dialog)
        header.pack(fill="x", **pad)

        ttk.Label(header, text=f"Pinterest Images — {self._profile_name}",
                  font=(theme.UI_FONT, 12, "bold")).pack(anchor="w")
        ttk.Label(header,
                  text="Select which image to use as your profile picture.",
                  foreground=theme.get()["muted"]).pack(anchor="w")

        # Selection control
        ctrl = ttk.Frame(self._dialog)
        ctrl.pack(fill="x", **pad)
        ctrl.columnconfigure(1, weight=1)

        # Profile pic combobox
        ttk.Label(ctrl, text="Profile Picture:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        image_names = [f"Image {i+1} — {Path(p).name[:30]}" for i, p in enumerate(self._images)]
        self._pic_var = tk.StringVar(value=image_names[0] if self._images and self._needs_pic else "None")
        self._pic_combo = ttk.Combobox(
            ctrl, textvariable=self._pic_var,
            values=["None"] + image_names,
            state="readonly", width=50)
        self._pic_combo.grid(row=0, column=1, sticky="ew")
        if not self._needs_pic:
            self._pic_combo.config(state="disabled")
            self._pic_var.set("Already has photo")

        # Thumbnails canvas area
        canvas_frame = ttk.Frame(self._dialog)
        canvas_frame.pack(fill="both", expand=True, **pad)
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)

        canvas = tk.Canvas(canvas_frame, borderwidth=0, highlightthickness=0,
                          bg=theme.get()["canvas_bg"])
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollable = ttk.Frame(canvas)
        scrollable.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))

        canvas_window = canvas.create_window((0, 0), window=scrollable,
                                            anchor="nw", tags="inner")

        def _configure_canvas(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _configure_canvas)

        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Wheel scrolling via the app-wide router — a local unbind_all here
        # used to break wheel scrolling for the whole app after the dialog
        # closed.
        from src.ui.effects import register_wheel_target
        register_wheel_target(canvas)

        # Populate thumbnails
        cols = 3
        self._thumb_refs.clear()
        for idx, img_path in enumerate(self._images):
            row, col = divmod(idx, cols)
            frame = ttk.Frame(scrollable, relief="solid", borderwidth=1)
            frame.grid(row=row, column=col, padx=6, pady=6, sticky="nsew")

            # Thumbnail
            thumb_w, thumb_h = 180, 140
            thumbnail = self._make_thumbnail(img_path, thumb_w, thumb_h)

            if thumbnail:
                lbl = ttk.Label(frame, image=thumbnail)
                lbl.image = thumbnail  # keep ref
                lbl.pack(padx=4, pady=(4, 0))
                self._thumb_refs.append(thumbnail)
            else:
                # Fallback: show filename and size
                try:
                    size = os.path.getsize(img_path)
                    size_str = f"{size / 1024:.0f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
                except Exception:
                    size_str = "?"
                lbl = ttk.Label(frame, text=f"{Path(img_path).name}\n{size_str}",
                               foreground=theme.get()["muted"], justify="center")
                lbl.pack(padx=4, pady=10)

            # Image number label
            ttk.Label(frame, text=f"Image {idx+1}",
                     font=(theme.UI_FONT, 9, "bold"),
                     foreground=theme.get()["heading"]).pack(pady=(2, 4))

        # Ensure columns expand equally
        for c in range(cols):
            scrollable.columnconfigure(c, weight=1)

        # Bottom buttons
        btn_frame = ttk.Frame(self._dialog)
        btn_frame.pack(fill="x", **pad)

        status_var = tk.StringVar(value="Pick an image then click Apply")
        if not self._needs_pic:
            status_var.set("Profile already has a picture — no selection needed")
        ttk.Label(btn_frame, textvariable=status_var,
                 foreground=theme.get()["muted"]).pack(side="left", padx=(0, 12))

        ttk.Button(btn_frame, text="Cancel",
                  command=self._on_cancel).pack(side="right", padx=(6, 0))
        ttk.Button(btn_frame, text="Apply & Upload",
                  command=self._on_apply,
                  style="Accent.TButton").pack(side="right")

    def _make_thumbnail(self, img_path: str, width: int, height: int):
        """Create a PhotoImage thumbnail from an image file."""
        if not os.path.isfile(img_path):
            return None
        try:
            if HAS_PIL:
                img = Image.open(img_path)
                img.thumbnail((width, height), Image.LANCZOS)
                return ImageTk.PhotoImage(img)
            else:
                # Without PIL, try tkinter's built-in support (limited formats)
                return tk.PhotoImage(file=img_path)
        except Exception:
            return None

    def _center_on_parent(self, parent):
        self._dialog.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        dw = self._dialog.winfo_width()
        dh = self._dialog.winfo_height()
        x = px + (pw - dw) // 2
        y = py + (ph - dh) // 2
        self._dialog.geometry(f"+{x}+{y}")

    # ── Handlers ──────────────────────────────────────────────

    def _get_selected_path(self, var: tk.StringVar) -> str | None:
        """Extract the actual file path from a combobox selection like 'Image 3 — ...'."""
        val = var.get()
        if val == "None" or val == "Already has photo":
            return None
        try:
            idx_str = val.split(" —")[0].replace("Image ", "")
            idx = int(idx_str) - 1
            if 0 <= idx < len(self._images):
                return self._images[idx]
        except (ValueError, IndexError):
            pass
        # Fall back to first image if parsing fails
        return self._images[0] if self._images else None

    def _on_apply(self):
        self._result = {
            "profile_pic": self._get_selected_path(self._pic_var) if self._needs_pic else None,
            "cancel": False,
        }
        self._dialog.destroy()

    def _on_cancel(self):
        self._result = {"cancel": True}
        self._dialog.destroy()

    def show(self) -> dict | None:
        """Show the dialog modally and return the result."""
        self._dialog.wait_window()
        return self._result
