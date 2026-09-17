"""Proof: phase 2 is wired into the real app, and the queue is shared.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The app is
the one create_app() builds - not a stand-in router - so a route module that
exists on disk but was never included fails here rather than in a browser.
Three things are asserted that no single route module can assert about
itself: every new path is behind the session guard, GET /api/state carries
the queue so a device that just woke needs one request, and the store the
routes mutate is the list every other device then reads.

The DriverManager thread is never started, so a command a route accepts is a
dict left on manager.cmd_queue for this proof to read and discard; nothing
opens a browser. The operator's config is touched in web_password_hash and
web_session_secret only, both restored in the finally block, and
events.cfg.save_setting is stubbed so the batch this proof fakes cannot
overwrite the real last-run summary. Uploads are pointed at a temp folder.
No Google, no Facebook, no Brave directory.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("phase-2 wiring")  # noqa: F821
import queue as _q  # noqa: E402
import shutil as _sh  # noqa: E402
import tempfile as _tf  # noqa: E402
import warnings as _warnings  # noqa: E402
from pathlib import Path as _P  # noqa: E402

_warnings.filterwarnings("ignore", message=".*httpx.*", module="starlette.*")
_warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.*")

from fastapi.testclient import TestClient as _TestClient  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.server import app as _appmod  # noqa: E402
from src.server import auth as _auth  # noqa: E402
from src.server import events as _evmod  # noqa: E402
from src.server import queue_store as _qs  # noqa: E402
from src.server import uploads as _uploads  # noqa: E402
from src.server.events import EventBridge as _EventBridge  # noqa: E402
from src.server.logbuf import LogRing as _LogRing  # noqa: E402
from src.server.state import AppState as _AppState  # noqa: E402
from src.storage import config_manager as _cfg  # noqa: E402

_PASS = "verify-wire-123"
_PROFILE = "VerifyWireProfile"
_URL = "https://www.facebook.com/verify/posts/1"

# The DriverManager helpers phase 2 reaches. app.USES must name them, or a
# button exists on the phone that proofs/24_parity.py still calls unrouted.
_PHASE2_USES = ("share", "share_to_timeline", "share_to_groups",
                "share_to_groups_bulk", "join_group", "fetch_my_groups",
                "fetch_my_groups_bulk", "post_to_timeline", "run_queue",
                "watch_url")

# Every path phase 2 added, with a body that is valid enough to get past
# FastAPI: the guard runs in middleware, before validation, so the 401 check
# below does not depend on the body at all.
_NEW_ROUTES = (
    ("GET", "/api/queue", None),
    ("POST", "/api/queue/add", {"profile_names": [_PROFILE]}),
    ("POST", "/api/queue/remove", {"id": "q1"}),
    ("POST", "/api/queue/clear", {}),
    ("POST", "/api/queue/run", None),
    ("POST", "/api/queue/watch", {"url": _URL}),
    ("POST", "/api/queue/stop-watch", None),
    ("GET", "/api/groups", None),
    ("POST", "/api/groups/fetch", {"profile_names": [_PROFILE]}),
    ("POST", "/api/compose/share", {"post_url": _URL, "group_name": "G"}),
    ("POST", "/api/compose/share-timeline", {"post_url": _URL}),
    ("POST", "/api/compose/share-groups",
     {"post_url": _URL, "groups": [{"name": "G"}]}),
    ("POST", "/api/compose/share-bulk",
     {"post_url": _URL, "groups": [{"name": "G", "url": _URL,
                                    "profiles": [_PROFILE]}]}),
    ("POST", "/api/compose/join", {"urls": [_URL]}),
    ("POST", "/api/compose/post-timeline", {"text": "hello"}),
    ("POST", "/api/uploads", None),
)


def _fail(msg):
    failures.append(f"wiring: {msg}")  # noqa: F821


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


def _send(client, method, path, body):
    if method == "GET":
        return client.get(path)
    if body is None:
        return client.post(path)
    return client.post(path, json=body)


def _expect(resp, status, what):
    if resp.status_code != status:
        _fail(f"{what}: status {resp.status_code} body {resp.text[:120]}")
        return {}
    try:
        return resp.json()
    except ValueError:
        return {}


def _queued(manager, what, expect_type):
    """One accepted route -> one command of the expected type on the queue."""
    cmds = _drain_cmds(manager)
    if [c.get("type") for c in cmds] != [expect_type]:
        _fail(f"{what}: queued {[c.get('type') for c in cmds]}, "
              f"expected [{expect_type!r}]")
    return cmds[0] if cmds else {}


def _state_queue(client):
    resp = client.get("/api/state")
    if resp.status_code != 200:
        _fail(f"/api/state: {resp.status_code} {resp.text[:80]}")
        return None
    body = resp.json()
    if "queue" not in body:
        _fail("/api/state carries no 'queue' key")
        return None
    return body["queue"]


_prev_hash = _cfg.get_setting(_auth.HASH_KEY)
_prev_secret = _cfg.get_setting(_auth.SECRET_KEY)
_real_save = _evmod.cfg.save_setting
_real_upload_dir = _uploads.UPLOAD_DIR
_tmp = _P(_tf.mkdtemp(prefix="verify_wiring_"))
_m = _DM()
_m.log = lambda _msg: None      # the driver logs non-ASCII; keep stdout clean
_ring = _LogRing(log_dir=_tmp / "logs")

try:
    _cfg.save_setting(_auth.HASH_KEY, _auth.hash_password(_PASS))
    _evmod.cfg.save_setting = lambda *_a, **_k: None
    _uploads.UPLOAD_DIR = _tmp / "uploads"
    _state = _AppState()
    _bridge = _EventBridge(_m, None, _state, _ring)
    _app = _appmod.create_app(_m, None, state=_state, logring=_ring,
                              bridge=_bridge, dev=False,
                              web_dist=_tmp / "no-such-dist")

    # -- the app holds one store, and the bridge can reach it ------------
    _store = getattr(_app.state, "queue", None)
    if not isinstance(_store, _qs.QueueStore):
        _fail(f"app.state.queue is {type(_store).__name__}, not a QueueStore")
    if getattr(_bridge, "queue", None) is not _store:
        _fail("create_app did not hand the store to the bridge")

    # -- USES names every phase-2 helper, and each one exists -----------
    _missing = [n for n in _PHASE2_USES if n not in _appmod.USES]
    if _missing:
        _fail(f"app.USES lacks the phase-2 helpers {_missing}")
    for _name in _appmod.USES:
        if not callable(getattr(_DM, _name, None)):
            _fail(f"app.USES names {_name!r}, which DriverManager lacks")

    # -- every new path is registered -----------------------------------
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

    _registered = set(_walk(_app.routes))
    for _method, _path, _ in _NEW_ROUTES:
        if (_method, _path) not in _registered:
            _fail(f"route never included: {_method} {_path}")

    with _TestClient(_app, base_url="https://testserver") as _c:
        # -- every new path is guarded -----------------------------------
        for _method, _path, _body in _NEW_ROUTES:
            _r = _send(_c, _method, _path, _body)
            if _r.status_code != 401 or _r.json() != {"error": "unauthorized"}:
                _fail(f"{_method} {_path} without a session: "
                      f"{_r.status_code} {_r.text[:80]}")
        if _drain_cmds(_m):
            _fail("a route refused for want of a session still queued a command")
        _r = _c.get("/api/health")
        if _r.status_code != 200:
            _fail(f"/api/health stopped being public: {_r.status_code}")

        _r = _c.post("/api/login", json={"password": _PASS})
        if _r.status_code != 204:
            _fail(f"login: {_r.status_code} {_r.text[:80]}")

        # -- the shared queue: add, mirror, remove, clear ----------------
        _body = _expect(_c.get("/api/queue"), 200, "GET /api/queue")
        if _body.get("items") != [] or _body.get("running") is not False:
            _fail(f"GET /api/queue on an empty store: {_body}")
        if _state_queue(_c) != []:
            _fail("/api/state starts with a non-empty queue")

        _r = _c.post("/api/queue/add", json={"profile_names": []})
        _expect(_r, 400, "/api/queue/add with no profiles")
        _item = {"profile_names": [_PROFILE], "action_type": "group",
                 "post_url": _URL, "group_name": "Verify Group"}
        _body = _expect(_c.post("/api/queue/add", json=_item), 202,
                        "/api/queue/add")
        if _body != {"accepted": True, "added": 1}:
            _fail(f"/api/queue/add body: {_body}")
        if _drain_cmds(_m):
            _fail("adding to the queue queued a command")

        _mirrored = _state_queue(_c)
        if not _mirrored or _mirrored[0].get("profile_name") != _PROFILE:
            _fail(f"/api/state queue after an add: {_mirrored}")
        _first = (_mirrored or [{}])[0]
        if _first.get("group_name") != "Verify Group" or not _first.get("id"):
            _fail(f"/api/state queue item: {_first}")
        if _mirrored != _store.items():
            _fail(f"/api/state queue {_mirrored} != store {_store.items()}")

        _expect(_c.post("/api/queue/remove", json={"id": "no-such-id"}), 404,
                "/api/queue/remove with an unknown id")
        _body = _expect(_c.post("/api/queue/remove",
                                json={"id": _first.get("id", "")}), 200,
                        "/api/queue/remove")
        if _body != {"ok": True}:
            _fail(f"/api/queue/remove body: {_body}")
        if _state_queue(_c) != []:
            _fail("a removed item is still on /api/state")

        _c.post("/api/queue/add", json=_item)
        _c.post("/api/queue/add", json=_item)
        _body = _expect(_c.post("/api/queue/clear"), 200, "/api/queue/clear")
        if _body != {"ok": True, "removed": 2}:
            _fail(f"/api/queue/clear body: {_body}")
        if _state_queue(_c) != [] or _store.items():
            _fail("clear left items behind")

        # -- run: empty is a 400, a second press is a 409 ----------------
        _expect(_c.post("/api/queue/run"), 400, "/api/queue/run with nothing queued")
        _c.post("/api/queue/add", json=_item)
        _body = _expect(_c.post("/api/queue/run"), 202, "/api/queue/run")
        if _body != {"accepted": True}:
            _fail(f"/api/queue/run body: {_body}")
        _cmd = _queued(_m, "/api/queue/run", "run_queue")
        _sent = (_cmd.get("items") or [{}])[0]
        if "id" in _sent or _sent.get("profile_name") != _PROFILE \
                or _sent.get("post_url") != _URL:
            _fail(f"run_queue was handed {_sent}")
        if _state.run is None or _state.run.kind != "batch":
            _fail(f"/api/queue/run left run={_state.run}")
        _body = _expect(_c.get("/api/queue"), 200, "GET /api/queue while running")
        if _body.get("running") is not True:
            _fail(f"GET /api/queue during a run: {_body}")
        _expect(_c.post("/api/queue/run"), 409, "a second /api/queue/run")
        if _drain_cmds(_m):
            _fail("the refused second run still queued a command")

        # -- batch_result empties the shared list, as queue_tab did ------
        _before = len(_bridge.recent)
        _bridge.handle_result({"type": "batch_result", "ok": True, "total": 1})
        if _store.items():
            _fail(f"batch_result left the queue holding {_store.items()}")
        if _state_queue(_c) != []:
            _fail("batch_result left items on /api/state")
        _after = [e.get("type") for e in list(_bridge.recent)[_before:]]
        if "queue_changed" not in _after:
            _fail(f"batch_result broadcast no queue_changed; sent {_after}")
        if _state.run is not None:
            _fail(f"batch_result left run={_state.run}")

        # -- watch and stop-watch ----------------------------------------
        _expect(_c.post("/api/queue/watch", json={"url": "not-a-link"}), 400,
                "/api/queue/watch with a bad url")
        _expect(_c.post("/api/queue/watch",
                        json={"url": _URL, "minutes": 3,
                              "profile_names": [_PROFILE]}), 202,
                "/api/queue/watch")
        _cmd = _queued(_m, "/api/queue/watch", "watch_url")
        if _cmd.get("url") != _URL or _cmd.get("profile_names") != [_PROFILE]:
            _fail(f"watch_url cmd={_cmd}")
        _expect(_c.post("/api/queue/stop-watch"), 202, "/api/queue/stop-watch")
        _queued(_m, "/api/queue/stop-watch", "stop_watch")

        # -- groups ------------------------------------------------------
        _body = _expect(_c.get("/api/groups"), 200, "GET /api/groups")
        if not isinstance(_body.get("groups"), list):
            _fail(f"GET /api/groups: {_body}")
        _expect(_c.post("/api/groups/fetch", json={"profile_names": [_PROFILE]}),
                202, "/api/groups/fetch with one name")
        _cmd = _queued(_m, "/api/groups/fetch", "fetch_my_groups")
        if _cmd.get("profile_name") != _PROFILE:
            _fail(f"fetch_my_groups cmd={_cmd}")
        _expect(_c.post("/api/groups/fetch", json={"profile_names": None}), 202,
                "/api/groups/fetch with no names")
        _queued(_m, "/api/groups/fetch (all)", "fetch_my_groups_bulk")

        # -- compose: one route per DriverManager helper ------------------
        for _path, _body_in, _ctype in (
            ("/api/compose/share", {"post_url": _URL, "group_name": "G"}, "share"),
            ("/api/compose/share-timeline", {"post_url": _URL}, "share_to_timeline"),
            ("/api/compose/share-groups",
             {"post_url": _URL, "groups": [{"name": "G"}]}, "share_to_groups"),
            ("/api/compose/share-bulk",
             {"post_url": _URL,
              "groups": [{"name": "G", "url": _URL, "profiles": [_PROFILE]}]},
             "share_to_groups_bulk"),
            ("/api/compose/join", {"urls": [_URL]}, "join_group_bulk"),
            ("/api/compose/post-timeline", {"text": "verify post"},
             "post_to_timeline"),
        ):
            _expect(_c.post(_path, json=_body_in), 202, _path)
            _queued(_m, _path, _ctype)
        _expect(_c.post("/api/compose/share",
                        json={"post_url": "nope", "group_name": "G"}), 400,
                "/api/compose/share with a bad url")
        if _drain_cmds(_m):
            _fail("a refused compose body still queued a command")

        # -- uploads: staged under the temp folder, nothing queued --------
        _body = _expect(
            _c.post("/api/uploads",
                    files={"file": ("verify.png", b"not-a-real-png", "image/png")}),
            200, "/api/uploads")
        _saved = _P(_body.get("path", ""))
        if not _saved.is_file() or not _saved.is_relative_to(
                _P(_uploads.UPLOAD_DIR).resolve()):
            _fail(f"/api/uploads stored at {_body.get('path')!r}")
        _expect(_c.post("/api/uploads",
                        files={"file": ("verify.exe", b"x", "application/octet-stream")}),
                400, "/api/uploads with a refused type")
        if _drain_cmds(_m):
            _fail("an upload queued a command")

        # -- a run in progress greys compose, as the Tk buttons were ------
        from src.server.state import RunState as _RunState
        _state.run = _RunState(kind="share", message="verify")
        for _path, _body_in in (("/api/compose/share",
                                 {"post_url": _URL, "group_name": "G"}),
                                ("/api/groups/fetch", {"profile_names": None})):
            _r = _c.post(_path, json=_body_in)
            if _r.status_code != 409:
                _fail(f"{_path} while a run is on: {_r.status_code}")
        _state.run = None
        if _drain_cmds(_m):
            _fail("a 409 still queued a command")
finally:
    _evmod.cfg.save_setting = _real_save
    _uploads.UPLOAD_DIR = _real_upload_dir
    _restore_setting(_auth.HASH_KEY, _prev_hash)
    _restore_setting(_auth.SECRET_KEY, _prev_secret)
    _ring.close()
    _sh.rmtree(_tmp, ignore_errors=True)

print("ok" if not [f for f in failures if f.startswith("wiring:")]  # noqa: F821
      else "FAILED")
