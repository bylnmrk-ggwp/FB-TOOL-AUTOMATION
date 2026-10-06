"""A one-account watch opens that account's own Brave profile, not a copy.

The fleet watch copies each session (extract_storage_state) and injects it
into one shared browser so many pages fit past Brave's singleton lock. But a
copied session cannot carry Brave 154's app-bound-encrypted cookies, so a
healthy account injects as logged out - which is why a watch of 24 showed 7
playing and 17 "logged out or session expired".

For a single account there is no concurrency to buy: opening its own Brave
User Data directory directly - exactly what a queue run does - is reliable
and there is nothing to copy. So a watch that targets one profile takes that
own-profile path, and a watch of many still takes the shared-browser copy
path.
"""
import asyncio
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("one account uses own profile")  # noqa: F821

import src.core.driver_manager as dm  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402

URL = "https://www.facebook.com/share/v/TEST/"
P1, P2 = "WatchOwnA", "WatchOwnB"
BRAVE = {P1: "C:/brave/WatchOwnA", P2: "C:/brave/WatchOwnB"}

_real_get_path = cfg.get_profile_path


class _StopCopy(Exception):
    """Raised from the fake extract to stop the multi path before it launches
    a real browser - its arrival proves the copy path was taken."""


class _Page:
    async def goto(self, *a, **k):
        return None

    async def evaluate(self, *a, **k):
        return True


class _FakeAuto:
    """Records which launch path each watch took."""

    started = []      # profile paths passed to start_browser (own-profile)
    extracted = []    # profiles whose session was copied (fleet path)

    def __init__(self, log_callback=print, debug=False):
        self.page = _Page()

    async def start_browser(self, profile_path, headless=True, flags=None, tile=None):
        _FakeAuto.started.append(profile_path)

    async def extract_storage_state(self, profile_path, skip_navigation=False):
        _FakeAuto.extracted.append(profile_path)
        raise _StopCopy()

    async def quit(self):
        return None

    async def close_context(self):
        return None


try:
    cfg.get_profile_path = lambda name: BRAVE.get(name)
    import src.core.facebook_automation as fa
    _real_auto = fa.FacebookAutomation
    fa.FacebookAutomation = _FakeAuto

    m = dm.DriverManager()
    m.log = lambda message: None
    m._debug = False
    # Keep the single path off a real browser and off the keeper loop.
    m._verify_watching = lambda auto, name, settle_ms=None: asyncio.sleep(0, result="playing")
    m._keep_watching = lambda url, deadline=None: asyncio.sleep(0)
    m._report_task_death = lambda what: (lambda *a, **k: None)
    m._pages_that_fit = lambda: 50

    # 1. One profile -> own-profile path: start_browser on its Brave dir, and
    #    no session copied.
    _FakeAuto.started.clear()
    _FakeAuto.extracted.clear()
    asyncio.run(m._do_watch(URL, minutes=1, profile_names=[P1]))
    if _FakeAuto.started != [BRAVE[P1]]:
        failures.append(  # noqa: F821
            f"one account uses own profile: a single-account watch must open "
            f"its own Brave dir {BRAVE[P1]!r}, got started={_FakeAuto.started}")
    if _FakeAuto.extracted:
        failures.append(  # noqa: F821
            f"one account uses own profile: a single-account watch copied a "
            f"session instead of opening the profile: {_FakeAuto.extracted}")
    if m._watch_autos.get(P1) is None:
        failures.append(  # noqa: F821
            "one account uses own profile: the account was not registered as a "
            "watch page, so Stop and the keeper cannot see it")

    # 2. Two profiles -> fleet copy path: sessions are extracted, own-profile
    #    start_browser is not used to open them.
    asyncio.run(m._stop_watch())
    _FakeAuto.started.clear()
    _FakeAuto.extracted.clear()
    asyncio.run(m._do_watch(URL, minutes=1, profile_names=[P1, P2]))
    if not _FakeAuto.extracted:
        failures.append(  # noqa: F821
            "one account uses own profile: a multi-account watch must still "
            "copy sessions (the shared-browser path), but none were extracted")
    if _FakeAuto.started:
        failures.append(  # noqa: F821
            f"one account uses own profile: a multi-account watch opened an "
            f"own profile directly: {_FakeAuto.started}")
finally:
    cfg.get_profile_path = _real_get_path
    try:
        import src.core.facebook_automation as fa
        fa.FacebookAutomation = _real_auto
    except Exception:
        pass

print("FAILED" if [f for f in failures  # noqa: F821
                   if "one account uses own profile" in f] else "ok")
