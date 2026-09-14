"""A watch sized to the machine, and pages that carry only the video.

46 visible pages took 14 minutes to open, 22 of them ever played, and the
desktop stopped responding. Two causes, both addressed here: every page was
loading a full Facebook page - feed images, web fonts, a heap sized for an
app nobody is driving - and nothing checked whether the machine had the RAM
for the number of pages asked for.

The savings are browser-level switches on purpose. A page.route() handler
would send every media segment of every stream through this Python process,
which is the traffic a watch cannot afford to queue behind.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("watch memory")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.core.facebook_automation import MEMORY_FLAGS, WATCH_FLAGS  # noqa: E402

joined = " ".join(WATCH_FLAGS)
for flag, why in (
        ("--disable-remote-fonts", "web fonts are still downloaded"),
        ("--mute-audio", "every page decodes audio nobody hears"),
        ("--disable-breakpad", "the crash reporter still runs per page")):
    if flag not in joined:
        failures.append(f"watch memory: {why}")  # noqa: F821

# Two savings are forbidden, both measured on a live broadcast: a JS heap cap
# freezes players at readyState 2 while paused stays false, and turning
# images off takes Facebook's own player chrome with it.
for flag, why in (
        ("--js-flags", "a JS heap cap starves the decoder and freezes players"),
        ("imagesEnabled=false", "turning images off breaks Facebook's player")):
    if flag in joined:
        failures.append(f"watch memory: {why}")  # noqa: F821

# One renderer for every page stalled 3-4 of 9 the same way.
if "--renderer-process-limit=1" in WATCH_FLAGS:
    failures.append("watch memory: every watch page is back in one renderer, which "  # noqa: F821
                    "froze players mid-stream")

# No page.route() on a watch page: that is the traffic this cannot afford.
from src.core.facebook_automation import FacebookAutomation  # noqa: E402
init = inspect.getsource(FacebookAutomation.init_from_storage)
if "block_resources" not in init:
    failures.append("watch memory: init_from_storage lost its switch for skipping "  # noqa: F821
                    "request interception")

# The fleet is sized to the machine, not to the roster.
watch = inspect.getsource(DriverManager._do_watch)
if "_pages_that_fit" not in watch:
    failures.append("watch memory: the watch opens as many pages as it is asked "  # noqa: F821
                    "for, whatever the machine has")
fits = DriverManager._pages_that_fit(DriverManager.__new__(DriverManager))
if fits is not None and fits < 1:
    failures.append(f"watch memory: the cap came back as {fits}, which would open "  # noqa: F821
                    f"nothing")
if DriverManager.WATCH_PAGE_MB < 50 or DriverManager.WATCH_RESERVE_MB < 512:
    failures.append("watch memory: the per-page cost or the reserve is too small to "  # noqa: F821
                    "keep the desktop responsive")

print("FAILED" if [f for f in failures if "watch memory" in f] else "ok")  # noqa: F821
