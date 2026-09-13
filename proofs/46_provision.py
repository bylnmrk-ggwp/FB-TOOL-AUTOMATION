"""POST /api/accounts/provision: create a Brave profile for every roster row
that has none, from the phone.

Rows 222-263 of the sheet sat unloggable because no Brave profile existed to
log them into, and creating one was a PC-only script. This route wraps that
script, refusing exactly where the script refuses: Brave open (it rewrites
Local State on exit and would discard the new profiles) or another run in
flight.
"""
import sys
import threading
import time
import types

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("provision route")  # noqa: F821

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.core.driver_manager import DriverManager  # noqa: E402
from src.server.routes import accounts as accounts_routes  # noqa: E402
from src.server.state import AppState, RunState  # noqa: E402
from src.core import browser_choice as bc  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402

# This route provisions Brave profiles, and the "close Brave first" guard is
# Brave's alone - Chromium writes no Local State and shares no directory. Pin
# the browser so the proof tests the Brave path whatever the PC is set to.
_saved_browser = cfg.get_setting(bc.SETTING_KEY, None)
cfg.save_setting(bc.SETTING_KEY, bc.BRAVE)


def _restore_browser():
    """Put the PC's browser back even when a check below raises: leaving it on
    Brave silently switches every later run away from Chromium."""
    if _saved_browser is None:
        conf = cfg._load_config()
        conf.pop(bc.SETTING_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.SETTING_KEY, _saved_browser)


import atexit  # noqa: E402
atexit.register(_restore_browser)


class _Bridge:
    """push_state needs something that broadcasts; record what it saw."""

    def __init__(self):
        self.events = []

    def broadcast(self, event):
        self.events.append(event)


def _client(brave_running=False, calls=None):
    app = FastAPI()
    app.include_router(accounts_routes.router)
    app.state.manager = DriverManager()
    app.state.appstate = AppState()
    app.state.bridge = _Bridge()
    app.state.cmd_lock = threading.RLock()
    app.state.logring = types.SimpleNamespace(write=lambda m: {"stamp": "00:00:00",
                                                              "text": m, "level": "info"})
    # Never run the real script in a proof: it would create directories under
    # Brave's User Data and rewrite Local State.
    accounts_routes._provision_deps = {
        "brave_running": lambda: brave_running,
        "run": lambda log: (calls.append("ran") if calls is not None else None) or 0,
    }
    return app, TestClient(app)


# Refused while Brave is open - the script's own precondition.
_app, _c = _client(brave_running=True)
_r = _c.post("/api/accounts/provision")
if _r.status_code != 409:
    failures.append(f"provision with Brave open should be 409, got {_r.status_code}")  # noqa: F821

# Refused while another run drives the worker.
_app, _c = _client()
_app.state.appstate.run = RunState(kind="batch", total=3)
_r = _c.post("/api/accounts/provision")
if _r.status_code != 409:
    failures.append(f"provision during a run should be 409, got {_r.status_code}")  # noqa: F821

# Accepted otherwise, and the script actually runs (off the request thread).
_calls = []
_app, _c = _client(calls=_calls)
_r = _c.post("/api/accounts/provision")
if _r.status_code != 202:
    failures.append(f"provision should answer 202, got {_r.status_code} {_r.text[:120]}")  # noqa: F821
for _ in range(40):
    if _calls:
        break
    time.sleep(0.05)
if not _calls:
    failures.append("provision accepted but never ran the provisioning script")  # noqa: F821

# The flag is published so other devices grey the button, and cleared after.
for _ in range(40):
    if _app.state.appstate.provision_active is False and _calls:
        break
    time.sleep(0.05)
if _app.state.appstate.provision_active:
    failures.append("provision_active stuck true after the run finished")  # noqa: F821
if not any(e.get("type") == "state" for e in _app.state.bridge.events):
    failures.append("provision never pushed a state event")  # noqa: F821

# A second press while one is running is refused rather than doubled.
_app, _c = _client()
_app.state.appstate.provision_active = True
if _c.post("/api/accounts/provision").status_code != 409:
    failures.append("a second provision while one runs should be 409")  # noqa: F821

print("FAILED" if [f for f in failures if "provision" in f] else "ok")  # noqa: F821


# ── Setup and log in, chained ─────────────────────────

step("setup-and-login route")  # noqa: F821

_calls2 = []
_app, _c = _client(calls=_calls2)
_r = _c.post("/api/accounts/setup-and-login", json={"usernames": ["a@example.com"]})
if _r.status_code != 202:
    failures.append(f"setup-and-login should answer 202, got {_r.status_code} {_r.text[:120]}")  # noqa: F821
for _ in range(40):
    if _calls2:
        break
    time.sleep(0.05)
if not _calls2:
    failures.append("setup-and-login never ran the provisioning half")  # noqa: F821
# The login half must reach the worker with exactly the usernames asked for.
_queued = None
for _ in range(40):
    try:
        _queued = _app.state.manager.cmd_queue.get_nowait()
        break
    except Exception:
        time.sleep(0.05)
if not _queued or _queued.get("type") != "login_accounts" or _queued.get("usernames") != ["a@example.com"]:
    failures.append(f"setup-and-login did not queue the login: {_queued}")  # noqa: F821

# An empty selection is a 400, not a silent no-op.
_app, _c = _client()
if _c.post("/api/accounts/setup-and-login", json={"usernames": []}).status_code != 400:
    failures.append("setup-and-login with no usernames should be 400")  # noqa: F821

# Refused while Brave is open, like provisioning.
_app, _c = _client(brave_running=True)
if _c.post("/api/accounts/setup-and-login", json={"usernames": ["a@example.com"]}).status_code != 409:
    failures.append("setup-and-login with Brave open should be 409")  # noqa: F821

_restore_browser()

print("FAILED" if [f for f in failures if "setup-and-login" in f] else "ok")  # noqa: F821
