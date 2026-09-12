"""Proof: DriverManager.login_accounts enqueues the command, and
_do_login_accounts walks the roster one account at a time.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The handler
is driven with a stubbed re-login (no browser), a stubbed Brave preflight
and a SheetWriter replaced by an inert stand-in, so nothing here touches
Playwright or the network. The verify_*@example.com rows it inserts are
deleted in a finally block, and the real SheetWriter is put back.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("login_accounts command")  # noqa: F821
import asyncio as _aio  # noqa: E402
import queue as _q  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.storage import database as _db  # noqa: E402
import src.storage.sheet_status as _ss  # noqa: E402

_m = _DM()
_m.log = lambda _msg: None      # the handler logs non-ASCII; keep stdout clean
_m._fast_tests = True           # no 2-4 s pause between accounts

# The public helper puts exactly one dict on cmd_queue.
_m.login_accounts(["a@example.com"])
_cmd = _m.cmd_queue.get_nowait()
if _cmd != {"type": "login_accounts", "usernames": ["a@example.com"]}:
    failures.append(f"login_accounts enqueued {_cmd}")  # noqa: F821


def _drain():
    out = []
    while True:
        try:
            out.append(_m.result_queue.get_nowait())
        except _q.Empty:
            return out


# Stubs: no browser, no Brave check, no sheet.
_calls = []


async def _fake_relogin(profile_name, **kwargs):
    _calls.append((profile_name, kwargs.get("why")))
    return profile_name == "P-ok"


class _NoWriter:
    on = False
    error = "stubbed"

    def mark_in_progress(self, _username):
        return False


_m._relogin_profile = _fake_relogin
_m._brave_running = lambda: False
_m._watch_autos = {}
_real_writer = _ss.SheetWriter
_ss.SheetWriter = lambda *a, **k: _NoWriter()
_run = {"type": "login_accounts",
        "usernames": ["verify_ok@example.com", "verify_np@example.com",
                      "ghost@example.com"]}
try:
    _db.upsert_account(1, "OK", "verify_ok@example.com", password="x")
    _db.link_account("verify_ok@example.com", "P-ok")
    _db.upsert_account(2, "NOPROF", "verify_np@example.com", password="x")
    _aio.run(_m._do_login_accounts(_run))
    _out = _drain()

    # Preflight refusals: one result, no progress, nothing logged in.
    _m._brave_running = lambda: True
    _aio.run(_m._do_login_accounts(_run))
    _refused_brave = _drain()
    _m._brave_running = lambda: False
    _aio.run(_m._do_login_accounts({"type": "login_accounts", "usernames": []}))
    _refused_empty = _drain()
finally:
    _ss.SheetWriter = _real_writer
    _db._get_conn().execute(
        "DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
    _db._get_conn().commit()

_types = [r["type"] for r in _out]
_res = _out[-1] if _out else {}
if _types.count("login_accounts_progress") != 3 \
        or _types[-1:] != ["login_accounts_result"]:
    failures.append(f"login_accounts events: {_types}")  # noqa: F821
if _res.get("ok") is not True or _res.get("total") != 3:
    failures.append(f"login_accounts result: {_res}")  # noqa: F821
if [p for p, _ in _calls] != ["P-ok"]:
    failures.append(f"relogin called for {_calls}")  # noqa: F821
elif _calls[0][1] != "Login requested":
    failures.append(  # noqa: F821
        f"relogin why={_calls[0][1]!r} (expected 'Login requested')")
if [u for u, _ in _res.get("logged_in", [])] != ["verify_ok@example.com"]:
    failures.append(f"logged_in {_res.get('logged_in')}")  # noqa: F821
if _res.get("failed"):
    failures.append(f"login_accounts failed {_res.get('failed')}")  # noqa: F821
if sorted(u for u, _ in _res.get("skipped", [])) \
        != ["ghost@example.com", "verify_np@example.com"]:
    failures.append(f"skipped {_res.get('skipped')}")  # noqa: F821

# Progress events carry the shape MainWindow reads, in roster order.
_prog = [r for r in _out if r["type"] == "login_accounts_progress"]
for _key in ("current", "total", "username", "profile_name", "ok", "message"):
    if any(_key not in r for r in _prog):
        failures.append(f"login_accounts_progress missing {_key}")  # noqa: F821
if _prog and ([r.get("current") for r in _prog] != [1, 2, 3]
              or [r.get("ok") for r in _prog] != [True, False, False]
              or _prog[0].get("profile_name") != "P-ok"):
    failures.append(  # noqa: F821
        f"login_accounts_progress order: "
        f"{[(r.get('current'), r.get('ok'), r.get('profile_name')) for r in _prog]}")

for _name, _got, _word in (("brave", _refused_brave, "Brave"),
                           ("empty", _refused_empty, "No accounts")):
    if (len(_got) != 1 or _got[0].get("type") != "login_accounts_result"
            or _got[0].get("ok") is not False
            or _word not in (_got[0].get("error") or "")):
        failures.append(f"login_accounts {_name} refusal: {_got}")  # noqa: F821
if len(_calls) != 1:
    failures.append(f"relogin ran during a refusal: {_calls}")  # noqa: F821

print("ok" if not [f for f in failures  # noqa: F821
                   if "login_accounts" in f or "relogin" in f
                   or "logged_in" in f or "skipped" in f]
      else "FAILED")
