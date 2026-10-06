"""An unattended re-login stays hidden, even with the watch-the-wave grid on.

`login_window_grid` means one thing: "tile the login wave I asked to watch."
An operator sets it before a Login-requested wave so the windows land in a
grid instead of stacking. It must not reach a re-login that nobody asked for
- the one that fires mid comment/react/share run when Facebook expires a
session, and the background sweep. Those have no slot in anyone's grid, and a
full Brave window thrown onto the desktop mid-run is exactly what the hidden
browser exists to avoid.

So the window follows the slot, not the global grid: a re-login with a slot
(the Login-requested wave) tiles and is watched; a re-login with no slot
stays headless/offscreen whatever the grid setting says.
"""
import asyncio
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("relogin hidden without slot")  # noqa: F821

import src.core.driver_manager as dm  # noqa: E402
from src.core import browser_choice as bc  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402
from src.storage import database as db  # noqa: E402

USER = "verify_hidden@example.com"
PROFILE = "VerifyHiddenRelogin"

# The case under test is the grid turned ON: that is the setting that used to
# leak a visible window into a slotless re-login.
_saved_grid = cfg.get_setting(bc.GRID_KEY, None)
cfg.save_setting(bc.GRID_KEY, "1")
_real_path = cfg.get_profile_path
_real_auto = None


class _FakeAuto:
    """Records how each browser was opened. The login always succeeds on the
    first try, so only the opening args are under test."""

    opened = []          # (headless, tile) per start_browser

    def __init__(self, log_callback=print):
        self.context = None
        self.page = None

    async def start_browser(self, path, headless=True, flags=None, tile=None):
        _FakeAuto.opened.append((headless, tile))

    async def go_to_facebook(self):
        return True

    async def quit(self):
        return None


try:
    db.upsert_account(880, "Hidden", USER, password="pw")
    db.link_account(USER, PROFILE)
    cfg.get_profile_path = lambda name: "C:/verify/" + str(name)
    import src.core.facebook_automation as fa
    _real_auto = fa.FacebookAutomation
    fa.FacebookAutomation = _FakeAuto

    m = dm.DriverManager()
    m.log = lambda message: None
    m._fast_tests = True
    m._record_and_publish = lambda *a, **k: asyncio.sleep(0)
    # Session already live: the re-login just opens the browser and confirms,
    # so start_browser is called exactly once per call with the args at test.
    m._session_is_live = staticmethod(lambda auto: asyncio.sleep(0, result=True))

    # 1. No slot - the mid-run re-login and the background sweep. Must be
    #    hidden (headless=True, no tile) despite the grid being on.
    _FakeAuto.opened.clear()
    asyncio.run(m._relogin_profile(PROFILE, why="Session expired"))
    if _FakeAuto.opened != [(True, None)]:
        failures.append(  # noqa: F821
            f"relogin hidden without slot: a slotless re-login with the grid "
            f"on must open hidden (headless=True, tile=None), got "
            f"{_FakeAuto.opened}")

    # 2. With a slot - the Login-requested wave the operator is watching. Must
    #    stay visible and tiled, unchanged by this fix.
    _FakeAuto.opened.clear()
    asyncio.run(m._relogin_profile(PROFILE, why="Login requested",
                                   slot=3, wave=25))
    if _FakeAuto.opened != [(False, (3, 25))]:
        failures.append(  # noqa: F821
            f"relogin hidden without slot: a slotted re-login must stay a "
            f"visible tile (headless=False, tile=(3,25)), got "
            f"{_FakeAuto.opened}")
finally:
    cfg.get_profile_path = _real_path
    if _saved_grid is None:
        conf = cfg._load_config()
        conf.pop(bc.GRID_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.GRID_KEY, _saved_grid)
    if _real_auto is not None:
        import src.core.facebook_automation as fa
        fa.FacebookAutomation = _real_auto
    conn = db._get_conn()
    conn.execute("DELETE FROM accounts WHERE username=?", (USER,))
    conn.commit()

print("FAILED" if [f for f in failures  # noqa: F821
                   if "relogin hidden without slot" in f] else "ok")
