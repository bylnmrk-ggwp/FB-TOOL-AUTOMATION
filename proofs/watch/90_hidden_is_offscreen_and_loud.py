"""A hidden window never reaches the screen, and a watch never shrinks quietly.

Two faults, both found while watching a real live.

Hiding a window means minimising a real one, because Chromium's headless
engines announce HeadlessChrome and Facebook answers that with a captcha
(proofs/85). But minimising happens through CDP, which needs the window to
exist first - so every hidden launch flashed a Brave window onto the
operator's desktop and then put it down. Launching off-screen leaves nothing
to flash.

Separately, `_revive_watcher` pops a profile out of `_watch_autos` before
rebuilding its page and used to return False without putting anything back.
Profiles left the broadcast one at a time in silence, and when the last one
went the keeper hit a bare `return` - so a watch meant to run until the live
ended stopped with NOTHING in the log. That is the exact failure the revive
docstring says it exists to prevent.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("hidden is offscreen and loud")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.core.facebook_automation import (  # noqa: E402
    OFFSCREEN_POSITION,
    SMALL_VIEWPORT,
    FacebookAutomation,
)

# ── A hidden launch puts the window outside every monitor ──

if "--window-position=" not in OFFSCREEN_POSITION:
    failures.append("hidden is offscreen and loud: OFFSCREEN_POSITION is not a "  # noqa: F821
                    "window-position flag")
else:
    x, _, y = OFFSCREEN_POSITION.split("=", 1)[1].partition(",")
    if int(x) > -10000 or int(y) > -10000:
        failures.append(f"hidden is offscreen and loud: {OFFSCREEN_POSITION} is "  # noqa: F821
                        f"not far enough off-screen to clear a monitor")

mode, headless, args = DriverManager._browser_launch_mode(SMALL_VIEWPORT)
if mode != "headless_new":
    failures.append(f"hidden is offscreen and loud: the default browser mode is "  # noqa: F821
                    f"{mode!r}, so this proof is testing the wrong path")
if headless:
    failures.append("hidden is offscreen and loud: the hidden mode asks Chromium "  # noqa: F821
                    "for headless, which announces HeadlessChrome to Facebook")
if OFFSCREEN_POSITION not in args:
    failures.append("hidden is offscreen and loud: a hidden launch does not "  # noqa: F821
                    "place its window off-screen, so a real Brave window "
                    "flashes on the desktop before it is minimised")

# A visible run is asked for on purpose: it must NOT be hidden off-screen.
import src.storage.config_manager as cfg  # noqa: E402

_real_get = cfg.get_setting
cfg.get_setting = lambda key, default=None: (
    "visible" if key == "browser_mode" else _real_get(key, default))
try:
    _, _, visible_args = DriverManager._browser_launch_mode(SMALL_VIEWPORT)
finally:
    cfg.get_setting = _real_get
if OFFSCREEN_POSITION in visible_args:
    failures.append("hidden is offscreen and loud: 'Visible windows' puts its "  # noqa: F821
                    "windows off-screen, so the operator sees nothing at all")

# The login/queue path opens its own persistent context and has the same
# choice to make.
start = inspect.getsource(FacebookAutomation.start_browser)
if "OFFSCREEN_POSITION" not in start:
    failures.append("hidden is offscreen and loud: start_browser still opens a "  # noqa: F821
                    "hidden window at a visible position")
if "--window-position=50,50" not in start:
    failures.append("hidden is offscreen and loud: start_browser no longer "  # noqa: F821
                    "places a window a human is meant to see")

# ── A profile that leaves the watch says so ──

revive = inspect.getsource(DriverManager._revive_watcher)
pop_at = revive.index("_watch_autos.pop(")
tail = revive[pop_at:]
if "self.log(" not in tail:
    failures.append("hidden is offscreen and loud: a rebuild that fails after "  # noqa: F821
                    "the page was popped says nothing, so the profile leaves "
                    "the broadcast silently")

keeper = inspect.getsource(DriverManager._keep_watching)
empty_at = keeper.index("if not self._watch_autos:")
after = keeper[empty_at:empty_at + 400]
if "self.log(" not in after.split("return")[0]:
    failures.append("hidden is offscreen and loud: the keeper ends the watch "  # noqa: F821
                    "with no log line when the last page has gone")

print("FAILED" if [f for f in failures  # noqa: F821
                   if "hidden is offscreen and loud" in f] else "ok")
