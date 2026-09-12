"""Proof: effects.tween runs to completion on the Tk clock, is synchronous
with animations off, and blend/ease_out_cubic hit their endpoints. Run by
verify.py with globals failures, step and ROOT."""
import sys
sys.path.insert(0, str(ROOT))

step("effects.tween")
import tkinter as _tk
from src.ui import effects as _fx
_root = _tk.Tk(); _root.withdraw()
_seen = []
_fx.set_animations_override(True)
_fx.tween(_root, 60, lambda t: _seen.append(t), done=lambda: _seen.append("done"),
          easing=_fx.linear)
_t0 = _root.after(400, _root.quit); _root.mainloop(); _root.after_cancel(_t0)
if not _seen or _seen[-1] != "done" or _seen[-2] != 1.0 or len(_seen) < 3:
    failures.append(f"tween did not run to completion: {_seen}")
if any(_seen[i] > _seen[i + 1] for i in range(len(_seen) - 2)):
    failures.append(f"tween not monotonic: {_seen}")
_seen.clear(); _fx.set_animations_override(False)
_fx.tween(_root, 60, lambda t: _seen.append(t), done=lambda: _seen.append("done"))
if _seen != [1.0, "done"]:
    failures.append(f"tween with animations off must be synchronous: {_seen}")
if _fx.blend("#000000", "#ffffff", 0.5) != "#808080":
    failures.append(f"blend wrong: {_fx.blend('#000000', '#ffffff', 0.5)}")
if _fx.ease_out_cubic(0) != 0 or _fx.ease_out_cubic(1) != 1:
    failures.append("ease_out_cubic endpoints")
_fx.set_animations_override(None); _root.destroy()
print("ok" if not [f for f in failures if "tween" in f or "blend" in f or "ease" in f] else "FAILED")
