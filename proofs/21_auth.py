"""Proof: src/server/auth.py - password hashing, session tokens, the login
rate limiter and the two FastAPI guards (require_session, check_origin).

Runs under verify.py with globals `failures`, `step` and `ROOT`. Everything
here is pure: the real config.json is never written (stored_hash /
store_password / session_secret are exercised by proofs/23_server.py, which
saves and restores the operator's hash). Requests are faked with
types.SimpleNamespace so no app is built and no socket is opened.
"""
import subprocess
import sys
import time
import types

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("auth")  # noqa: F821
from fastapi import HTTPException  # noqa: E402
from starlette.datastructures import Headers  # noqa: E402

from src.server import auth  # noqa: E402

_before = len(failures)  # noqa: F821


def _fail(msg: str) -> None:
    failures.append(f"auth: {msg}")  # noqa: F821


def _raises(fn, status: int) -> bool:
    """True when fn() raises HTTPException with exactly `status`."""
    try:
        fn()
    except HTTPException as e:
        return e.status_code == status
    return False


# -- constants the routes and the cookie depend on ------------------------
if auth.COOKIE != "fbtool_session":
    _fail(f"COOKIE is {auth.COOKIE!r}")
if auth.SESSION_MAX_AGE != 30 * 24 * 3600:
    _fail(f"SESSION_MAX_AGE is {auth.SESSION_MAX_AGE}")
if (auth.HASH_KEY, auth.SECRET_KEY) != ("web_password_hash", "web_session_secret"):
    _fail(f"config keys are {(auth.HASH_KEY, auth.SECRET_KEY)!r}")

# -- password hash ---------------------------------------------------------
_h = auth.hash_password("verify-pass-123")
if not isinstance(_h, str) or not _h.startswith("$2"):
    _fail(f"hash_password returned {type(_h).__name__} {_h[:4]!r}")
if not auth.verify_password("verify-pass-123", _h):
    _fail("verify_password rejected the right password")
if auth.verify_password("verify-pass-124", _h):
    _fail("verify_password accepted the wrong password")
if auth.verify_password("verify-pass-123", "") or auth.verify_password("x", None):
    _fail("verify_password accepted an empty/None hash")
# bcrypt 5 raises on >72 bytes; a long guess must be a plain "no", not a 500.
if auth.verify_password("x" * 100, _h):
    _fail("verify_password accepted a 100-char password")

# -- session tokens --------------------------------------------------------
_tok = auth.Sessions("s").issue()
if not isinstance(_tok, str) or not _tok:
    _fail("issue() did not return a non-empty str")
if not auth.Sessions("s").check(_tok):
    _fail("same-secret token rejected")
if auth.Sessions("other").check(_tok):
    _fail("wrong-secret token accepted")
if auth.Sessions("s").check(None):
    _fail("check(None) returned True")
if auth.Sessions("s").check("not.a.token"):
    _fail("garbage token accepted")
_short = auth.Sessions("s", max_age=0)
_stale = _short.issue()
time.sleep(1.1)
if _short.check(_stale):
    _fail("expired token accepted")

# -- rate limiter ----------------------------------------------------------
_rl = auth.RateLimiter(limit=2, window_s=60)
_seq = []
_seq.append(_rl.allowed("ip1"))
_rl.failure("ip1")
_seq.append(_rl.allowed("ip1"))
_rl.failure("ip1")
_seq.append(_rl.allowed("ip1"))
_other = _rl.allowed("ip2")
_rl.reset("ip1")
_seq.append(_rl.allowed("ip1"))
if _seq != [True, True, False, True]:
    _fail(f"RateLimiter sequence {_seq}")
if not _other:
    _fail("RateLimiter mixed up two keys")


# -- fake requests ---------------------------------------------------------
def _req(method="GET", headers=None, scheme="http", cookies=None,
         sessions=None, client_host="127.0.0.1"):
    return types.SimpleNamespace(
        method=method,
        headers=Headers(headers or {}),
        url=types.SimpleNamespace(scheme=scheme),
        cookies=cookies or {},
        client=types.SimpleNamespace(host=client_host) if client_host else None,
        app=types.SimpleNamespace(state=types.SimpleNamespace(sessions=sessions)),
    )


# check_origin: the CSRF guard.
try:
    auth.check_origin(_req("GET", {"origin": "https://evil.example",
                                   "host": "localhost:8000"}), set())
except HTTPException as e:
    _fail(f"GET raised {e.status_code}")
try:
    auth.check_origin(_req("POST", {"origin": "http://localhost:8000",
                                    "host": "localhost:8000"}), set())
except HTTPException as e:
    _fail(f"same-origin POST raised {e.status_code}")
if not _raises(lambda: auth.check_origin(
        _req("POST", {"origin": "https://evil.example",
                      "host": "localhost:8000"}), set()), 403):
    _fail("cross-site POST did not raise 403")
try:
    auth.check_origin(_req("POST", {"host": "localhost:8000"}), set())
except HTTPException as e:
    _fail(f"non-browser POST without Origin raised {e.status_code}")
if not _raises(lambda: auth.check_origin(
        _req("POST", {"host": "localhost:8000", "sec-fetch-site": "cross-site"}),
        set()), 403):
    _fail("browser POST without Origin did not raise 403")
try:
    auth.check_origin(_req("POST", {"origin": "https://phone.example",
                                    "host": "localhost:8000"}),
                      {"https://phone.example"})
except HTTPException as e:
    _fail(f"allow-listed origin raised {e.status_code}")

# require_session: the cookie guard.
_sess = auth.Sessions("s")
if not _raises(lambda: auth.require_session(_req(sessions=_sess)), 401):
    _fail("no cookie did not raise 401")
if not _raises(lambda: auth.require_session(
        _req(sessions=_sess, cookies={auth.COOKIE: "junk"})), 401):
    _fail("bad cookie did not raise 401")
try:
    auth.require_session(_req(sessions=_sess, cookies={auth.COOKIE: _sess.issue()}))
except HTTPException as e:
    _fail(f"valid cookie raised {e.status_code}")

# client_ip: first hop of X-Forwarded-For (Caddy), else the socket peer.
if auth.client_ip(_req(headers={"x-forwarded-for": "1.2.3.4, 10.0.0.1"})) != "1.2.3.4":
    _fail("client_ip ignored X-Forwarded-For")
if auth.client_ip(_req(client_host="9.9.9.9")) != "9.9.9.9":
    _fail("client_ip ignored request.client.host")
if auth.client_ip(_req(client_host=None)) != "":
    _fail("client_ip raised or returned non-str with no client")

# -- scripts/set_web_password.py --check: read-only, exits 0 or 1 -----------
_p = subprocess.run([sys.executable, str(ROOT / "scripts" / "set_web_password.py"),  # noqa: F821
                     "--check"], capture_output=True, text=True, timeout=60)
if _p.returncode not in (0, 1):
    _fail(f"set_web_password.py --check exited {_p.returncode}: {_p.stderr[-300:]}")
elif "web_password_hash" not in _p.stdout:
    _fail(f"set_web_password.py --check output: {_p.stdout!r}")

print("ok" if len(failures) == _before else "FAILED")  # noqa: F821
