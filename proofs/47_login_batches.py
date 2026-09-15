"""A login run walks the roster in batches, pausing between them.

Logging in stays strictly sequential - Brave 152 binds the cookie key to the
user-data-dir and Chromium's ProcessSingleton locks that dir, so two logins
cannot share it - but a long unbroken run of fresh logins from one machine is
the pattern most likely to draw a checkpoint on every account. Spacing the
run into batches is the only lever that is ours to pull.

Also proves the skip for a linked profile the config does not know: the
roster row 'jane' pointed at 'Profile 7', which was never a saved profile,
and the run reported it as a failed login rather than a skipped one.
"""
import asyncio
import queue as _queue
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("login batches")  # noqa: F821

from src.core.driver_manager import DriverManager  # noqa: E402
from src.storage import database as db  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402

_USERS = [f"verify_b{i}@example.com" for i in range(12)]
_real_path = cfg.get_profile_path


try:
    for i, u in enumerate(_USERS):
        db.upsert_account(900 + i, f"B{i}", u, password="x")
        db.link_account(u, f"VerifyProfile{i}")

    # Every VerifyProfile* resolves; anything else (the 'Profile 7' case) does not.
    cfg.get_profile_path = lambda name: ("C:/verify/" + name) if name.startswith("VerifyProfile") else None

    m = DriverManager()
    # Its default log callback is print(), and the run logs check marks and
    # arrows that a cp1252 console cannot encode.
    m.log = lambda message: None
    m._fast_tests = True
    m._watch_autos = {}
    m._brave_running = staticmethod(lambda: False)

    pauses = []
    attempts = []

    async def _fake_relogin(profile_name, **kw):
        attempts.append(profile_name)
        return True

    async def _fake_pause(seconds):
        pauses.append(seconds)

    m._relogin_profile = _fake_relogin
    m._batch_pause = _fake_pause

    asyncio.run(m._do_login_accounts({"type": "login_accounts", "usernames": list(_USERS),
                                      "batch_size": 5, "pause_minutes": 3}))

    out = []
    while True:
        try:
            out.append(m.result_queue.get_nowait())
        except _queue.Empty:
            break
    result = out[-1] if out else {}

    if len(attempts) != 12:
        failures.append(f"login batches: expected 12 logins, got {len(attempts)}")  # noqa: F821
    # 12 accounts in batches of 5 -> a pause after #5 and after #10, none at the end.
    if len(pauses) != 2:
        failures.append(f"login batches: expected 2 pauses for 12 in 5s, got {len(pauses)} {pauses}")  # noqa: F821
    if pauses and any(abs(p - 180.0) > 0.01 for p in pauses):
        failures.append(f"login batches: pause should be 3 min = 180 s, got {pauses}")  # noqa: F821
    if len(result.get("logged_in", [])) != 12:
        failures.append(f"login batches: logged_in {len(result.get('logged_in', []))}")  # noqa: F821

    # batch_size 0 / absent means one unbroken run, as before.
    pauses.clear(); attempts.clear()
    while True:
        try:
            m.result_queue.get_nowait()
        except _queue.Empty:
            break
    asyncio.run(m._do_login_accounts({"type": "login_accounts", "usernames": list(_USERS),
                                      "batch_size": 0}))
    if pauses:
        failures.append(f"login batches: batch_size 0 must not pause, got {pauses}")  # noqa: F821

    # A linked profile the config does not know is a skip, not a failure.
    pauses.clear(); attempts.clear()
    while True:
        try:
            m.result_queue.get_nowait()
        except _queue.Empty:
            break
    db.link_account(_USERS[0], "Profile 7")          # not a saved profile
    asyncio.run(m._do_login_accounts({"type": "login_accounts", "usernames": [_USERS[0]]}))
    tail = []
    while True:
        try:
            tail.append(m.result_queue.get_nowait())
        except _queue.Empty:
            break
    res = tail[-1] if tail else {}
    if [u for u, _ in res.get("skipped", [])] != [_USERS[0]]:
        failures.append(f"unregistered profile should be skipped, got {res.get('skipped')} "  # noqa: F821
                        f"failed={res.get('failed')}")
    if attempts:
        failures.append("unregistered profile must not open a browser")  # noqa: F821
    # An account already logged in is skipped, not driven again: opening a
    # browser for it costs a minute and risks a fresh checkpoint on a session
    # that was working. The database's own 'ok' is the only thing that skips
    # one; a row with no recorded verdict is still attempted.
    pauses.clear(); attempts.clear()
    while True:
        try:
            m.result_queue.get_nowait()
        except _queue.Empty:
            break
    db.link_account(_USERS[1], "VerifyProfile1")
    db.set_account_status(_USERS[1], "ok")
    asyncio.run(m._do_login_accounts({"type": "login_accounts",
                                      "usernames": [_USERS[1], _USERS[2], _USERS[3]]}))
    tail2 = []
    while True:
        try:
            tail2.append(m.result_queue.get_nowait())
        except _queue.Empty:
            break
    res2 = tail2[-1] if tail2 else {}
    skipped_users = [u for u, _ in res2.get("skipped", [])]
    if _USERS[1] not in skipped_users:
        failures.append(f"login batches: status 'ok' must be skipped, got {res2.get('skipped')}")  # noqa: F821
    if _USERS[2] in skipped_users:
        failures.append("login batches: a row with no verdict must still be attempted")  # noqa: F821
    if _USERS[3] in skipped_users:
        failures.append("login batches: a row with no verdict must still be attempted")  # noqa: F821
    if _USERS[3] not in [u for u, _ in res2.get("logged_in", [])]:
        failures.append(f"login batches: the not-logged-in account was not attempted: {res2}")  # noqa: F821

finally:
    cfg.get_profile_path = _real_path
    conn = db._get_conn()
    conn.execute("DELETE FROM accounts WHERE username LIKE 'verify_b%@example.com'")
    conn.commit()

print("FAILED" if [f for f in failures if "login batches" in f or "unregistered" in f] else "ok")  # noqa: F821
