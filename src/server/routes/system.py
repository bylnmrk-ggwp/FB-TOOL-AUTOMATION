"""Session, state, log, prompt answers and the stop button: the routes that
are about the server itself rather than one page.

Every handler is a plain `def`: FastAPI runs those on a threadpool, so a
DB read or a cmd_queue.put never stalls the event loop the WebSocket
fan-out lives on. Nothing here waits on the worker - a command is queued
and the client hears the outcome on /ws.

The session guard and the Origin check are applied by the middleware in
app.py, not per route, so a route added here is guarded by default; only
/api/health and /api/login are public, by name, in that middleware.
"""
import os

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.server import auth, data
from src.server.logbuf import LogRing

router = APIRouter(prefix="/api")


def _state_event(request: Request) -> dict:
    """The {"type": "state"} event as the bridge builds it; routes that
    flip a flag broadcast it so every other device sees the button go
    grey at once."""
    st = request.app.state
    return {"type": "state", **st.appstate.to_dict(), "counts": data.counts()}


def push_state(request: Request) -> None:
    request.app.state.bridge.broadcast(_state_event(request))


# ── Session ───────────────────────────────────────────


class LoginBody(BaseModel):
    password: str = ""


@router.post("/login", status_code=204)
def login(body: LoginBody, request: Request) -> Response:
    st = request.app.state
    ip = auth.client_ip(request)
    # Checked before the password so a locked-out address learns nothing
    # from the timing of a bcrypt compare it is not allowed to make.
    if not st.limiter.allowed(ip):
        raise HTTPException(status_code=429,
                            detail={"error": "too many attempts, try again later"})
    if not auth.verify_password(body.password, auth.stored_hash()):
        st.limiter.failure(ip)
        raise HTTPException(status_code=401, detail={"error": "wrong password"})
    st.limiter.reset(ip)
    response = Response(status_code=204)
    # Secure is dropped only under --dev: `vite` serves http://localhost
    # and a browser will not store a Secure cookie from there.
    response.set_cookie(auth.COOKIE, st.sessions.issue(), max_age=auth.SESSION_MAX_AGE,
                        path="/", httponly=True, samesite="lax", secure=not st.dev)
    return response


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    st = request.app.state
    response = Response(status_code=204)
    # Same attributes as the cookie that was set: a browser only replaces
    # a cookie whose name, path and flags match.
    response.delete_cookie(auth.COOKIE, path="/", httponly=True, samesite="lax",
                           secure=not st.dev)
    return response


# ── Read-only ─────────────────────────────────────────


@router.get("/health")
def health(request: Request) -> dict:
    """Public: frpc's health check and the runbook's curl hit this."""
    return {"ok": True, "version": request.app.state.appstate.version}


@router.get("/state")
def state(request: Request) -> dict:
    st = request.app.state
    return {**st.appstate.to_dict(), "counts": data.counts()}


@router.get("/log")
def log(request: Request,
        tail: int = Query(500, ge=0, le=LogRing.MAX_LINES)) -> dict:
    return {"lines": request.app.state.logring.tail(tail)}


@router.get("/images/{image_id}")
def image(image_id: str, request: Request) -> FileResponse:
    """A file from the open prompt's allow-list only: the id is the whole
    address, so no path ever crosses the wire in either direction."""
    path = request.app.state.bridge.image_path(image_id)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail={"error": "no such image"})
    return FileResponse(path)


# ── Commands ──────────────────────────────────────────


class InputBody(BaseModel):
    profile_pic: str | None = None
    cancel: bool = False


@router.post("/input")
def answer_input(body: InputBody, request: Request) -> dict:
    """The first device to answer closes the prompt; the second one gets
    409 rather than a silent no-op, so its operator knows it was handled."""
    if not request.app.state.bridge.answer_input(body.model_dump()):
        raise HTTPException(status_code=409, detail={"error": "no prompt is open"})
    return {"ok": True}


@router.post("/stop", status_code=202)
def stop(request: Request) -> dict:
    """What the Tk Stop button did: close the watch windows, then let the
    worker close the browser it holds."""
    manager = request.app.state.manager
    manager.stop_watch()
    manager.cleanup()
    return {"accepted": True}
