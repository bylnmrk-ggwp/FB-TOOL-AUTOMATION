"""A login is confirmed over a few seconds, not in a single instant.

After the credentials go in, Facebook still has to finish its redirects and
set c_user/xs. _session_is_live() was called once, right away: a session that
needed two more seconds was recorded as "signed in but never reached the home
page - Facebook is gating this account", which is how accounts the operator
could open by hand came back NOT LOGGED IN.

_wait_session_live() polls until the session really is live or the window
closes, so a slow redirect reads as success and only a genuine failure reads
as failure.
"""
import asyncio
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("session confirm wait")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402

seconds = getattr(DriverManager, "SESSION_CONFIRM_S", None)
if not isinstance(seconds, (int, float)):
    failures.append("session confirm: DriverManager.SESSION_CONFIRM_S missing")  # noqa: F821
elif not (10 <= seconds <= 60):
    failures.append(  # noqa: F821
        f"session confirm: {seconds}s is outside the useful 10-60 s band")

if not callable(getattr(DriverManager, "_wait_session_live", None)):
    failures.append("session confirm: DriverManager._wait_session_live missing")  # noqa: F821
else:
    m = DriverManager.__new__(DriverManager)      # no worker thread, no browser
    calls = {"n": 0}

    async def live_on_third(auto):
        calls["n"] += 1
        return calls["n"] >= 3

    m._session_is_live = live_on_third
    got = asyncio.run(DriverManager._wait_session_live(m, object(), seconds=5, poll=0.01))
    if got is not True:
        failures.append(f"session confirm: a session that goes live on the 3rd poll "  # noqa: F821
                        f"must be confirmed, got {got!r}")
    if calls["n"] < 3:
        failures.append(f"session confirm: gave up after {calls['n']} checks")  # noqa: F821

    # A session that never goes live still returns False, and does not hang.
    async def never(auto):
        return False

    m._session_is_live = never
    if asyncio.run(DriverManager._wait_session_live(m, object(), seconds=0.05, poll=0.01)) is not False:
        failures.append("session confirm: a dead session must return False")  # noqa: F821

# The re-login path must use the wait, not a bare single check, to decide.
src = inspect.getsource(DriverManager._relogin_profile)
if "_wait_session_live" not in src:
    failures.append("session confirm: _relogin_profile still confirms with a single "  # noqa: F821
                    "instant _session_is_live call")

print("FAILED" if [f for f in failures if "session confirm" in f] else "ok")  # noqa: F821
