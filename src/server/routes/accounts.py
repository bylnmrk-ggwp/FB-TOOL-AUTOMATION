"""The Accounts page and the dashboard's "Log in pending" button.

Each command route is one ProfilesTab / dashboard button: validate the
body, refuse what the Tk button would have greyed out (409), call the same
DriverManager helper the button called, answer 202. The outcome is never
in the response; it arrives on /ws as the worker's own result dicts.

The two exclusivity flags (login_run_active, scan_active) are checked and
set under one lock so two phones pressing the same button in the same
instant queue one run, not two. The bridge clears them when the matching
*_result comes back.
"""
import threading

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.server import data
from src.server.routes.system import push_state
from src.storage import database as db

router = APIRouter(prefix="/api")

ACCEPTED = {"accepted": True}


# ── Bodies ────────────────────────────────────────────


class UsernamesBody(BaseModel):
    usernames: list[str] = []


class ProfileNamesBody(BaseModel):
    profile_names: list[str] | None = None


class AutoSetupBody(BaseModel):
    profile_name: str
    target_friends: int = 0
    pinterest_query: str | None = None
    bio: str | None = None


class AutoSetupAllBody(BaseModel):
    target_friends: int = 0
    pinterest_query: str | None = None
    bio: str | None = None
    connect_friends: bool = True
    profile_names: list[str] | None = None


class LinkBody(BaseModel):
    username: str
    profile_name: str


class LaunchBody(BaseModel):
    profile_name: str


def _clean(names: list[str] | None) -> list[str] | None:
    """Drop blanks and repeats but keep None (= every profile) as None."""
    if names is None:
        return None
    seen: list[str] = []
    for n in names:
        n = str(n).strip()
        if n and n not in seen:
            seen.append(n)
    return seen


# ── Rows ──────────────────────────────────────────────


@router.get("/accounts")
def accounts(request: Request) -> dict:
    return {"rows": data.accounts_rows()}


# ── Login runs ────────────────────────────────────────


def _start_login_run(request: Request, usernames: list[str]) -> dict:
    st = request.app.state
    with st.cmd_lock:
        if st.appstate.login_run_active:
            raise HTTPException(status_code=409, detail={"error": "a login run is active"})
        if not usernames:
            raise HTTPException(status_code=400, detail={"error": "no usernames given"})
        st.appstate.login_run_active = True
        st.manager.login_accounts(usernames)
    push_state(request)
    return ACCEPTED


@router.post("/accounts/login", status_code=202)
def login_selected(body: UsernamesBody, request: Request) -> dict:
    return _start_login_run(request, _clean(body.usernames) or [])


@router.post("/accounts/login-pending", status_code=202)
def login_pending(request: Request) -> dict:
    st = request.app.state
    # The 409 outranks the 400: with a run on, "none pending" would be a
    # lie about the roster rather than a fact about the button.
    if st.appstate.login_run_active:
        raise HTTPException(status_code=409, detail={"error": "a login run is active"})
    usernames = data.pending_usernames()
    if not usernames:
        raise HTTPException(status_code=400,
                            detail={"error": "no pending accounts with a Brave profile"})
    return _start_login_run(request, usernames)


@router.post("/accounts/check-login", status_code=202)
def check_login(body: ProfileNamesBody, request: Request) -> dict:
    st = request.app.state
    with st.cmd_lock:
        if st.appstate.scan_active:
            raise HTTPException(status_code=409, detail={"error": "a login check is running"})
        st.appstate.scan_active = True
        st.manager.check_login_status(_clean(body.profile_names))
    push_state(request)
    return ACCEPTED


# ── Profile setup ─────────────────────────────────────


@router.post("/accounts/auto-setup", status_code=202)
def auto_setup(body: AutoSetupBody, request: Request) -> dict:
    name = body.profile_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"error": "profile_name is required"})
    request.app.state.manager.auto_setup_profile(
        name, target_friends=body.target_friends,
        pinterest_query=body.pinterest_query, bio=body.bio)
    return ACCEPTED


@router.post("/accounts/auto-setup-all", status_code=202)
def auto_setup_all(body: AutoSetupAllBody, request: Request) -> dict:
    request.app.state.manager.auto_setup_all_profiles(
        target_friends=body.target_friends, pinterest_query=body.pinterest_query,
        bio=body.bio, connect_friends=body.connect_friends,
        profile_names=_clean(body.profile_names))
    return ACCEPTED


@router.post("/accounts/accept-pending", status_code=202)
def accept_pending(body: ProfileNamesBody, request: Request) -> dict:
    request.app.state.manager.accept_all_pending_requests(
        profile_names=_clean(body.profile_names))
    return ACCEPTED


@router.post("/profiles/launch", status_code=202)
def launch(body: LaunchBody, request: Request) -> dict:
    """Opens a visible Brave window on the PC - the page says so before
    the tap, since the operator may be nowhere near it."""
    name = body.profile_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail={"error": "profile_name is required"})
    request.app.state.manager.start_profile(name)
    return ACCEPTED


# ── Link an account to a Brave profile ────────────────


@router.post("/accounts/link")
def link(body: LinkBody, request: Request) -> dict:
    username, profile = body.username.strip(), body.profile_name.strip()
    if not username or not profile:
        raise HTTPException(status_code=400,
                            detail={"error": "username and profile_name are required"})
    if not db.link_account(username, profile):
        raise HTTPException(status_code=404, detail={"error": "no such account"})
    request.app.state.bridge.broadcast({"type": "accounts_changed"})
    return {"ok": True}


@router.delete("/accounts/link/{username}")
def unlink(username: str, request: Request) -> dict:
    if not db.link_account(username, ""):
        raise HTTPException(status_code=404, detail={"error": "no such account"})
    request.app.state.bridge.broadcast({"type": "accounts_changed"})
    return {"ok": True}


# ── Provisioning Brave profiles ───────────────────────


def _provision_run(log) -> int:
    """Run scripts/provision_profiles.py in-process, its printed output going
    to `log` line by line. Imported lazily: the script lives outside the
    package and pulls in Brave's Local State handling, which a proof that
    never provisions should not load."""
    import contextlib
    import io
    import sys as _sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    if str(root / "scripts") not in _sys.path:
        _sys.path.insert(0, str(root / "scripts"))
    import provision_profiles

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = provision_profiles.main([])
    for line in buf.getvalue().splitlines():
        if line.strip():
            log(f"  {line}")
    return code


def _brave_running() -> bool:
    """Brave rewrites Local State when it exits and would discard whatever we
    add, so the script refuses while it is open and so does this route."""
    from src.core.driver_manager import DriverManager
    return DriverManager._brave_running()


# Swapped out by proofs so the real script never creates Brave profiles.
_provision_deps = {"brave_running": _brave_running, "run": _provision_run}


@router.post("/accounts/provision", status_code=202)
def provision(request: Request) -> dict:
    """Create and link a Brave profile for every roster row that has none.

    Long and filesystem-bound, so it answers 202 and runs on its own thread;
    progress arrives as log lines over /ws exactly like a worker run.
    """
    st = request.app.state
    deps = _provision_deps
    with st.cmd_lock:
        if st.appstate.provision_active:
            raise HTTPException(status_code=409,
                                detail={"error": "profiles are already being created"})
        if (st.appstate.run is not None or st.appstate.login_run_active
                or st.appstate.scan_active):
            raise HTTPException(status_code=409, detail={"error": "a run is active"})
        if deps["brave_running"]():
            raise HTTPException(
                status_code=409,
                detail={"error": "Brave is open - close every Brave window first, "
                                 "or the new profiles are discarded when it exits"})
        st.appstate.provision_active = True

    logring = st.logring

    def log(message: str) -> None:
        entry = logring.write(message)
        if isinstance(entry, dict):
            st.bridge.broadcast({"type": "log", **entry})

    def worker() -> None:
        try:
            log("Creating Brave profiles for unlinked roster rows...")
            code = deps["run"](log)
            log(f"Profile provisioning finished (exit {code})")
        except Exception as e:  # noqa: BLE001 - reported, never raised into the thread
            log(f"\u2717 Profile provisioning failed: {type(e).__name__}: {e}")
        finally:
            st.appstate.provision_active = False
            st.bridge.broadcast({"type": "accounts_changed"})
            st.bridge.broadcast(_state_event_safe(request))

    threading.Thread(target=worker, name="provision", daemon=True).start()
    push_state(request)
    return ACCEPTED


def _state_event_safe(request: Request) -> dict:
    """push_state() off the request thread, without needing the Request to
    still be live: the same payload, built from app.state."""
    from src.server.routes.system import _state_event
    return _state_event(request)
