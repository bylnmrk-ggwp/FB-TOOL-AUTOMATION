"""On Chromium the login run drives several accounts at once.

Brave binds the cookie key to one shared User Data tree and Chromium's
ProcessSingleton locks it, so a Brave run must stay sequential - that is not
a tuning choice, it is the reason copied profiles come back dead. With one
self-contained directory per account nothing is shared, so the run may open
several at a time.

The switch is per browser, never a flag someone can set wrongly: ask
browser_choice.supports_parallel_login().
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

USERS = [f"verify_p{i}@example.com" for i in range(6)]
_saved_browser = cfg.get_setting(bc.SETTING_KEY, None)
_real_path = cfg.get_profile_path


try:
    for i, u in enumerate(USERS):
        db.upsert_account(800 + i, f"P{i}", u, password="x")
        db.link_account(u, u)
    cfg.get_profile_path = lambda name: "C:/verify/" + str(name)

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

    # Chromium: several at once.
    cfg.save_setting(bc.SETTING_KEY, "chromium")
    asyncio.run(m._do_login_accounts({"type": "login_accounts", "usernames": list(USERS)}))
    result = None
    while True:
        try:
            r = m.result_queue.get_nowait()
        except _queue.Empty:
            break
        if r.get("type") == "login_accounts_result":
            result = r
    if state["peak"] < 2:
        failures.append(f"parallel login: on Chromium the run stayed sequential "  # noqa: F821
                        f"(peak {state['peak']})")
    if width and state["peak"] > width:
        failures.append(f"parallel login: {state['peak']} logins at once exceeds the "  # noqa: F821
                        f"{width} worker limit")
    if not result or len(result.get("logged_in", [])) != len(USERS):
        failures.append(f"parallel login: not every account was attempted: {result}")  # noqa: F821

    # Brave: strictly one at a time, whatever the worker count says.
    state.update(now=0, peak=0)
    cfg.save_setting(bc.SETTING_KEY, "brave")
    asyncio.run(m._do_login_accounts({"type": "login_accounts", "usernames": list(USERS)}))
    while True:
        try:
            m.result_queue.get_nowait()
        except _queue.Empty:
            break
    if state["peak"] != 1:
        failures.append(f"parallel login: Brave must stay sequential - its cookie key is "  # noqa: F821
                        f"bound to one shared directory (peak {state['peak']})")
finally:
    cfg.get_profile_path = _real_path
    if _saved_browser is None:
        conf = cfg._load_config()
        conf.pop(bc.SETTING_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.SETTING_KEY, _saved_browser)
    conn = db._get_conn()
    conn.execute("DELETE FROM accounts WHERE username LIKE 'verify_p%@example.com'")
    conn.commit()

print("FAILED" if [f for f in failures if "parallel login" in f] else "ok")  # noqa: F821
