"""A background run stays headless, except the one account that hits a captcha.

The whole login run is headless so the PC stays usable. A captcha is the one
failure a person can clear in seconds, and nothing headless can be clicked -
so that account alone is reopened in a visible tile and logged in again
there, while the rest of the wave never leaves the background.
"""
import asyncio
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("captcha window")  # noqa: F821

import src.core.driver_manager as dm  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402
from src.storage import database as db  # noqa: E402

USER = "verify_cap@example.com"
PROFILE = "VerifyCaptcha"

_real_path = cfg.get_profile_path
_real_creds = db.credentials_for_profile
_real_auto = None


class _FakeAuto:
    """Records how each browser was opened and what each login attempt said."""

    opened = []          # (headless, tile) per start_browser
    attempts = 0

    def __init__(self, log_callback=print):
        self.context = None
        self.page = None

    async def start_browser(self, path, headless=True, flags=None, tile=None):
        _FakeAuto.opened.append((headless, tile))

    async def go_to_facebook(self):
        return True

    async def login_with_credentials(self, email, password, wait_for_2fa=True):
        _FakeAuto.attempts += 1
        if _FakeAuto.attempts == 1:
            # Headless: the picture challenge cannot be answered here.
            return False, "captcha - solve it in the window"
        return True, "Logged in successfully"

    async def _classify_account_access(self):
        return "unknown"

    async def quit(self):
        return None


try:
    db.upsert_account(870, "Cap", USER, password="pw")
    db.link_account(USER, PROFILE)
    cfg.get_profile_path = lambda name: "C:/verify/" + str(name)
    import src.core.facebook_automation as fa
    _real_auto = fa.FacebookAutomation
    fa.FacebookAutomation = _FakeAuto

    m = dm.DriverManager()
    m.log = lambda message: None
    m._fast_tests = True
    m._record_and_publish = lambda *a, **k: asyncio.sleep(0)
    m._session_is_live = staticmethod(lambda auto: asyncio.sleep(0, result=False))
    m._wait_session_live = lambda auto, seconds=None, poll=2.0: asyncio.sleep(0, result=True)

    ok = asyncio.run(m._relogin_profile(PROFILE, why="Login requested", slot=3, wave=25))

    if not ok:
        failures.append("captcha window: the account never logged in after the "  # noqa: F821
                        "operator was given a window")
    if len(_FakeAuto.opened) != 2:
        failures.append(f"captcha window: expected a headless attempt then a visible "  # noqa: F821
                        f"one, got {_FakeAuto.opened}")
    else:
        first, second = _FakeAuto.opened
        if first != (True, None):
            failures.append(f"captcha window: the run did not start in the background: "  # noqa: F821
                            f"{first}")
        if second[0] is not False or second[1] != (3, 25):
            failures.append(f"captcha window: the retry is not a visible tile: {second}")  # noqa: F821

    # No captcha, no second window: an ordinary failure must not open one.
    _FakeAuto.opened.clear()
    _FakeAuto.attempts = 5      # every attempt now succeeds on the first try
    asyncio.run(m._relogin_profile(PROFILE, why="Login requested", slot=0, wave=25))
    if len(_FakeAuto.opened) != 1:
        failures.append(f"captcha window: a login with no captcha opened "  # noqa: F821
                        f"{len(_FakeAuto.opened)} browsers")
finally:
    cfg.get_profile_path = _real_path
    db.credentials_for_profile = _real_creds
    if _real_auto is not None:
        import src.core.facebook_automation as fa
        fa.FacebookAutomation = _real_auto
    conn = db._get_conn()
    conn.execute("DELETE FROM accounts WHERE username=?", (USER,))
    conn.commit()

print("FAILED" if [f for f in failures if "captcha window" in f] else "ok")  # noqa: F821
