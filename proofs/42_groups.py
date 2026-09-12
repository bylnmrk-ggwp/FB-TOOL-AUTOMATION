"""Proof: src/server/routes/groups.py - the saved "My Groups" list and the fetch button.

Runs under verify.py with globals `failures`, `step` and `ROOT`. The router is
mounted on a bare FastAPI() built here, not create_app, so this proof asserts the
routes themselves and never the session/Origin middleware (proofs/23_server.py
owns that). The DriverManager is built but its thread is never started: every
accepted command is a dict left on manager.cmd_queue for this proof to read.
Two throwaway profiles share one group URL in profile_groups; both rows are
deleted in the finally block. No browser, no Google, no Brave directory.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("groups routes")  # noqa: F821
import queue as _q  # noqa: E402
import threading as _th  # noqa: E402
import warnings as _warnings  # noqa: E402

# starlette 1.6 warns that httpx (not httpx2) drives its TestClient; the
# proof works either way and the warning is not a finding.
_warnings.filterwarnings("ignore", message=".*httpx.*", module="starlette.*")
_warnings.filterwarnings("ignore", category=DeprecationWarning, module="starlette.*")

from fastapi import FastAPI as _FastAPI  # noqa: E402
from fastapi.testclient import TestClient as _TestClient  # noqa: E402

from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.server.routes import groups as _groups  # noqa: E402
from src.server.state import AppState as _AppState  # noqa: E402
from src.server.state import RunState as _RunState  # noqa: E402
from src.storage import database as _db  # noqa: E402

_P1 = "verify_groups_a@example.com"
_P2 = "verify_groups_b@example.com"
_SHARED_URL = "https://www.facebook.com/groups/verify-shared-group"
_SOLO_URL = "https://www.facebook.com/groups/verify-solo-group"
_SHARED_NAME = "Verify Shared Group"
_SOLO_NAME = "Verify Solo Group"


def _fail(msg):
    failures.append(f"groups: {msg}")  # noqa: F821


class _StubBridge:
    """Only what a route reaches for: create_app's real bridge owns a thread
    and a log ring, neither of which this proof needs."""

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


def _err(resp):
    """A refusal's payload. A bare FastAPI wraps HTTPException.detail in
    {"detail": ...}; create_app unwraps it to the flat {"error": ...} shape."""
    body = resp.json()
    return body.get("detail", body) if isinstance(body, dict) else body


def _expect_cmd(manager, resp, ctype, what):
    """One accepted fetch -> one command of the expected type on the queue."""
    cmds = _drain_cmds(manager)
    if resp.status_code != 202:
        _fail(f"{what}: status {resp.status_code} body {resp.text[:120]}")
    elif resp.json() != {"accepted": True}:
        _fail(f"{what}: body {resp.text[:120]}")
    if [c.get("type") for c in cmds] != [ctype]:
        _fail(f"{what}: queued {[c.get('type') for c in cmds]}, expected [{ctype!r}]")
    return cmds[0] if cmds else {}


_m = _DM()
_m.log = lambda _msg: None      # the driver logs non-ASCII; keep stdout clean
_state = _AppState()

try:
    _db.save_profile_groups(_P1, [{"name": _SHARED_NAME, "url": _SHARED_URL},
                                  {"name": _SOLO_NAME, "url": _SOLO_URL}])
    _db.save_profile_groups(_P2, [{"name": _SHARED_NAME, "url": _SHARED_URL}])

    _app = _FastAPI()
    _app.include_router(_groups.router)
    _st = _app.state
    _st.manager = _m
    _st.appstate = _state
    _st.bridge = _StubBridge()
    _st.cmd_lock = _th.Lock()

    def _walk(routes):
        # FastAPI 0.141 keeps an included router as one nested entry that
        # points back at the router; older releases flattened the routes.
        for r in routes:
            inner = getattr(getattr(r, "original_router", None), "routes", None)
            if inner is not None:
                yield from _walk(inner)
            elif hasattr(r, "path"):
                for m in (getattr(r, "methods", None) or set()):
                    yield (m, r.path)

    _paths = set(_walk(_app.routes))
    for _want in [("GET", "/api/groups"), ("POST", "/api/groups/fetch")]:
        if _want not in _paths:
            _fail(f"route missing: {_want}")

    with _TestClient(_app) as _c:
        # -- the saved list: one entry per group, every profile that has it --
        _r = _c.get("/api/groups")
        if _r.status_code != 200:
            _fail(f"GET /api/groups: {_r.status_code} {_r.text[:120]}")
            _rows = []
        else:
            _rows = _r.json().get("groups")
            if not isinstance(_rows, list):
                _fail(f"GET /api/groups body={_r.text[:120]}")
                _rows = []

        _mine = [g for g in _rows if g.get("url") == _SHARED_URL]
        if len(_mine) != 1:
            _fail(f"the shared group appears {len(_mine)} time(s), expected once")
        else:
            _g = _mine[0]
            if set(_g) != {"name", "url", "profiles"}:
                _fail(f"group keys={sorted(_g)}")
            if _g.get("name") != _SHARED_NAME:
                _fail(f"shared group name={_g.get('name')!r}")
            if sorted(_g.get("profiles") or []) != sorted([_P1, _P2]):
                _fail(f"shared group profiles={_g.get('profiles')}, "
                      f"expected both {_P1} and {_P2}")

        _solo = [g for g in _rows if g.get("url") == _SOLO_URL]
        if len(_solo) != 1 or (_solo and _solo[0].get("profiles") != [_P1]):
            _fail(f"solo group rows={_solo}")

        _names = [str(g.get("name", "")).casefold() for g in _rows]
        if _names != sorted(_names):
            _fail("GET /api/groups is not sorted by name")

        # -- fetch: one name is the single-profile command, the rest bulk --
        _cmd = _expect_cmd(_m, _c.post("/api/groups/fetch", json={"profile_names": None}),
                           "fetch_my_groups_bulk", "fetch all profiles")
        if _cmd.get("profile_names") is not None:
            _fail(f"fetch all: profile_names={_cmd.get('profile_names')!r}, expected None")

        _cmd = _expect_cmd(_m, _c.post("/api/groups/fetch", json={}),
                           "fetch_my_groups_bulk", "fetch with no body")
        if _cmd.get("profile_names") is not None:
            _fail(f"fetch with no body: profile_names={_cmd.get('profile_names')!r}")

        _cmd = _expect_cmd(_m, _c.post("/api/groups/fetch",
                                       json={"profile_names": ["VerifyProfile"]}),
                           "fetch_my_groups", "fetch one profile")
        if _cmd.get("profile_name") != "VerifyProfile":
            _fail(f"fetch one: profile_name={_cmd.get('profile_name')!r}")

        _cmd = _expect_cmd(_m, _c.post("/api/groups/fetch",
                                       json={"profile_names": ["A", "B", "A", " "]}),
                           "fetch_my_groups_bulk", "fetch two profiles")
        if _cmd.get("profile_names") != ["A", "B"]:
            _fail(f"fetch two: profile_names={_cmd.get('profile_names')!r}, "
                  f"expected ['A', 'B'] (blanks and repeats dropped)")

        # An empty selection is every profile, which is what the worker reads
        # an empty list as anyway; the command says so with None.
        _cmd = _expect_cmd(_m, _c.post("/api/groups/fetch", json={"profile_names": []}),
                           "fetch_my_groups_bulk", "fetch with an empty list")
        if _cmd.get("profile_names") is not None:
            _fail(f"fetch empty list: profile_names={_cmd.get('profile_names')!r}")

        # -- a run is on: refused, and nothing queued --
        _state.run = _RunState(kind="batch", current=1, total=3)
        _r = _c.post("/api/groups/fetch", json={"profile_names": None})
        if _r.status_code != 409:
            _fail(f"fetch while a run is on: {_r.status_code}, expected 409")
        elif "error" not in (_err(_r) or {}):
            _fail(f"fetch 409 body={_r.text[:120]}")
        if _drain_cmds(_m):
            _fail("the 409 fetch still queued a command")
        _state.run = None

        _cmd = _expect_cmd(_m, _c.post("/api/groups/fetch", json={"profile_names": None}),
                           "fetch_my_groups_bulk", "fetch once the run ended")
finally:
    _state.run = None
    _conn = _db._get_conn()
    _conn.execute("DELETE FROM profile_groups WHERE profile IN (?, ?)", (_P1, _P2))
    _conn.commit()

print("ok" if not [f for f in failures if f.startswith("groups:")]  # noqa: F821
      else "FAILED")
