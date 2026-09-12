"""create_app(): the FastAPI app that stands in for MainWindow.

The window owned the manager, polled its results and wired buttons to its
helpers; here the routes are the buttons, the EventBridge is the poll and
/ws is the widget tree every phone repaints from. create_app builds none
of the threads: server.py starts the manager, the watcher and the bridge
after the app exists, and a proof builds the app with none of them
running.

What lives here rather than in a route module: the session/Origin
middleware (so a new route is guarded unless named public), the error
shape ({"error": ...} for every refusal, whatever raised it), the
WebSocket, and the static SPA. The bridge learns the event loop in the
lifespan handler because that is the loop the WebSocket handlers run on -
under uvicorn the server's loop, under TestClient the portal's.
"""
import asyncio
import json
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.server import auth, data
from src.server.events import EventBridge
from src.server.logbuf import LogRing
from src.server.routes import accounts as accounts_routes
from src.server.routes import system as system_routes
from src.server.state import AppState
from src.storage import config_manager as cfg

ROOT = Path(__file__).resolve().parents[2]

# The DriverManager helpers phase 1 reaches through a route or the bridge.
# proofs/24_parity.py diffs this against what MainWindow._connect_callbacks
# wires, so a helper the desktop reaches and the phone cannot is visible.
USES: tuple[str, ...] = (
    "login_accounts",
    "check_login_status",
    "auto_setup_profile",
    "auto_setup_all_profiles",
    "accept_all_pending_requests",
    "start_profile",
    "stop_watch",
    "cleanup",
    "send_user_response",
)

# /api paths that need no session. Everything else under /api, and /ws, does.
PUBLIC_PATHS = frozenset({"/api/health", "/api/login"})

# Where `vite` and the server itself answer during development; --dev adds
# these so the Vite proxy's Origin passes the CSRF check.
DEV_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173",
               "http://localhost:8000", "http://127.0.0.1:8000")

# config_manager key: the public host the phone reaches the server on
# (Caddy's), so its Origin is accepted even when Host is rewritten.
PUBLIC_HOST_KEY = "web_public_host"

# What GET / says before BUILD_WEB.bat has run. One line: it is the whole
# page, and a page is what a browser expects from GET /.
NOT_BUILT_HTML = ("<!doctype html><title>AutoShare</title>"
                  "<p>web/dist not built - run BUILD_WEB.bat</p>")

WS_CLOSE_UNAUTHORIZED = 4401


def _allowed_origins(dev: bool) -> set[str]:
    allowed: set[str] = set(DEV_ORIGINS) if dev else set()
    public = str(cfg.get_setting(PUBLIC_HOST_KEY, "") or "").strip().rstrip("/")
    if public:
        allowed.add(public if "://" in public else f"https://{public}")
    return allowed


def _error_response(exc: HTTPException) -> JSONResponse:
    """auth.py raises with a dict detail; anything else that raises
    HTTPException gets the same {"error": ...} shape so the frontend has
    one field to read."""
    detail = exc.detail
    body = detail if isinstance(detail, dict) else {"error": str(detail)}
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


def create_app(manager, watcher=None, *, state: AppState | None = None,
               logring: LogRing | None = None, bridge: EventBridge | None = None,
               dev: bool = False, web_dist: Path = ROOT / "web" / "dist") -> FastAPI:
    state = state if state is not None else AppState()
    logring = logring if logring is not None else LogRing()
    if bridge is None:
        # Never started here: routes need a bridge to answer prompts and
        # broadcast through, and whoever starts the manager starts it.
        bridge = EventBridge(manager, watcher, state, logring)
    web_dist = Path(web_dist)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bridge.attach_loop(asyncio.get_running_loop())
        try:
            yield
        finally:
            bridge.attach_loop(None)

    app = FastAPI(title="MCARSPH AutoShare", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)
    st = app.state
    st.manager = manager
    st.watcher = watcher
    st.appstate = state
    st.logring = logring
    st.bridge = bridge
    st.sessions = auth.Sessions(auth.session_secret())
    st.limiter = auth.RateLimiter()
    st.allowed_origins = _allowed_origins(dev)
    st.dev = dev
    st.web_dist = web_dist
    # Routes that check-then-set an exclusivity flag hold this, so two
    # devices cannot both pass the check (sync routes run on a threadpool).
    st.cmd_lock = threading.Lock()

    # ── Errors: one shape ─────────────────────────────────

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, exc: HTTPException):
        return _error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def _bad_body(request: Request, exc: RequestValidationError):
        # 400, not FastAPI's 422: the frontend treats every 4xx from a
        # command as "refused, show the error", and one code is simpler.
        return JSONResponse({"error": "invalid request",
                             "details": jsonable_encoder(exc.errors())},
                            status_code=400)

    # ── Guards ────────────────────────────────────────────

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        path = request.url.path
        if path.startswith("/api/"):
            try:
                # Origin first: a cross-site POST is refused whether or not
                # it carries the cookie, and it always does.
                auth.check_origin(request, st.allowed_origins)
                if path not in PUBLIC_PATHS:
                    auth.require_session(request)
            except HTTPException as exc:
                # Raised inside middleware, so the exception handlers above
                # never see it; answered in their shape by hand.
                return _error_response(exc)
        return await call_next(request)

    # ── Routes ────────────────────────────────────────────

    app.include_router(system_routes.router)
    app.include_router(accounts_routes.router)

    # ── WebSocket: server -> client only ──────────────────

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        if not st.sessions.check(websocket.cookies.get(auth.COOKIE)):
            await websocket.close(code=WS_CLOSE_UNAUTHORIZED)
            return
        await websocket.accept()
        # Subscribed before the first send so nothing broadcast between
        # the snapshot and the loop below can be missed.
        q = bridge.subscribe()

        async def drain_client() -> None:
            """Client text is ignored; reading it is the only way to learn
            that the socket closed while the bridge was quiet."""
            try:
                while True:
                    await websocket.receive_text()
            except (WebSocketDisconnect, RuntimeError):
                pass
            tg.cancel_scope.cancel()

        async def push() -> None:
            try:
                while True:
                    event = await q.get()
                    # default=str: a worker result with a stray Path or
                    # datetime must not close every phone's socket.
                    await websocket.send_text(json.dumps(event, default=str))
            except (WebSocketDisconnect, RuntimeError):
                # The peer went away between two events; a child that
                # raised would leave the group as an ExceptionGroup, so
                # the closed socket is ended here, quietly.
                pass
            tg.cancel_scope.cancel()

        try:
            await websocket.send_text(json.dumps(
                {"type": "state", **state.to_dict(), "counts": data.counts()},
                default=str))
            # An anyio task group, not bare asyncio tasks: Starlette (and
            # its TestClient) cancel a handler through anyio's scope tree,
            # and children outside it are cancelled a step too late.
            async with anyio.create_task_group() as tg:
                tg.start_soon(drain_client)
                tg.start_soon(push)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            bridge.unsubscribe(q)

    # ── Static SPA ────────────────────────────────────────

    if (web_dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        """Any path that is not the API is the app: a file from web/dist
        when one matches, else index.html so a deep link or a PWA reload on
        /accounts still opens the app and the router takes it from there."""
        if path.startswith("api/") or path == "api" or path == "ws":
            raise HTTPException(status_code=404, detail={"error": "not found"})
        index = web_dist / "index.html"
        if not index.is_file():
            return HTMLResponse(NOT_BUILT_HTML)
        if path:
            root = web_dist.resolve()
            candidate = (web_dist / path).resolve()
            # Inside web/dist only: ".." in a URL must never reach the repo.
            if candidate.is_relative_to(root) and candidate.is_file():
                return FileResponse(str(candidate))
        return FileResponse(str(index))

    return app
