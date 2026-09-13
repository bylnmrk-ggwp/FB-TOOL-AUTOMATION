"""A batch runs only on accounts with a live session, and a live session is
never reported as a dead one.

Two halves of the same mistake. The queue opened a browser for all 65
profiles whatever their status, so accounts marked NOT LOGGED IN were driven
anyway - each one costing a launch, a page load, a misleading reason on the
sheet and another failed request on the account's record. And the classifier
had no way of answering "this account is fine": asked after any failure, it
returned unknown_not_logged_in for a working session, which demoted it.
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
SHEET_LIVE = "verify_sheet@example.com"

try:
    for i, u in enumerate((LIVE, DEAD, SHEET_LIVE)):
        db.upsert_account(880 + i, f"L{i}", u, password="x")
        db.link_account(u, u)
    db.set_account_status(LIVE, "ok")
    conn = db._get_conn()
    conn.execute("UPDATE accounts SET sheet_status='LOGGED IN' WHERE username=?", (SHEET_LIVE,))
    # The exact string the operator asked never to be used again.
    conn.execute("UPDATE accounts SET sheet_status='NOT LOGGED IN / SESSION EXPIRED' "
                 "WHERE username=?", (DEAD,))
    conn.commit()

    if not DriverManager._session_recorded_live(LIVE):
        failures.append("only logged in: an account the database calls 'ok' is not "  # noqa: F821
                        "recognised as logged in")
    if not DriverManager._session_recorded_live(SHEET_LIVE):
        failures.append("only logged in: the sheet's LOGGED IN cell is not recognised")  # noqa: F821
    if DriverManager._session_recorded_live(DEAD):
        failures.append("only logged in: 'NOT LOGGED IN / SESSION EXPIRED' was read as "  # noqa: F821
                        "logged in - the words overlap, so the match must be exact")

    # A batch of dead accounts opens no browser at all.
    m = DriverManager()
    m.log = lambda message: None
    m._fast_tests = True
    opened = []
    m._create_temp_automation = lambda *a, **k: opened.append("browser")
    asyncio.run(m._do_batch([{"profile_name": DEAD, "action_type": "comment",
                              "comment": "hi"}]))
    if opened:
        failures.append("only logged in: a dead account still opened a browser")  # noqa: F821
    messages = []
    while True:
        try:
            messages.append(m.result_queue.get_nowait())
        except _queue.Empty:
            break
    if not any("skipped - not logged in" in (r.get("message") or "") for r in messages):
        failures.append(f"only logged in: the skip was not reported: {messages}")  # noqa: F821
    if not any(r.get("type") == "batch_result" for r in messages):
        failures.append("only logged in: the batch never finished when every account "  # noqa: F821
                        "was skipped")

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
