"""Proof: src/server/app.py and the phase-1 routes, under FastAPI's TestClient.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The
DriverManager is built but its thread is never started, so every command a
route accepts is a dict left on manager.cmd_queue for this proof to read
and discard; nothing opens a browser. The operator's real config is touched
in exactly two keys - web_password_hash (set to a throwaway hash so the
login route has something to check) and web_session_secret (minted by
create_app when absent) - and both are put back in the finally block. The
one verify_*@example.com row the link round trip inserts is deleted there
too. No Google, no Brave directory.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("server routes")  # noqa: F821
import queue as _q  # noqa: E402
import shutil as _sh  # noqa: E402
import tempfile as _tf  # noqa: E402
import threading as _th  # noqa: E402
import warnings as _warnings  # noqa: E402
from pathlib import Path as _P  # noqa: E402

# starlette 1.6 warns that httpx (not httpx2) drives its TestClient; the
# proof works either way and the warning is not a finding.
_warnings.filterwarnings("ignore", message=".*httpx.*", module="starlette.*")
_warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.*")

from fastapi.testclient import TestClient as _TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect as _WSDisconnect  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.server import app as _appmod  # noqa: E402
from src.server import auth as _auth  # noqa: E402
from src.server.events import EventBridge as _EventBridge  # noqa: E402
from src.server.logbuf import LogRing as _LogRing  # noqa: E402
from src.server.state import AppState as _AppState  # noqa: E402
from src.storage import config_manager as _cfg  # noqa: E402
from src.storage import database as _db  # noqa: E402

_PASS = "verify-pass-123"
_LINK_USER = "verify_link@example.com"
_PENDING_USER = "verify_pending@example.com"


def _fail(msg):
    failures.append(f"server: {msg}")  # noqa: F821


def _restore_setting(key, value):
    """Put one config key back exactly as it was: absent stays absent."""
    config = _cfg._load_config()
    settings = config.setdefault("settings", {})
    if value is None:
        settings.pop(key, None)
    else:
        settings[key] = value
    _cfg._save_config(config)


def _drain_cmds(manager):
    out = []
    while True:
        try:
            out.append(manager.cmd_queue.get_nowait())
        except _q.Empty:
            return out


def _expect_cmd(manager, resp, status, ctype, what):
    """One accepted route -> one command of the expected type on the queue."""
    cmds = _drain_cmds(manager)
    if resp.status_code != status:
        _fail(f"{what}: status {resp.status_code} body {resp.text[:120]}")
    if status == 202 and resp.json() != {"accepted": True}:
        _fail(f"{what}: body {resp.text[:120]}")
    if [c.get("type") for c in cmds] != [ctype]:
        _fail(f"{what}: queued {[c.get('type') for c in cmds]}, expected [{ctype!r}]")
    return cmds[0] if cmds else {}


def _recv(ws, timeout=3.0):
    """ws.receive_json() with a deadline, so a wiring bug fails the proof
    instead of hanging verify.py."""
    box = _q.Queue()

    def _get():
        try:
            box.put(ws.receive_json())
        except BaseException as e:  # noqa: BLE001 - reported to the proof
            box.put(e)

    _th.Thread(target=_get, daemon=True).start()
    try:
        got = box.get(timeout=timeout)
    except _q.Empty:
        return None
    return got


def _recv_until(ws, rtype, limit=12):
    """Events arrive in the bridge's order (log lines first); read past
    them to the one this step is about."""
    seen = []
    for _ in range(limit):
        ev = _recv(ws)
        if not isinstance(ev, dict):
            return None, seen
        seen.append(ev.get("type"))
        if ev.get("type") == rtype:
            return ev, seen
    return None, seen


_prev_hash = _cfg.get_setting(_auth.HASH_KEY)
_prev_secret = _cfg.get_setting(_auth.SECRET_KEY)
_tmp = _P(_tf.mkdtemp(prefix="verify_server_"))
_m = _DM()
_m.log = lambda _msg: None      # the driver logs non-ASCII; keep stdout clean
_ring = _LogRing(log_dir=_tmp / "logs")
_ring.write("verify line one")
_ring.write("verify line two")
_ring.write("verify line three")

try:
    _cfg.save_setting(_auth.HASH_KEY, _auth.hash_password(_PASS))
    _state = _AppState()
    _bridge = _EventBridge(_m, _state, _ring)

    # ── module surface the plan names ─────────────────────────────────
    _expected_uses = ("login_accounts", "check_login_status", "auto_setup_profile",
                      "auto_setup_all_profiles", "accept_all_pending_requests",
                      "start_profile", "stop_watch", "cleanup", "send_user_response",
                      "share", "share_to_timeline", "share_to_groups",
                      "share_to_groups_bulk", "join_group", "fetch_my_groups",
                      "fetch_my_groups_bulk", "post_to_timeline", "run_queue",
                      "watch_url")
    if tuple(_appmod.USES) != _expected_uses:
        _fail(f"USES={_appmod.USES}")
    for _name in _appmod.USES:
        if not callable(getattr(_DM, _name, None)):
            _fail(f"USES names {_name}, which DriverManager lacks")

    _app = _appmod.create_app(_m, state=_state, logring=_ring,
                              bridge=_bridge, dev=False,
                              web_dist=_tmp / "no-such-dist")
    _st = _app.state
    for _attr in ("manager", "appstate", "logring", "bridge",
                  "sessions", "limiter", "allowed_origins"):
        if not hasattr(_st, _attr):
            _fail(f"app.state lacks {_attr}")
    if _st.bridge is not _bridge or _st.appstate is not _state:
        _fail("create_app did not keep the bridge/state it was given")
    def _walk(routes):
        # FastAPI 0.141 keeps an included router as one nested entry that
        # points back at the router; older releases flattened the routes.
        for r in routes:
            inner = getattr(getattr(r, "original_router", None), "routes", None)
            if inner is not None:
                yield from _walk(inner)
            elif hasattr(r, "path"):
                for m in (getattr(r, "methods", None) or {"WS"}):
                    yield (m, r.path)

    _routes = set(_walk(_app.routes))
    for _want in [("POST", "/api/login"), ("POST", "/api/logout"),
                  ("GET", "/api/health"), ("GET", "/api/state"),
                  ("GET", "/api/accounts"), ("POST", "/api/accounts/login"),
                  ("POST", "/api/accounts/login-pending"),
                  ("POST", "/api/accounts/check-login"),
                  ("POST", "/api/accounts/auto-setup"),
                  ("POST", "/api/accounts/auto-setup-all"),
                  ("POST", "/api/accounts/accept-pending"),
                  ("POST", "/api/accounts/link"),
                  ("DELETE", "/api/accounts/link/{username}"),
                  ("POST", "/api/profiles/launch"), ("GET", "/api/log"),
                  ("POST", "/api/input"), ("POST", "/api/stop"),
                  ("GET", "/api/images/{image_id}"), ("WS", "/ws")]:
        if _want not in _routes:
            _fail(f"route missing: {_want}")

    # Bare create_app builds its own (unstarted) bridge and state.
    _app_bare = _appmod.create_app(_DM(), web_dist=_tmp / "no-such-dist")
    if _app_bare.state.bridge is None or _app_bare.state.bridge.is_alive():
        _fail("bare create_app: bridge missing or started")

    # https base: the cookie is Secure outside --dev and the jar only
    # returns Secure cookies over https.
    with _TestClient(_app, base_url="https://testserver") as _c:
        # ── public vs guarded ─────────────────────────────────────────
        _r = _c.get("/api/health")
        if _r.status_code != 200 or _r.json().get("ok") is not True \
                or "version" not in _r.json():
            _fail(f"/api/health: {_r.status_code} {_r.text[:80]}")
        _r = _c.get("/api/state")
        if _r.status_code != 401 or _r.json() != {"error": "unauthorized"}:
            _fail(f"/api/state without a cookie: {_r.status_code} {_r.text[:80]}")
        try:
            with _c.websocket_connect("/ws"):
                _fail("/ws accepted a connection without a session")
        except _WSDisconnect as _e:
            if _e.code != 4401:
                _fail(f"/ws rejected with close code {_e.code}, expected 4401")

        # ── login: 5 misses then 429, from one address ────────────────
        _bad_ip = {"X-Forwarded-For": "10.9.9.9"}
        for _i in range(5):
            _r = _c.post("/api/login", json={"password": "wrong-pass"}, headers=_bad_ip)
            if _r.status_code != 401:
                _fail(f"bad login #{_i + 1}: {_r.status_code}")
        _r = _c.post("/api/login", json={"password": "wrong-pass"}, headers=_bad_ip)
        if _r.status_code != 429:
            _fail(f"6th bad login: {_r.status_code}, expected 429")
        _r = _c.post("/api/login", json={"password": _PASS}, headers=_bad_ip)
        if _r.status_code != 429:
            _fail(f"right password while limited: {_r.status_code}, expected 429")
        if _c.cookies.get(_auth.COOKIE):
            _fail("a cookie was set by a refused login")

        # ── login: the right password from another address ────────────
        _r = _c.post("/api/login", json={"password": _PASS})
        if _r.status_code != 204:
            _fail(f"good login: {_r.status_code} {_r.text[:80]}")
        _set_cookie = _r.headers.get("set-cookie", "")
        _lc = _set_cookie.lower()
        for _part in (f"{_auth.COOKIE}=", "httponly", "samesite=lax", "path=/",
                      "max-age=2592000", "secure"):
            if _part not in _lc:
                _fail(f"Set-Cookie lacks {_part!r}: {_set_cookie[:160]}")
        _token = _c.cookies.get(_auth.COOKIE)
        if not _token or not _st.sessions.check(_token):
            _fail("login cookie is not a valid session token")
        _ws_headers = {"cookie": f"{_auth.COOKIE}={_token}"}

        _r = _c.get("/api/state")
        if _r.status_code != 200:
            _fail(f"/api/state with a cookie: {_r.status_code}")
        else:
            _body = _r.json()
            for _key in ("run", "last_run_summary", "pending_input", "login_run_active",
                         "scan_active", "system", "bridge_alive",
                         "version", "counts"):
                if _key not in _body:
                    _fail(f"/api/state lacks {_key}")
            if "total" not in (_body.get("counts") or {}):
                _fail(f"/api/state counts={_body.get('counts')}")

        # ── CSRF: a cross-site Origin is refused before anything queues ─
        _r = _c.post("/api/stop", headers={"Origin": "https://evil.example"})
        if _r.status_code != 403 or "error" not in _r.json():
            _fail(f"evil Origin: {_r.status_code} {_r.text[:80]}")
        if _drain_cmds(_m):
            _fail("a refused Origin still queued a command")
        _r = _c.post("/api/stop", headers={"Origin": "https://testserver"})
        if _r.status_code != 202:
            _fail(f"same-origin POST: {_r.status_code} {_r.text[:80]}")
        if [c.get("type") for c in _drain_cmds(_m)] != ["stop_watch", "cleanup"]:
            _fail("/api/stop did not queue stop_watch then cleanup")

        # ── commands -> manager.cmd_queue ─────────────────────────────
        _r = _c.post("/api/accounts/login", json={"usernames": []})
        if _r.status_code != 400:
            _fail(f"login with no usernames: {_r.status_code}")
        _cmd = _expect_cmd(_m, _c.post("/api/accounts/login",
                                       json={"usernames": ["verify_a@example.com"]}),
                           202, "login_accounts", "/api/accounts/login")
        if _cmd.get("usernames") != ["verify_a@example.com"]:
            _fail(f"login_accounts usernames={_cmd.get('usernames')}")
        if not _state.login_run_active:
            _fail("/api/accounts/login did not set login_run_active")
        _r = _c.post("/api/accounts/login", json={"usernames": ["verify_b@example.com"]})
        if _r.status_code != 409 or _r.json() != {"error": "a login run is active"}:
            _fail(f"second login while active: {_r.status_code} {_r.text[:80]}")
        if _drain_cmds(_m):
            _fail("the 409 login still queued a command")
        _r = _c.post("/api/accounts/login-pending")
        if _r.status_code != 409:
            _fail(f"login-pending while active: {_r.status_code}")
        _state.login_run_active = False

        # login-pending: a pending account with a Brave profile is sent.
        _db.upsert_account(9901, "Verify Pending", _PENDING_USER)
        _db.link_account(_PENDING_USER, "VerifyProfile")
        _cmd = _expect_cmd(_m, _c.post("/api/accounts/login-pending"),
                           202, "login_accounts", "/api/accounts/login-pending")
        if _PENDING_USER not in (_cmd.get("usernames") or []):
            _fail(f"login-pending left out {_PENDING_USER}: {_cmd.get('usernames')}")
        _state.login_run_active = False

        _expect_cmd(_m, _c.post("/api/accounts/check-login", json={"profile_names": None}),
                    202, "check_login_status", "/api/accounts/check-login")
        if not _state.scan_active:
            _fail("/api/accounts/check-login did not set scan_active")
        _r = _c.post("/api/accounts/check-login", json={"profile_names": ["P"]})
        if _r.status_code != 409:
            _fail(f"check-login while scanning: {_r.status_code}")
        _state.scan_active = False
        _cmd = _expect_cmd(_m, _c.post("/api/accounts/check-login",
                                       json={"profile_names": ["P"]}),
                           202, "check_login_status", "check-login with names")
        if _cmd.get("profile_names") != ["P"]:
            _fail(f"check-login profile_names={_cmd.get('profile_names')}")
        _state.scan_active = False

        _cmd = _expect_cmd(_m, _c.post("/api/accounts/auto-setup",
                                       json={"profile_name": "P", "target_friends": 7}),
                           202, "auto_setup_profile", "/api/accounts/auto-setup")
        if _cmd.get("profile_name") != "P" or _cmd.get("target_friends") != 7:
            _fail(f"auto_setup_profile cmd={_cmd}")
        _cmd = _expect_cmd(_m, _c.post("/api/accounts/auto-setup-all",
                                       json={"profile_names": ["P"], "bio": "hi"}),
                           202, "auto_setup_all", "/api/accounts/auto-setup-all")
        if _cmd.get("profile_names") != ["P"] or _cmd.get("bio") != "hi" \
                or _cmd.get("connect_friends") is not True:
            _fail(f"auto_setup_all cmd={_cmd}")
        _cmd = _expect_cmd(_m, _c.post("/api/accounts/accept-pending",
                                       json={"profile_names": ["P"]}),
                           202, "accept_all_pending", "/api/accounts/accept-pending")
        if _cmd.get("profile_names") != ["P"]:
            _fail(f"accept_all_pending cmd={_cmd}")
        _cmd = _expect_cmd(_m, _c.post("/api/profiles/launch", json={"profile_name": "P"}),
                           202, "start_profile", "/api/profiles/launch")
        if _cmd.get("profile_name") != "P":
            _fail(f"start_profile cmd={_cmd}")
        _r = _c.post("/api/profiles/launch", json={})
        if _r.status_code != 400 or "error" not in _r.json():
            _fail(f"launch without a body: {_r.status_code} {_r.text[:80]}")

        # ── link / unlink round trip ──────────────────────────────────
        _db.upsert_account(9902, "Verify Link", _LINK_USER)
        _r = _c.post("/api/accounts/link",
                     json={"username": _LINK_USER, "profile_name": "VerifyProfile"})
        if _r.status_code != 200 or _r.json() != {"ok": True}:
            _fail(f"/api/accounts/link: {_r.status_code} {_r.text[:80]}")
        _row = next((a for a in _db.list_accounts() if a["username"] == _LINK_USER), {})
        if _row.get("linked_profile") != "VerifyProfile":
            _fail(f"link did not reach the database: {_row}")
        _r = _c.get("/api/accounts")
        _rows = _r.json().get("rows", []) if _r.status_code == 200 else []
        _mine = next((x for x in _rows if x.get("username") == _LINK_USER), None)
        if _mine is None or _mine.get("linked_profile") != "VerifyProfile":
            _fail(f"/api/accounts row for {_LINK_USER}: {_mine}")
        _r = _c.delete(f"/api/accounts/link/{_LINK_USER}")
        if _r.status_code != 200 or _r.json() != {"ok": True}:
            _fail(f"DELETE link: {_r.status_code} {_r.text[:80]}")
        _row = next((a for a in _db.list_accounts() if a["username"] == _LINK_USER), {})
        if _row.get("linked_profile"):
            _fail(f"unlink left linked_profile={_row.get('linked_profile')!r}")
        _r = _c.post("/api/accounts/link",
                     json={"username": "verify_nobody@example.com", "profile_name": "X"})
        if _r.status_code != 404:
            _fail(f"link of an unknown username: {_r.status_code}")

        # ── log tail, input with nothing open, images off the list ────
        _r = _c.get("/api/log", params={"tail": 2})
        _lines = _r.json().get("lines") if _r.status_code == 200 else None
        if not isinstance(_lines, list) or len(_lines) > 2:
            _fail(f"/api/log?tail=2: {_r.status_code} {_r.text[:120]}")
        elif _lines and _lines[-1].get("text") != "verify line three":
            _fail(f"/api/log tail is not the newest lines: {_lines}")
        _r = _c.post("/api/input", json={"profile_pic": None, "cancel": True})
        if _r.status_code != 409:
            _fail(f"/api/input with no prompt open: {_r.status_code}")
        _r = _c.get("/api/images/nope")
        if _r.status_code != 404:
            _fail(f"/api/images/nope: {_r.status_code}")

        # ── the socket: state first, then whatever the bridge sends ───
        with _c.websocket_connect("/ws", headers=_ws_headers) as _ws:
            _first = _recv(_ws)
            if not isinstance(_first, dict) or _first.get("type") != "state":
                _fail(f"first ws message: {_first!r}"[:160])
            elif "counts" not in _first:
                _fail("first ws state event lacks counts")
            _bridge.broadcast({"type": "login_accounts_progress", "current": 1, "total": 1})
            _got = _recv(_ws, timeout=1.0)
            if _got != {"type": "login_accounts_progress", "current": 1, "total": 1}:
                _fail(f"broadcast did not reach the socket: {_got!r}"[:160])

            # needs_input round trip: prompt -> event -> /api/input -> worker
            _img = _tmp / "pic.jpg"
            _img.write_bytes(b"verify-image-bytes")
            _bridge.handle_result({"type": "auto_setup_images_preview",
                                   "profile_name": "P", "images": [str(_img)],
                                   "needs_pic": True})
            _ev, _seen = _recv_until(_ws, "needs_input")
            if _ev is None:
                _fail(f"needs_input never arrived; saw {_seen}")
            else:
                _images = _ev.get("images") or [{}]
                _id = _images[0].get("id")
                _r = _c.get(f"/api/images/{_id}")
                if _r.status_code != 200 or _r.content != b"verify-image-bytes":
                    _fail(f"/api/images/{_id}: {_r.status_code}")
                _r = _c.post("/api/input", json={"profile_pic": _id, "cancel": False})
                if _r.status_code != 200:
                    _fail(f"/api/input: {_r.status_code} {_r.text[:80]}")
                try:
                    _resp = _m._user_response_queue.get_nowait()
                except _q.Empty:
                    _resp = None
                if _resp != {"profile_pic": str(_img), "cancel": False}:
                    _fail(f"worker received {_resp}")
                if _state.pending_input is not None:
                    _fail("/api/input left the prompt open")
                _r = _c.get(f"/api/images/{_id}")
                if _r.status_code != 404:
                    _fail("an answered prompt's image is still served")

        # ── static: nothing built -> the one-line hint, never index.html ─
        for _path in ("/", "/accounts"):
            _r = _c.get(_path)
            if _r.status_code != 200 or "BUILD_WEB.bat" not in _r.text:
                _fail(f"GET {_path} without web/dist: {_r.status_code} {_r.text[:80]}")
        _r = _c.get("/api/no-such-route")
        if _r.status_code != 404:
            _fail(f"unknown /api path: {_r.status_code}, expected 404")

        # ── logout clears the cookie ──────────────────────────────────
        _r = _c.post("/api/logout")
        if _r.status_code != 204:
            _fail(f"/api/logout: {_r.status_code}")
        _r = _c.get("/api/state")
        if _r.status_code != 401:
            _fail(f"/api/state after logout: {_r.status_code}")

    # ── static: a built dist is served with the SPA fallback ──────────
    _dist = _tmp / "dist"
    (_dist / "assets").mkdir(parents=True)
    (_dist / "index.html").write_text("<!doctype html><title>verify index</title>",
                                      encoding="utf-8")
    (_dist / "assets" / "verify.js").write_text("// verify asset", encoding="utf-8")
    (_dist / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    _app2 = _appmod.create_app(_DM(), web_dist=_dist)
    with _TestClient(_app2) as _c2:
        for _path in ("/", "/accounts", "/log"):
            _r = _c2.get(_path)
            if _r.status_code != 200 or "verify index" not in _r.text:
                _fail(f"GET {_path} with web/dist: {_r.status_code} {_r.text[:80]}")
        _r = _c2.get("/assets/verify.js")
        if _r.status_code != 200 or "verify asset" not in _r.text:
            _fail(f"GET /assets/verify.js: {_r.status_code}")
        _r = _c2.get("/manifest.webmanifest")
        if _r.status_code != 200 or _r.text != "{}":
            _fail(f"GET /manifest.webmanifest: {_r.status_code}")
        _r = _c2.get("/api/state")
        if _r.status_code != 401:
            _fail(f"/api/state on the built app: {_r.status_code}, expected 401")
        _r = _c2.get("/../server.py")
        if _r.status_code == 200 and "uvicorn" in _r.text:
            _fail("static fallback served a file outside web/dist")
finally:
    _restore_setting(_auth.HASH_KEY, _prev_hash)
    _restore_setting(_auth.SECRET_KEY, _prev_secret)
    _ring.close()
    _sh.rmtree(_tmp, ignore_errors=True)
    _db._get_conn().execute(
        "DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
    _db._get_conn().commit()

print("ok" if not [f for f in failures if f.startswith("server:")]  # noqa: F821
      else "FAILED")
