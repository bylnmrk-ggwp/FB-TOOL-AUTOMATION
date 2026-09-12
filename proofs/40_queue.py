"""Proof: src/server/queue_store.py and the queue routes.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The store
is exercised directly; the routes are driven over a bare FastAPI built
here rather than through create_app, so this proof needs no session cookie
and does not care what the app factory looks like while it is being
written. The DriverManager is constructed but never started, so every
accepted command is a dict left on cmd_queue for this proof to read and
discard - nothing opens a browser, nothing reaches Facebook, and no row or
config key is written.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("queue store and routes")  # noqa: F821
import queue as _q  # noqa: E402
import threading as _threading  # noqa: E402
import warnings as _warnings  # noqa: E402

_warnings.filterwarnings("ignore", message=".*httpx.*", module="starlette.*")
_warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.*")

from fastapi import FastAPI as _FastAPI  # noqa: E402
from fastapi.testclient import TestClient as _TestClient  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.server.queue_store import QueueStore as _QueueStore  # noqa: E402
from src.server.routes import queue as _queue_routes  # noqa: E402
from src.server.state import AppState as _AppState  # noqa: E402

# Every key DriverManager._process_one reads off a queue item (verified
# against src/core/driver_manager.py). The store may hand the worker these
# and nothing else.
_WORKER_KEYS = {"profile_name", "action_type", "post_url", "group_name",
                "comment_text", "reaction", "text", "image_paths"}

_URL = "https://www.facebook.com/verify/posts/1"


def _fail(msg):
    failures.append(f"queue: {msg}")  # noqa: F821


class _Bridge:
    """All push_state needs is broadcast(); recording the events is how
    this proof sees that the other devices were told."""

    def __init__(self):
        self.events = []

    def broadcast(self, event):
        self.events.append(event)


def _drain_cmds(manager):
    out = []
    while True:
        try:
            out.append(manager.cmd_queue.get_nowait())
        except _q.Empty:
            return out


def _rejects(store, payload, what):
    try:
        store.add(payload)
    except ValueError:
        return
    except Exception as e:  # noqa: BLE001 - reported, not raised
        _fail(f"{what}: raised {type(e).__name__} instead of ValueError")
        return
    _fail(f"{what}: accepted")


# ── The store on its own ──────────────────────────────────────────────

_store = _QueueStore()
if len(_store) != 0 or _store.items() != []:
    _fail("a new store is not empty")

_added = _store.add({"profile_name": " P1 ", "post_url": _URL,
                     "group_name": "Verify Group", "comment_text": "hello",
                     "reaction": "like", "nonsense": "drop me"})
if _added.get("profile_name") != "P1":
    _fail(f"profile_name not trimmed: {_added.get('profile_name')!r}")
if _added.get("action_type") != "group":
    _fail(f"default action_type={_added.get('action_type')!r}, expected 'group'")
if "nonsense" in _added:
    _fail("an unknown key survived validation")
if not _added.get("id"):
    _fail("the stored item has no id")
if len(_store) != 1:
    _fail(f"len(store)={len(_store)} after one add")

_second = _store.add({"profile_name": "P2", "action_type": "post_text",
                      "text": "hello world"})
if _second.get("id") == _added.get("id"):
    _fail("two items share one id")

# Every action_type _process_one branches on is accepted.
for _action in ("group", "timeline", "post_text", "react", "comment", "share", "story"):
    _probe = {"profile_name": "P9", "action_type": _action, "post_url": _URL,
              "group_name": "Verify Group", "text": "body", "comment_text": "hi"}
    try:
        _QueueStore().add(_probe)
    except ValueError as e:
        _fail(f"action_type {_action!r} refused: {e}")

# Values the worker reads as strings are coerced, not passed through.
_coerced = _QueueStore().add({"profile_name": "P1", "action_type": "react",
                              "post_url": _URL, "reaction": 7})
if _coerced.get("reaction") != "7":
    _fail(f"reaction not coerced to str: {_coerced.get('reaction')!r}")

_scratch = _QueueStore()
_rejects(_scratch, {"post_url": _URL, "group_name": "G"}, "no profile_name")
_rejects(_scratch, {"profile_name": "   ", "post_url": _URL, "group_name": "G"},
         "blank profile_name")
_rejects(_scratch, {"profile_name": "P1", "action_type": "nope", "post_url": _URL},
         "unknown action_type")
_rejects(_scratch, {"profile_name": "P1", "group_name": "G"}, "no post_url")
_rejects(_scratch, {"profile_name": "P1", "post_url": "javascript:void(0)",
                    "group_name": "G"}, "post_url that is not http")
_rejects(_scratch, {"profile_name": "P1", "post_url": _URL}, "group share with no group")
_rejects(_scratch, {"profile_name": "P1", "action_type": "post_text", "text": " "},
         "text post with no text")
if len(_scratch) != 0:
    _fail(f"a refused item still reached the store ({len(_scratch)})")

# The list the store owns is never handed out.
_rows = _store.items()
_rows[0]["profile_name"] = "mutated"
if _store.items()[0].get("profile_name") != "P1":
    _fail("items() handed out the store's own dict")

_run_items = _store.to_run()
if any("id" in it for it in _run_items):
    _fail("to_run() left the ui id on an item")
if _run_items[0] != {"profile_name": "P1", "action_type": "group", "post_url": _URL,
                     "group_name": "Verify Group", "comment_text": "hello",
                     "reaction": "like"}:
    _fail(f"to_run() group item={_run_items[0]}")
if _run_items[1] != {"profile_name": "P2", "action_type": "post_text",
                     "text": "hello world"}:
    _fail(f"to_run() text item={_run_items[1]}")
for _it in _run_items:
    _extra = set(_it) - _WORKER_KEYS
    if _extra:
        _fail(f"to_run() item carries keys the worker never reads: {sorted(_extra)}")

if _store.remove(99) or _store.remove(-1):
    _fail("remove() of an index that is not there returned True")
if not _store.remove(0) or len(_store) != 1:
    _fail("remove(0) did not drop exactly one item")

_store.replace([{"profile_name": "P3", "action_type": "timeline", "post_url": _URL}])
if len(_store) != 1 or _store.items()[0].get("profile_name") != "P3":
    _fail(f"replace() left {_store.items()}")
try:
    _store.replace([{"profile_name": "P4", "action_type": "timeline", "post_url": _URL},
                    {"profile_name": "", "post_url": _URL}])
except ValueError:
    pass
else:
    _fail("replace() accepted a list with a bad item")
if len(_store) != 1 or _store.items()[0].get("profile_name") != "P3":
    _fail("a refused replace() changed the queue")
if _store.clear() != 1 or len(_store) != 0:
    _fail("clear() did not report and drop every item")

# ── The routes over a bare app ────────────────────────────────────────

_app = _FastAPI()
_app.include_router(_queue_routes.router)
_m = _DM()
_m.log = lambda _msg: None      # the driver logs non-ASCII; keep stdout clean
_state = _AppState()
_bridge = _Bridge()
_st = _app.state
_st.manager = _m
_st.queue = _QueueStore()
_st.appstate = _state
_st.bridge = _bridge
_st.cmd_lock = _threading.Lock()

with _TestClient(_app) as _c:
    _r = _c.get("/api/queue")
    if _r.status_code != 200 or _r.json() != {"items": [], "running": False}:
        _fail(f"GET /api/queue when empty: {_r.status_code} {_r.text[:120]}")

    # One item per profile, as the Tk tab's "All Profiles" quick-add did.
    _r = _c.post("/api/queue/add", json={"profile_names": ["P1", "P2"],
                                         "action_type": "group", "post_url": _URL,
                                         "group_name": "Verify Group",
                                         "comment_text": "hi", "reaction": "like"})
    if _r.status_code != 202 or _r.json() != {"accepted": True, "added": 2}:
        _fail(f"POST /api/queue/add: {_r.status_code} {_r.text[:120]}")
    if len(_st.queue) != 2:
        _fail(f"add for 2 profiles stored {len(_st.queue)} item(s)")
    if not any(e.get("type") == "state" for e in _bridge.events):
        _fail("add did not push the state to the other devices")
    if _drain_cmds(_m):
        _fail("add queued a command; only run does that")

    _r = _c.post("/api/queue/add", json={"profile_names": [], "post_url": _URL,
                                         "group_name": "Verify Group"})
    if _r.status_code != 400:
        _fail(f"add with no profiles: {_r.status_code} {_r.text[:120]}")
    _r = _c.post("/api/queue/add", json={"profile_names": ["P1"],
                                         "action_type": "nope", "post_url": _URL})
    if _r.status_code != 400:
        _fail(f"add with an unknown action_type: {_r.status_code} {_r.text[:120]}")
    _r = _c.post("/api/queue/add", json={"profile_names": ["P1"],
                                         "action_type": "timeline",
                                         "post_url": "not-a-url"})
    if _r.status_code != 400:
        _fail(f"add with a bad post_url: {_r.status_code} {_r.text[:120]}")
    if len(_st.queue) != 2:
        _fail(f"a refused add changed the queue ({len(_st.queue)} items)")

    _body = _c.get("/api/queue").json()
    _ids = [it.get("id") for it in _body.get("items", [])]
    if len(_ids) != 2 or not all(_ids):
        _fail(f"GET /api/queue items={_body.get('items')}")

    _r = _c.post("/api/queue/remove", json={"id": _ids[0]})
    if _r.status_code != 200 or _r.json() != {"ok": True}:
        _fail(f"POST /api/queue/remove: {_r.status_code} {_r.text[:120]}")
    _r = _c.post("/api/queue/remove", json={"id": _ids[0]})
    if _r.status_code != 404:
        _fail(f"remove of an id that is gone: {_r.status_code} {_r.text[:120]}")
    if len(_st.queue) != 1:
        _fail(f"remove left {len(_st.queue)} item(s), expected 1")

    # ── run ───────────────────────────────────────────────────────────
    _expected_items = _st.queue.to_run()
    _r = _c.post("/api/queue/run")
    if _r.status_code != 202 or _r.json() != {"accepted": True}:
        _fail(f"POST /api/queue/run: {_r.status_code} {_r.text[:120]}")
    _cmds = _drain_cmds(_m)
    if [c.get("type") for c in _cmds] != ["run_queue"]:
        _fail(f"run queued {[c.get('type') for c in _cmds]}, expected ['run_queue']")
    elif _cmds[0].get("items") != _expected_items:
        _fail(f"run_queue items={_cmds[0].get('items')}")
    if _state.run is None or _state.run.kind != "batch" or _state.run.total != 1:
        _fail(f"run did not open a batch RunState: {_state.run}")
    _body = _c.get("/api/queue").json()
    if _body.get("running") is not True:
        _fail(f"GET /api/queue running={_body.get('running')} during a run")

    _r = _c.post("/api/queue/run")
    if _r.status_code != 409:
        _fail(f"run while a run is active: {_r.status_code} {_r.text[:120]}")
    if _drain_cmds(_m):
        _fail("the refused run still queued a command")

    _state.run = None
    _state.login_run_active = True
    _r = _c.post("/api/queue/run")
    if _r.status_code != 409:
        _fail(f"run during a login run: {_r.status_code} {_r.text[:120]}")
    _state.login_run_active = False
    _state.scan_active = True
    _r = _c.post("/api/queue/run")
    if _r.status_code != 409:
        _fail(f"run during a login scan: {_r.status_code} {_r.text[:120]}")
    _state.scan_active = False
    _drain_cmds(_m)

    _r = _c.post("/api/queue/clear")
    if _r.status_code != 200 or _r.json() != {"ok": True, "removed": 1}:
        _fail(f"POST /api/queue/clear: {_r.status_code} {_r.text[:120]}")
    if len(_st.queue) != 0:
        _fail(f"clear left {len(_st.queue)} item(s)")

    _r = _c.post("/api/queue/run")
    if _r.status_code != 400:
        _fail(f"run on an empty queue: {_r.status_code} {_r.text[:120]}")
    if _drain_cmds(_m):
        _fail("run on an empty queue still queued a command")

    # ── watch ─────────────────────────────────────────────────────────
    _r = _c.post("/api/queue/watch", json={"url": "www.facebook.com"})
    if _r.status_code != 400:
        _fail(f"watch with a url that is not http: {_r.status_code} {_r.text[:120]}")
    if _drain_cmds(_m):
        _fail("the refused watch still queued a command")
    _r = _c.post("/api/queue/watch", json={"url": _URL, "minutes": 5,
                                           "profile_names": ["P1", "", "P1"]})
    if _r.status_code != 202 or _r.json() != {"accepted": True}:
        _fail(f"POST /api/queue/watch: {_r.status_code} {_r.text[:120]}")
    _cmds = _drain_cmds(_m)
    if [c.get("type") for c in _cmds] != ["watch_url"]:
        _fail(f"watch queued {[c.get('type') for c in _cmds]}")
    elif (_cmds[0].get("url") != _URL or _cmds[0].get("minutes") != 5
            or _cmds[0].get("profile_names") != ["P1"]):
        _fail(f"watch_url cmd={_cmds[0]}")

    _r = _c.post("/api/queue/stop-watch")
    if _r.status_code != 202 or _r.json() != {"accepted": True}:
        _fail(f"POST /api/queue/stop-watch: {_r.status_code} {_r.text[:120]}")
    if [c.get("type") for c in _drain_cmds(_m)] != ["stop_watch"]:
        _fail("stop-watch did not queue stop_watch")

print("ok" if not [f for f in failures if f.startswith("queue:")]  # noqa: F821
      else "FAILED")
