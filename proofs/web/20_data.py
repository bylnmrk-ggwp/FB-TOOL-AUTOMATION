"""Proof: src/server data.py, state.py and logbuf.py - the pure reads and
the two value holders the web server is built on.

Runs under verify.py with globals `failures`, `step` and `ROOT`. Inserts
three verify_*@example.com rows into the real database and deletes them in
a finally block, so an assertion that raises cannot leave them behind. The
LogRing writes to a throwaway temp directory, never ~/.autoshare/logs, and
that directory is removed in the same finally.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("server data / state / logbuf")  # noqa: F821
import json as _json  # noqa: E402
import re as _re  # noqa: E402
import shutil as _shutil  # noqa: E402
import tempfile as _tempfile  # noqa: E402
from datetime import datetime as _dt  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

from src.storage import config_manager as _cfg  # noqa: E402
from src.storage import database as _db  # noqa: E402
from src.server import data as _data  # noqa: E402
from src.server.logbuf import LogRing as _LogRing  # noqa: E402
from src.server.state import AppState as _AppState, RunState as _RunState  # noqa: E402
from src.ui.log_tab import LogTab as _LogTab  # noqa: E402


def _fail(msg):
    failures.append(f"20_data: {msg}")  # noqa: F821


_OK, _PEND, _DIS = ("verify_s1_ok@example.com", "verify_s1_pending@example.com",
                    "verify_s1_disabled@example.com")
_PROFILE = "verify-s1-profile"       # linked, but not a saved Brave profile
_ROW_KEYS = {"sheet_no", "facebook_name", "username", "gmail", "linked_profile",
             "status", "status_reason", "sheet_status", "logged_in", "restricted"}
_STATE_KEYS = {"run", "last_run_summary", "queue", "pending_input",
               "login_run_active", "scan_active", "provision_active",
               "sheet_last_ok", "system",
               "bridge_alive", "version"}

# -- data.py ---------------------------------------------------------------
_before = _data.counts()
try:
    # The logged-in one carries the sheet's LOGGED IN verdict: a blank
    # sheet_status is what makes a row pending, so without it the ok row
    # would be counted twice (logged in and pending).
    _db.upsert_account(9001, "S1 OK", _OK, password="x", sheet_status="LOGGED IN")
    _db.link_account(_OK, _PROFILE)
    _db.set_account_status(_OK, "ok")
    _db.upsert_account(9002, "S1 PENDING", _PEND, password="x")
    _db.upsert_account(9003, "S1 DISABLED", _DIS, password="x")
    _db.set_account_status(_DIS, "disabled", "checkpoint")

    _after = _data.counts()
    _want = {"total": 3, "logged_in": 1, "pending": 1, "pending_unlinked": 1,
             "disabled": 1, "profiles": 0, "active": 1}
    if set(_after) != set(_want):
        _fail(f"counts() keys {sorted(_after)}")
    else:
        _delta = {k: _after[k] - _before[k] for k in _want}
        if _delta != _want:
            _fail(f"counts() delta {_delta}, expected {_want}")

    _rows = _data.accounts_rows()
    _by_user = {r.get("username"): r for r in _rows}
    for _u in (_OK, _PEND, _DIS):
        _r = _by_user.get(_u)
        if _r is None:
            _fail(f"accounts_rows() lacks {_u}")
            continue
        if set(_r) != _ROW_KEYS:
            _fail(f"accounts_rows() keys for {_u}: {sorted(_r)}")
        if _r.get("logged_in") is not (_u == _OK):
            _fail(f"accounts_rows() logged_in for {_u}: {_r.get('logged_in')!r}")
        if _r.get("restricted") is not False:
            _fail(f"accounts_rows() restricted for {_u}: {_r.get('restricted')!r}")
    if _by_user.get(_OK, {}).get("linked_profile") != _PROFILE:
        _fail(f"accounts_rows() linked_profile: {_by_user.get(_OK)}")
    if _by_user.get(_DIS, {}).get("status_reason") != "checkpoint":
        _fail(f"accounts_rows() status_reason: {_by_user.get(_DIS)}")
    # Every saved Brave profile shows up exactly like ProfilesTab shows it:
    # under the account linked to it, or as its own username-less row.
    _linked = {r["linked_profile"] for r in _rows if r.get("username")}
    _unlinked = [r for r in _rows if r.get("username") is None]
    for _name in _cfg.list_profiles():
        _seen = [r for r in _rows if r.get("linked_profile") == _name]
        if not _seen:
            _fail(f"accounts_rows() lacks Brave profile {_name!r}")
        elif _name not in _linked and len(_seen) != 1:
            _fail(f"accounts_rows() lists unlinked {_name!r} {len(_seen)} times")
    for _r in _unlinked:
        if _r["linked_profile"] in _linked or set(_r) != _ROW_KEYS \
                or _r["logged_in"] is not False:
            _fail(f"accounts_rows() unlinked profile row {_r}")
    if any(r["username"] is None and r["linked_profile"] == _PROFILE for r in _rows):
        _fail("accounts_rows() invented a Brave profile for a linked name")

    _pend = _data.pending_usernames()
    if _PEND in _pend:
        _fail("pending_usernames() includes an account with no Brave profile")
    _linked_pending = {a["username"] for a in _db.pending_accounts()
                       if a.get("linked_profile")}
    if set(_pend) != _linked_pending:
        _fail(f"pending_usernames() {sorted(_pend)} != {sorted(_linked_pending)}")
finally:
    _db._get_conn().execute(
        "DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
    _db._get_conn().commit()

_line = _data.summary_line(3, 1, _dt(2026, 9, 12, 20, 11))
if _line != "3 ok \u00b7 1 failed \u00b7 20:11":
    _fail(f"summary_line() {ascii(_line)}")
if not _re.fullmatch(r"0 ok \u00b7 0 failed \u00b7 \d\d:\d\d", _data.summary_line(0, 0)):
    _fail(f"summary_line() default when: {ascii(_data.summary_line(0, 0))}")

# -- state.py --------------------------------------------------------------
_st = _AppState()
_d = _st.to_dict()
if set(_d) != _STATE_KEYS:
    _fail(f"AppState.to_dict() keys {sorted(_d)}")
if _d.get("run") is not None or _d.get("bridge_alive") is not True \
        or _d.get("version") != "dev" or _d.get("system") != {}:
    _fail(f"AppState defaults {_d}")
if _d.get("last_run_summary") != (_cfg.get_setting("last_run_summary", "") or ""):
    _fail("AppState.last_run_summary not restored from config")
try:
    _json.dumps(_d)
except Exception as _e:
    _fail(f"AppState.to_dict() not JSON-safe: {_e}")
_run = _AppState(run=_RunState("batch", 2, 5, "sharing", "P", 1.5),
                 pending_input={"kind": "image_picker", "images": []},
                 last_run_summary="kept").to_dict()
if _run.get("run") != {"kind": "batch", "current": 2, "total": 5, "message": "sharing",
                       "profile_name": "P", "started_at": 1.5}:
    _fail(f"AppState.to_dict() run {_run.get('run')}")
if _run.get("pending_input") != {"kind": "image_picker", "images": []} \
        or _run.get("last_run_summary") != "kept":
    _fail(f"AppState.to_dict() explicit fields {_run}")
try:
    _json.dumps(_run)
except Exception as _e:
    _fail(f"AppState.to_dict() with run not JSON-safe: {_e}")

# -- logbuf.py -------------------------------------------------------------
if _LogRing.LOG_DIR != _LogTab.LOG_DIR or _LogRing.MAX_LINES != _LogTab.MAX_LINES:
    _fail("LogRing.LOG_DIR / MAX_LINES differ from LogTab's")
_tmp = _Path(_tempfile.mkdtemp(prefix="verify_logring_"))
try:
    _ring = _LogRing(log_dir=_tmp)
    _seen = []
    _ring.set_on_line(_seen.append)
    _wrote = [_ring.write("\u2713 logged in  "),
              _ring.write("\u2717 login failed"),
              _ring.write("plain line")]
    if [e["level"] for e in _wrote] != ["ok", "error", "info"]:
        _fail(f"LogRing levels {[e['level'] for e in _wrote]}")
    if [e["text"] for e in _wrote] != ["\u2713 logged in", "\u2717 login failed", "plain line"]:
        _fail(f"LogRing texts {ascii([e['text'] for e in _wrote])}")
    if any(set(e) != {"stamp", "text", "level"}
           or not _re.fullmatch(r"\d\d:\d\d:\d\d", e["stamp"]) for e in _wrote):
        _fail(f"LogRing entry shape {ascii(_wrote)}")
    if _ring.write("Share error: refused")["level"] != "error" \
            or _ring.write("Fail-safe engaged")["level"] != "error" \
            or _ring.write("Error-free")["level"] != "error":
        _fail("LogRing level rule differs from LogTab.write")
    if _ring.tail(2) != _ring.tail(99)[-2:] or len(_ring.tail(2)) != 2 \
            or _ring.tail(2)[-1]["text"] != "Error-free" or _ring.tail(0) != []:
        _fail(f"LogRing.tail {ascii(_ring.tail(2))}")
    if _seen != _wrote + _ring.tail(3):
        _fail(f"LogRing on_line saw {len(_seen)} of 6")
    _ring.close()
    _path = _tmp / f"app-{_dt.now():%Y%m%d}.log"
    if not _path.exists():
        _fail(f"LogRing wrote no {_path.name}")
    else:
        _lines = _path.read_text(encoding="utf-8").splitlines()
        if len(_lines) != 6:
            _fail(f"LogRing file has {len(_lines)} lines, expected 6")
        # Same line shape LogTab writes - one stamp, one space, the text -
        # since the Tk app and the server append to the same file.
        for _l, _e in zip(_lines, _wrote):
            if not _re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d "
                                 + _re.escape(_e["text"]), _l):
                _fail(f"LogRing file line {ascii(_l)}")
    # write after close reopens, as LogTab does when the day rolls over
    _ring.write("after close")
    _ring.close()
    if len(_path.read_text(encoding="utf-8").splitlines()) != 7:
        _fail("LogRing did not reopen the file after close()")
    _small = _LogRing(maxlen=2, log_dir=_tmp)
    for _i in range(3):
        _small.write(f"line {_i}")
    _small.close()
    if [e["text"] for e in _small.tail()] != ["line 1", "line 2"]:
        _fail(f"LogRing maxlen {[e['text'] for e in _small.tail()]}")
finally:
    _shutil.rmtree(_tmp, ignore_errors=True)

print("ok" if not [f for f in failures if f.startswith("20_data:")]  # noqa: F821
      else "FAILED")
