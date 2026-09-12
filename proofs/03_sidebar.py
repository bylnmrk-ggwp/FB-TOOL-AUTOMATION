"""Proof: the Sidebar widget builds on a withdrawn root with animations
forced off, selects through its <Button-1> binding, collapses to 56 px,
expands to 220 px, and re-themes in both modes. Run by verify.py with
globals failures, step and ROOT."""
import re
import sys
sys.path.insert(0, str(ROOT))

step("sidebar")
import tkinter as _tk
from src.ui import effects as _fx
from src.ui import theme as _theme
from src.ui.sidebar import Sidebar as _Sidebar


def _click(widget):
    """Run widget's <Button-1> binding as Tk would on a real click.

    Tk 8.6.15 on Windows drops every event_generate() aimed at a widget
    under a withdrawn toplevel (checked: even virtual events), and the
    proof must not map a window. So eval the bound script itself: %# needs
    an int, %W the widget path; Tkinter's Event substitution accepts ??
    for every other field.
    """
    script = widget.bind("<Button-1>")
    if not script:
        failures.append(f"sidebar item {widget!r} has no <Button-1> binding")
        return
    script = script.replace("%#", "0").replace("%W", str(widget))
    widget.tk.eval(re.sub(r"%[a-zA-Z]", "??", script))


_root = _tk.Tk(); _root.withdraw()
_fx.set_animations_override(False)
_sb = _Sidebar(_root, px=lambda n: n)
_sb.pack(side="left", fill="y")
_picked = []
_sb.set_on_select(_picked.append)
for _k, _l in (("dashboard", "Dashboard"), ("queue", "Queue")):
    _sb.add_item(_k, _l, chr(0xE80F), chr(0x25A3))
_sb.set_active("queue")
_root.update_idletasks()
if _sb.active != "queue":
    failures.append("sidebar.set_active did not stick")
_item = _sb._items["dashboard"]
for _w in (_item, *_item.winfo_children()):
    if "<Button-1>" not in _w.bind():
        failures.append(f"sidebar item child {_w.winfo_class()} not clickable")
_click(_item)
_root.update()
if _picked != ["dashboard"] or _sb.active != "dashboard":
    failures.append(f"sidebar select callback not fired: {_picked}")
_sb.set_collapsed(True, animate=False); _root.update_idletasks()
if _sb.winfo_reqwidth() != 56 or not _sb.collapsed:
    failures.append(f"sidebar collapsed width {_sb.winfo_reqwidth()}")
if any(p["label"].winfo_manager() for p in _sb._parts.values()):
    failures.append("sidebar labels still packed while collapsed")
_sb.set_collapsed(False, animate=False); _root.update_idletasks()
if _sb.winfo_reqwidth() != 220:
    failures.append(f"sidebar expanded width {_sb.winfo_reqwidth()}")
if not all(p["label"].winfo_manager() == "pack" for p in _sb._parts.values()):
    failures.append("sidebar labels not restored after expand")
for _mode in ("light", "dark"):
    _theme.set_mode(_mode); _sb.apply_theme(_theme.get())
_theme.set_mode("light")
_fx.set_animations_override(None); _root.destroy()
print("ok" if not [f for f in failures if "sidebar" in f] else "FAILED")
