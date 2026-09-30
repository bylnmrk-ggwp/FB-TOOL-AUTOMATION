"""The login run drives exactly one account at a time.

Brave binds the cookie key to one shared User Data tree and Chromium's
ProcessSingleton locks that tree, so an overlapping login is handed to the
running instance and reports "Opening in existing browser session" - and a
profile copied out of the tree comes back with cookies nothing can decrypt.
Sequential is not a tuning choice here, it is the reason those sessions die.

A second browser without that binding existed for a while and is gone, so the
worker count must stay behind browser_choice.supports_parallel_login() rather
than become a number someone can raise: the check is the thing that keeps a
wave from being opened.
"""
import asyncio
import queue as _queue
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("parallel login")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402
from src.core.driver_manager import DriverManager  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402
from src.storage import database as db  # noqa: E402
import src.storage.sheet_status as sheet_status  # noqa: E402

USERS = [f"verify_p{i}@example.com" for i in range(6)]
_real_writer = sheet_status.SheetWriter
_real_path = cfg.get_profile_path


class _NoWriter:
    on = False
    error = ""

    def mark_in_progress(self, username):
        return False


try:
    for i, u in enumerate(USERS):
        db.upsert_account(800 + i, f"P{i}", u, password="x")
        db.link_account(u, u)
    sheet_status.SheetWriter = lambda *a, **k: _NoWriter()
    cfg.get_profile_path = lambda name: "C:/verify/" + str(name)

    if bc.supports_parallel_login():
        failures.append("parallel login: the only browser driven is Brave, which "  # noqa: F821
                        "cannot overlap logins")

    width = getattr(DriverManager, "LOGIN_PARALLEL", None)
    if not isinstance(width, int) or not (2 <= width <= 32):
        failures.append(f"parallel login: DriverManager.LOGIN_PARALLEL should be a small "  # noqa: F821
                        f"worker count, got {width!r}")

    m = DriverManager()
    m.log = lambda message: None
    m._fast_tests = True
    m._watch_autos = {}
    m._brave_running = staticmethod(lambda: False)

    # Record how many logins are in flight at once.
    state = {"now": 0, "peak": 0}

    async def _relogin(profile_name, **kw):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.05)
        state["now"] -= 1
        return True

    m._relogin_profile = _relogin
    m._batch_pause = lambda seconds: asyncio.sleep(0)

    asyncio.run(m._do_login_accounts({"type": "login_accounts", "usernames": list(USERS)}))
    result = None
    while True:
        try:
            r = m.result_queue.get_nowait()
        except _queue.Empty:
            break
        if r.get("type") == "login_accounts_result":
            result = r

    if state["peak"] != 1:
        failures.append(f"parallel login: Brave must stay sequential - its cookie key is "  # noqa: F821
                        f"bound to one shared directory (peak {state['peak']})")
    if not result or len(result.get("logged_in", [])) != len(USERS):
        failures.append(f"parallel login: not every account was attempted: {result}")  # noqa: F821
finally:
    sheet_status.SheetWriter = _real_writer
    cfg.get_profile_path = _real_path
    conn = db._get_conn()
    conn.execute("DELETE FROM accounts WHERE username LIKE 'verify_p%@example.com'")
    conn.commit()

print("FAILED" if [f for f in failures if "parallel login" in f] else "ok")  # noqa: F821
