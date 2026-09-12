"""Operator login for the web app: one password, one signed cookie.

The server sits behind Caddy and an frp tunnel, so this module is the only
thing between the internet and the PC's Brave profiles. There is exactly one
operator, hence no user table: a bcrypt hash of the one password lives in
~/.autoshare/config.json under `web_password_hash` (written by
scripts/set_web_password.py) next to the other settings. A login mints an
itsdangerous-signed timestamp; the cookie carries no session id and the
server keeps no session table, so a restart does not log the phone out and
there is nothing to garbage-collect. The signing secret is generated once
and saved under `web_session_secret`.

Failed logins are rate-limited per client IP in memory (5 per 15 minutes)
because a phone-typeable password is short enough to guess at, and the
Origin header is checked on state-changing requests because the cookie is
SameSite=Lax, which still lets a top-level cross-site form POST through.

`require_session` and `check_origin` raise fastapi.HTTPException with a
dict `detail` ({"error": ...}) so app.py can hand `detail` straight to a
JSONResponse and the client always sees {"error": "..."}.
"""
import secrets
import threading
import time

import bcrypt
from fastapi import HTTPException, Request
from itsdangerous import BadData, URLSafeTimedSerializer

from src.storage import config_manager as cfg

COOKIE = "fbtool_session"
SESSION_MAX_AGE = 30 * 24 * 3600
HASH_KEY, SECRET_KEY = "web_password_hash", "web_session_secret"  # config_manager keys

# bcrypt 5 raises ValueError past 72 bytes instead of silently truncating as
# older releases did; the script refuses longer passwords up front and
# verify_password treats one as a plain mismatch so a login attempt can
# never turn into a 500.
BCRYPT_MAX_BYTES = 72
MIN_PASSWORD_CHARS = 8

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


# -- password ----------------------------------------------------------------


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(pw: str, hashed: str | None) -> bool:
    if not pw or not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("ascii"))
    except ValueError:
        # Over 72 bytes, or a config value that is not a bcrypt hash at all.
        return False


def stored_hash() -> str | None:
    return cfg.get_setting(HASH_KEY) or None


def store_password(pw: str) -> None:
    cfg.save_setting(HASH_KEY, hash_password(pw))


def session_secret() -> str:
    """The cookie-signing secret, minted on first use and kept in config so
    tokens survive a server restart."""
    secret = cfg.get_setting(SECRET_KEY)
    if not secret:
        secret = secrets.token_urlsafe(32)
        cfg.save_setting(SECRET_KEY, secret)
    return secret


# -- sessions ----------------------------------------------------------------


class Sessions:
    """Stateless session tokens: a signed timestamp, checked against max_age."""

    def __init__(self, secret: str, max_age: int = SESSION_MAX_AGE):
        self._serializer = URLSafeTimedSerializer(secret)
        self.max_age = max_age

    def issue(self) -> str:
        # "v" lets a future change invalidate every outstanding cookie at once
        # by bumping the number, without rotating the secret.
        return self._serializer.dumps({"v": 1, "iat": time.time()})

    def check(self, token: str | None) -> bool:
        if not token:
            return False
        try:
            payload = self._serializer.loads(token, max_age=self.max_age)
        except BadData:  # BadSignature, SignatureExpired, BadPayload
            return False
        return isinstance(payload, dict) and payload.get("v") == 1


# -- login rate limit --------------------------------------------------------


class RateLimiter:
    """Per-key failure counter over a sliding window, in memory only."""

    def __init__(self, limit: int = 5, window_s: int = 900):
        self.limit = limit
        self.window_s = window_s
        self._failures: dict[str, list[float]] = {}
        # Sync routes run on uvicorn's threadpool, so two logins can race.
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        stamps = [t for t in self._failures.get(key, ()) if now - t < self.window_s]
        if stamps:
            self._failures[key] = stamps
        else:
            self._failures.pop(key, None)
        return stamps

    def allowed(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.monotonic())) < self.limit

    def failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._failures[key] = self._recent(key, now) + [now]

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# -- request guards ----------------------------------------------------------


def client_ip(request: Request) -> str:
    """The first X-Forwarded-For hop (Caddy sets it) else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    client = getattr(request, "client", None)
    return client.host if client and client.host else ""


def require_session(request: Request) -> None:
    """FastAPI dependency: 401 unless the cookie carries a live session token.

    Reads the Sessions instance from app.state so proofs can hand in a
    SimpleNamespace instead of building an app.
    """
    if not request.app.state.sessions.check(request.cookies.get(COOKIE)):
        raise HTTPException(status_code=401, detail={"error": "unauthorized"})


def check_origin(request: Request, allowed: set[str]) -> None:
    """CSRF guard for POST/PUT/PATCH/DELETE: the Origin header must equal
    "<scheme>://<Host header>" or be in `allowed`, else 403.

    A request with no Origin and no Sec-Fetch-Site comes from something that
    is not a browser (curl, the frpc health check) and passes; a browser
    always sends Sec-Fetch-Site, so no Origin there means it withheld it.
    """
    if request.method.upper() in _SAFE_METHODS:
        return
    headers = request.headers
    origin = headers.get("origin")
    if origin is None:
        if headers.get("sec-fetch-site") is None:
            return
        raise HTTPException(status_code=403, detail={"error": "origin missing"})
    # Caddy terminates TLS, so uvicorn sees "http" while the phone's Origin
    # says "https"; X-Forwarded-Proto is the scheme the browser used.
    scheme = (headers.get("x-forwarded-proto", "").split(",")[0].strip()
              or request.url.scheme)
    expected = f"{scheme}://{headers.get('host', '')}"
    if origin == expected or origin in allowed:
        return
    raise HTTPException(status_code=403, detail={"error": "origin not allowed"})
