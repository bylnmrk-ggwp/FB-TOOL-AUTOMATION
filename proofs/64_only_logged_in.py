"""A batch attempts every profile, and a live session is never reported dead.

The pre-filter that skipped accounts marked NOT LOGGED IN was asked for and
then withdrawn: the operator wants the whole fleet to act and to judge from
the per-item results, because a stored status is a verdict from an earlier
run, not the state of the session now. What remains from that work is the
half that was always right - the classifier can answer "this account is
fine". Asked after any failure it used to return unknown_not_logged_in for a
working session, and the account was demoted on that.
"""
import asyncio
import queue as _queue
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("only logged in")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.core.facebook_automation import FacebookAutomation  # noqa: E402
from src.storage import database as db  # noqa: E402

LIVE = "verify_live@example.com"
DEAD = "verify_dead@example.com"

try:
    for i, u in enumerate((LIVE, DEAD)):
        db.upsert_account(880 + i, f"L{i}", u, password="x")
        db.link_account(u, u)
    db.set_account_status(LIVE, "ok")
    db.set_account_status(DEAD, "session expired")

    if not DriverManager._session_recorded_live(LIVE):
        failures.append("only logged in: an account the database calls 'ok' is not "  # noqa: F821
                        "recognised as logged in")
    if DriverManager._session_recorded_live(DEAD):
        failures.append("only logged in: a non-'ok' status was read as logged in")  # noqa: F821

    # An account last seen signed out is still attempted: no pre-filter.
    import inspect
    batch_src = inspect.getsource(DriverManager._do_batch)
    if "skipped - not logged in" in batch_src:
        failures.append("only logged in: the batch still drops accounts before "  # noqa: F821
                        "opening a browser, so the fleet cannot be seen acting")
    if "attempting them anyway" not in batch_src:
        failures.append("only logged in: the batch does not say it is attempting "  # noqa: F821
                        "profiles that were last seen signed out")

    # The classifier can say an account is fine.
    if not hasattr(FacebookAutomation, "LOGGED_IN"):
        failures.append("only logged in: the classifier has no verdict for a live "  # noqa: F821
                        "session, so a working account gets a failure reason")
    else:
        class _Page:
            url = "https://www.facebook.com/"

        auto = FacebookAutomation(log_callback=lambda m: None)
        auto.page = _Page()
        auto._is_logged_in = lambda timeout=10: asyncio.sleep(0, result=True)
        if asyncio.run(auto._classify_account_access()) != FacebookAutomation.LOGGED_IN:
            failures.append("only logged in: a live session is still classified as a "  # noqa: F821
                            "reason for failure")
        auto._is_logged_in = lambda timeout=10: asyncio.sleep(0, result=False)
        verdict = asyncio.run(auto._classify_account_access())
        if verdict == FacebookAutomation.LOGGED_IN:
            failures.append("only logged in: a dead session was called logged in")  # noqa: F821

        # A login check that meets a live session reports it as logged in.
        m2 = DriverManager()
        m2.log = lambda message: None
        auto2 = FacebookAutomation(log_callback=lambda m: None)
        auto2._classify_account_access = lambda page=None: asyncio.sleep(
            0, result=FacebookAutomation.LOGGED_IN)
        out = asyncio.run(m2._login_failure(auto2, "whoever"))
        if not out.get("ok") or out.get("needs_login"):
            failures.append(f"only logged in: a live session was still marked as "  # noqa: F821
                            f"needing login: {out}")
finally:
    conn = db._get_conn()
    conn.execute("DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
    conn.commit()

print("FAILED" if [f for f in failures if "only logged in" in f] else "ok")  # noqa: F821
