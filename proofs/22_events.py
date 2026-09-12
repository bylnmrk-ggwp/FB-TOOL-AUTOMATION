"""Proof: src/server/events.py - the EventBridge does what MainWindow's
result polling did, without a window.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The bridge
is fed result dicts shaped exactly as DriverManager emits them (the manager
thread is never started), its log lines land in a LogRing under a temp
directory, and cfg.save_setting is replaced by a recorder so the operator's
real config never receives a fake batch summary. The one verify_*@example.com
row the sheet-event check inserts is deleted in the finally block. No
browser, no Google, no Brave directory.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("events bridge")  # noqa: F821
import asyncio as _aio  # noqa: E402
import queue as _q  # noqa: E402
import re as _re  # noqa: E402
import shutil as _sh  # noqa: E402
import tempfile as _tf  # noqa: E402
import threading as _th  # noqa: E402
import time as _time  # noqa: E402
from pathlib import Path as _P  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.storage import database as _db  # noqa: E402
from src.server import events as _ev  # noqa: E402
from src.server.logbuf import LogRing as _LogRing  # noqa: E402
from src.server.state import AppState as _AppState  # noqa: E402


def _fail(msg):
    failures.append(f"events: {msg}")  # noqa: F821


_tmp = _P(_tf.mkdtemp(prefix="verify_events_"))
_saved_settings = []
_real_save = _ev.cfg.save_setting
_real_timeout = _ev.INPUT_TIMEOUT_S
_m = _DM()
_m.log = lambda _msg: None      # the driver logs non-ASCII; keep stdout clean
_state = _AppState()
_ring = _LogRing(log_dir=_tmp / "logs")
_bridge = _ev.EventBridge(_m, None, _state, _ring)


def _types():
    return [e.get("type") for e in _bridge.recent]


def _texts():
    return [e["text"] for e in _ring.tail(2000)]


def _has_line(prefix):
    return any(t.startswith(prefix) for t in _texts())


try:
    _ev.cfg.save_setting = lambda k, v: _saved_settings.append((k, v))

    # ── fan-out without a loop: nothing raises, recent still fills ─────
    _bridge.broadcast({"type": "ping"})
    if _types() != ["ping"]:
        _fail(f"broadcast without a loop: recent={_types()}")

    # ── batch_progress -> run ──────────────────────────────────────────
    _bridge.handle_result({"type": "batch_progress", "current": 2, "total": 5,
                           "profile_name": "P", "message": "sharing"})
    _run = _state.run
    if (_run is None or _run.kind != "batch" or _run.current != 2
            or _run.total != 5 or _run.profile_name != "P"
            or _run.message != "sharing" or not _run.started_at):
        _fail(f"batch_progress run={_run}")
    if "sharing" not in _texts():
        _fail("batch_progress message not logged")
    if _types()[-2:] != ["batch_progress", "state"]:
        _fail(f"result then state expected, got {_types()[-2:]}")
    _state_ev = _bridge.recent[-1]
    if "counts" not in _state_ev or "run" not in _state_ev:
        _fail(f"state event lacks counts/run: {sorted(_state_ev)}")

    # ── batch_item_result x2 then batch_result as _do_batch emits it ───
    _bridge.handle_result({"type": "batch_item_result", "ok": True,
                           "profile_name": "P", "message": "shared",
                           "rate_limited": False, "needs_login": False})
    _bridge.handle_result({"type": "batch_item_result", "ok": False,
                           "profile_name": "Q", "message": "refused",
                           "rate_limited": False, "needs_login": False})
    _bridge.handle_result({"type": "batch_result", "ok": True, "total": 5})
    if _state.run is not None:
        _fail(f"batch_result left run={_state.run}")
    if not _state.last_run_summary.startswith("1 ok · 4 failed · "):
        _fail(f"last_run_summary={_state.last_run_summary!r}")
    if _saved_settings[-1:] != [("last_run_summary", _state.last_run_summary)]:
        _fail(f"last_run_summary not saved: {_saved_settings}")
    if not _has_line("Batch complete: 5 item(s) processed"):
        _fail("batch_result summary line missing")
    if not _has_line("✓ P: shared") or not _has_line("✗ Q: refused"):
        _fail(f"batch_item_result lines missing from {_texts()[-6:]}")

    # ── login scan: scan_active follows progress/result ────────────────
    _bridge.handle_result({"type": "login_scan_progress", "current": 1,
                           "total": 2, "profile_name": "P", "logged_in": True,
                           "message": "[1/2] 'P' - logged in"})
    if not _state.scan_active or _state.run is None or _state.run.kind != "scan":
        _fail(f"login_scan_progress: scan_active={_state.scan_active} run={_state.run}")
    _bridge.handle_result({
        "type": "login_scan_result", "ok": True, "logged_in_count": 1,
        "total": 2, "removed_profiles": [],
        "results": [{"profile_name": "P", "logged_in": True,
                     "reason": "logged_in", "removed": False},
                    {"profile_name": "Q", "logged_in": False,
                     "reason": "wrong_password", "removed": False}]})
    if _state.scan_active or _state.run is not None:
        _fail(f"login_scan_result: scan_active={_state.scan_active} run={_state.run}")
    if not _has_line("Login check done — 1/2 logged in; need re-login: Q"):
        _fail(f"login_scan_result line missing from {_texts()[-3:]}")

    # ── login_accounts: flag cleared, error toast on ok False ──────────
    _state.login_run_active = True          # the route sets it
    _bridge.handle_result({"type": "login_accounts_progress", "current": 1,
                           "total": 1, "username": "u@example.com",
                           "profile_name": "P", "ok": True,
                           "message": "[1/1] u@example.com: logged in"})
    if _state.run is None or _state.run.kind != "login":
        _fail(f"login_accounts_progress run={_state.run}")
    _bridge.handle_result({"type": "login_accounts_result", "ok": False,
                           "error": "Brave is open", "total": 0,
                           "logged_in": [], "failed": [], "skipped": []})
    if _state.login_run_active or _state.run is not None:
        _fail(f"login_accounts_result: active={_state.login_run_active} run={_state.run}")
    _errs = [e for e in _bridge.recent if e.get("type") == "error"]
    if not _errs or _errs[-1].get("text") != "Brave is open":
        _fail(f"error event missing: {_errs}")
    # A refused item inside a bulk run is a log line, not a toast.
    _n_err = len(_errs)
    _bridge.handle_result({"type": "join_group_item_result", "ok": False,
                           "error": "timed out", "url": "u", "profile_name": "P",
                           "current": 1, "total": 3})
    if len([e for e in _bridge.recent if e.get("type") == "error"]) != _n_err:
        _fail("join_group_item_result raised an error toast")

    # ── a handler that raised: the flags it owned are released ─────────
    _state.login_run_active = True
    _bridge.handle_result({"type": "login_accounts", "success": False,
                           "message": "boom"})
    if _state.login_run_active or _state.run is not None:
        _fail("command failure left login_run_active set")
    if "boom" not in _texts():
        _fail("command failure message not logged")

    # ── image prompt round trip ────────────────────────────────────────
    _tmp1, _tmp2 = _tmp / "a.jpg", _tmp / "b.jpg"
    _tmp1.write_bytes(b"a")
    _tmp2.write_bytes(b"b")
    _bridge.handle_result({"type": "auto_setup_images_preview",
                           "profile_name": "P",
                           "images": [str(_tmp1), str(_tmp2)],
                           "needs_pic": True})
    _pi = _state.pending_input
    if (not _pi or _pi.get("kind") != "image_picker"
            or _pi.get("profile_name") != "P" or _pi.get("needs_pic") is not True
            or len(_pi.get("images", [])) != 2 or not _pi.get("created_at")):
        _fail(f"pending_input={_pi}")
    else:
        _id1, _id2 = _pi["images"][0]["id"], _pi["images"][1]["id"]
        if _pi["images"][0]["url"] != f"/api/images/{_id1}" or _id1 == _id2:
            _fail(f"image ids/urls: {_pi['images']}")
        if _bridge.image_path(_id1) != str(_tmp1) or _bridge.image_path(_id2) != str(_tmp2):
            _fail("image_path does not map ids back to the paths")
        if _bridge.image_path("nope") is not None:
            _fail("image_path answered an id outside the allow-list")
        _ni = [e for e in _bridge.recent if e.get("type") == "needs_input"]
        if not _ni or _ni[-1].get("images") != _pi["images"]:
            _fail(f"needs_input event: {_ni[-1:] }")
        if not _has_line("Waiting for image choice"):
            _fail("'Waiting for image choice' not logged")
        if _bridge.answer_input({"profile_pic": _id1, "cancel": False}) is not True:
            _fail("answer_input returned False with a prompt open")
        try:
            _resp = _m._user_response_queue.get_nowait()
        except _q.Empty:
            _resp = None
        if _resp != {"profile_pic": str(_tmp1), "cancel": False}:
            _fail(f"send_user_response got {_resp}")
        if _state.pending_input is not None or _bridge.image_path(_id1) is not None:
            _fail("answer_input did not clear the prompt and allow-list")
    if _bridge.answer_input({"profile_pic": None, "cancel": True}) is not False:
        _fail("answer_input answered a prompt that is not open")

    # ── sheet events: rows are applied here, on the bridge thread ──────
    class _Watcher:
        last_ok = 1234.5
        events = _q.Queue()

    _b2 = _ev.EventBridge(_m, _Watcher(), _state, _ring)
    _b2.handle_sheet_event("rows", [{
        "sheet_no": 999, "facebook_name": "Verify Events",
        "username": "verify_events@example.com", "password": "", "gmail": "",
        "gmail_password": "", "number": "", "sheet_status": ""}])
    if not any(a["username"] == "verify_events@example.com"
               for a in _db.list_accounts()):
        _fail("sheet rows were not applied to the database")
    if not _has_line("Roster synced from sheet: 1 new, 0 refreshed"):
        _fail(f"roster sync line missing from {_texts()[-3:]}")
    if _state.sheet_last_ok != 1234.5:
        _fail(f"sheet_last_ok={_state.sheet_last_ok}")
    if [e.get("type") for e in _b2.recent][-2:] != ["accounts_changed", "state"]:
        _fail(f"sheet rows events: {[e.get('type') for e in _b2.recent]}")
    _b2.handle_sheet_event("error", "HTTPError: 503")
    if not _has_line("Sheet sync error: HTTPError: 503"):
        _fail("sheet error line missing")

    # ── fan-out through a real loop, from another thread ───────────────
    async def _fanout():
        loop = _aio.get_running_loop()
        _bridge.attach_loop(loop)
        q = _bridge.subscribe()
        _th.Thread(target=lambda: _bridge.broadcast({"type": "ping2"})).start()
        try:
            return await _aio.wait_for(q.get(), 1.0)
        finally:
            _bridge.unsubscribe(q)
            _bridge.attach_loop(None)

    try:
        _got = _aio.run(_fanout())
    except Exception as e:  # noqa: BLE001 - reported, never fatal
        _got = f"raised {e!r}"
    if _got != {"type": "ping2"}:
        _fail(f"subscriber received {_got}")

    # ── the thread: drains the manager, refreshes system, times out ────
    _ev.INPUT_TIMEOUT_S = 0
    _m.result_queue.put({"type": "auto_setup_images_preview",
                         "profile_name": "P", "images": [str(_tmp1)],
                         "needs_pic": False})
    _b3 = _ev.EventBridge(_m, None, _state, _ring, poll_ms=20)
    _b3.start()
    _resp = None
    _deadline = _time.monotonic() + 5.0
    while _time.monotonic() < _deadline:
        try:
            _resp = _m._user_response_queue.get_nowait()
            break
        except _q.Empty:
            _time.sleep(0.02)
    _b3.stop()
    if _b3.is_alive():
        _fail("bridge thread did not stop")
    if _resp != {"profile_pic": None, "cancel": True}:
        _fail(f"pending_input timeout sent {_resp}")
    if _state.pending_input is not None:
        _fail("timed-out prompt still open")
    if "auto_setup_images_preview" not in [e.get("type") for e in _b3.recent]:
        _fail("thread did not forward the manager's result")
    if not _state.bridge_alive:
        _fail("bridge_alive dropped on a clean run")
    for _key in ("ram_used_gb", "ram_total_gb", "browser_mb",
                 "process_count", "peak_browser_mb"):
        if _key not in _state.system:
            _fail(f"state.system lacks {_key}: {_state.system}")
            break
    _bad = [t for t in _texts() if "bridge error" in t]
    if _bad:
        _fail(f"bridge errors logged: {_bad}")

    # ── parity: every rtype MainWindow switches on has a branch here ───
    _src = (ROOT / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")  # noqa: F821
    _tk = set(_re.findall(r'rtype == "(\w+)"', _src))
    if len(_tk) != 24:
        _fail(f"main_window handles {len(_tk)} rtypes, plan says 24")
    _missing = sorted(_tk - set(_ev.HANDLED_RTYPES))
    if _missing:
        _fail(f"HANDLED_RTYPES lacks {_missing}")
    for _name in ("login_accounts_progress", "login_accounts_result"):
        if _name not in _ev.HANDLED_RTYPES:
            _fail(f"HANDLED_RTYPES lacks {_name}")
    _no_branch = [n for n in _ev.HANDLED_RTYPES
                  if not callable(getattr(_ev.EventBridge, f"_on_{n}", None))]
    if _no_branch:
        _fail(f"HANDLED_RTYPES names without a branch: {_no_branch}")
finally:
    _ev.cfg.save_setting = _real_save
    _ev.INPUT_TIMEOUT_S = _real_timeout
    _ring.close()
    _sh.rmtree(_tmp, ignore_errors=True)
    _db._get_conn().execute(
        "DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
    _db._get_conn().commit()

print("ok" if not [f for f in failures if f.startswith("events:")]  # noqa: F821
      else "FAILED")
