# Web App Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A FastAPI server on the operator's PC that drives the existing `DriverManager`, plus a React PWA (Dashboard, Accounts, Log, Login) so the operator can log pending accounts in from a phone.

**Architecture:** `server.py` builds `DriverManager` + `SheetWatcher` exactly like `src/app.py`, then an `EventBridge` thread drains `manager.poll_result()` and the watcher queue, keeps one `AppState`, and broadcasts JSON events to `/ws`. Routes validate a body, call the existing manager helper, return `202`. The frontend holds one store fed by `GET /api/state` + `/ws` events. Nothing in `DriverManager`'s command/result contract changes.

**Tech Stack:** Python 3.14, FastAPI 0.141, uvicorn 0.52, itsdangerous, bcrypt 5, httpx (TestClient); Node 24, Vite 8, React 19, vite-plugin-pwa; Playwright (already installed) for the screenshot pass.

**Spec:** `docs/superpowers/specs/2026-09-12-web-app-design.md`

## Global Constraints

- `DriverManager` command and result contract is frozen: routes only call existing helpers; the bridge only reads result dicts.
- Every proof is a file `proofs/NN_name.py` run by `verify.py` with globals `failures`, `step`, `ROOT`; ASCII-only prints; never opens a browser, never contacts Google, never touches the real Brave directory. Temporary DB rows use usernames `verify_*@example.com` and are deleted at the end of the proof.
- `python verify.py` must print `ALL PROOFS PASS` at the end of every task.
- Never `git add .`/`-A`; stage explicit paths. Commit messages: `type: what and why`.
- No credentials in the repo: `tools/frp/frpc.toml` and `web_password_hash` are config/gitignored.
- Frontend colours, spacing, type and motion come from `web/src/theme.css` tokens (copied from `src/ui/theme.py`); brand red only on the logo and the active-nav bar.
- The server binds `127.0.0.1` by default; HTTPS is Caddy's job on the VPS.

---

## File map

| file | responsibility |
|---|---|
| `src/server/__init__.py` | empty |
| `src/server/data.py` | pure DB/config reads: `counts()`, `accounts_rows()`, `summary_line()` |
| `src/server/state.py` | `AppState`, `RunState` dataclasses + `to_dict()` |
| `src/server/logbuf.py` | `LogRing`: ring buffer + daily file + level rule from `LogTab.write` |
| `src/server/auth.py` | password hash, session tokens, rate limiter, FastAPI dependencies |
| `src/server/events.py` | `EventBridge` thread, `HANDLED_RTYPES`, needs_input round trip |
| `src/server/app.py` | `create_app()`; mounts routes, `/ws`, static SPA |
| `src/server/routes/__init__.py` | empty |
| `src/server/routes/system.py` | `/api/state`, `/api/log`, `/api/input`, `/api/stop`, `/api/health`, `/api/images/{id}` |
| `src/server/routes/accounts.py` | `/api/accounts*`, `/api/profiles/launch` |
| `server.py` | entry point (`--host --port --dev`) |
| `scripts/set_web_password.py` | prompts twice, stores bcrypt hash |
| `SERVER.bat`, `BUILD_WEB.bat` | launchers |
| `tools/frp/frpc.example.toml`, `docs/runbooks/vps.md` | relay config + runbook |
| `web/` | Vite + React PWA (see Task F1/F2) |
| `proofs/20_data.py … 25_web_build.py` | proofs |

---

## Task S1: `data.py`, `state.py`, `logbuf.py`

**Files:** create `src/server/__init__.py`, `src/server/data.py`, `src/server/state.py`, `src/server/logbuf.py`; proof `proofs/20_data.py`.

**Produces:**

```python
# src/server/data.py
def counts() -> dict:
    """{"total","logged_in","pending","pending_unlinked","disabled","profiles","active"}
    total=db.count_accounts()[0]; logged_in=len(db.logged_in_profiles());
    pending, pending_unlinked = db.count_pending(); disabled=db.count_disabled();
    profiles=len(cfg.list_profiles()); active = logged_in (profiles whose account is status ok)."""
def accounts_rows() -> list[dict]:
    """One row per db.list_accounts() entry plus one per cfg.list_profiles() name not linked to any account.
    Keys: sheet_no, facebook_name, username (None for an unlinked Brave profile), gmail,
    linked_profile, status, status_reason, sheet_status, logged_in (status == 'ok'),
    restricted (db.share_restriction(linked_profile) is not None)."""
def pending_usernames() -> list[str]:
    """[a['username'] for a in db.pending_accounts() if a['linked_profile']]"""
def summary_line(ok: int, failed: int, when: datetime | None = None) -> str:
    """f"{ok} ok · {failed} failed · {when:%H:%M}" (the middle dot is U+00B7)."""
```

```python
# src/server/state.py
@dataclass
class RunState:
    kind: str            # "batch" | "login" | "scan" | "auto_setup" | "join" | "share" | "fetch" | "watch"
    current: int = 0
    total: int = 0
    message: str = ""
    profile_name: str = ""
    started_at: float = 0.0   # time.time()

@dataclass
class AppState:
    run: RunState | None = None
    last_run_summary: str = ""          # restored from cfg 'last_run_summary' on construction
    pending_input: dict | None = None   # {"kind":"image_picker","profile_name":str,"images":[{"id":str,"url":str}],"needs_pic":bool,"created_at":float}
    login_run_active: bool = False
    scan_active: bool = False
    sheet_last_ok: float = 0.0
    system: dict = field(default_factory=dict)   # {"ram_used_gb","ram_total_gb","browser_mb","process_count","peak_browser_mb"}
    bridge_alive: bool = True
    version: str = "dev"
    def to_dict(self) -> dict   # run as dict or None; every field JSON-safe
```

```python
# src/server/logbuf.py
class LogRing:
    MAX_LINES = 2000
    LOG_DIR = Path.home() / ".autoshare" / "logs"      # same file LogTab writes: app-YYYYMMDD.log
    def __init__(self, maxlen: int = MAX_LINES, log_dir: Path | None = None)
    def write(self, message: str) -> dict
        """Thread-safe. Appends {"stamp":"HH:MM:SS","text":stripped,"level":"ok"|"error"|"info"},
        writes 'YYYY-MM-DD HH:MM:SS  text' to today's file, calls on_line(entry). Level rule
        copied from src/ui/log_tab.py LogTab.write: startswith U+2713 -> ok; startswith U+2717
        or 'error'/'fail' in lower -> error; else info."""
    def tail(self, n: int = 500) -> list[dict]
    def set_on_line(self, cb) -> None
    def close(self) -> None
```

**Proof `proofs/20_data.py`:** insert three `verify_*@example.com` accounts (one linked + status ok, one pending unlinked, one disabled) via `db.upsert_account`/`link_account`/`set_account_status`; assert `counts()` deltas (+3 total, +1 logged_in, +1 pending, +1 pending_unlinked, +1 disabled); assert `accounts_rows()` contains the three with the documented keys and `logged_in` True only for the ok one; assert `pending_usernames()` excludes the unlinked one; `summary_line(3,1,datetime(2026,9,12,20,11)) == "3 ok · 1 failed · 20:11"`; `AppState().to_dict()` JSON-dumps and has every key; `LogRing(log_dir=<tmp under scratch>)`: write a check-mark line, a cross line, a plain line → levels ok/error/info, `tail(2)` returns the last two, `on_line` called 3 times, file has 3 lines. Delete the rows.

---

## Task S2: `auth.py` and `scripts/set_web_password.py`

**Files:** create `src/server/auth.py`, `scripts/set_web_password.py`; proof `proofs/21_auth.py`.

**Produces:**

```python
COOKIE = "fbtool_session"
SESSION_MAX_AGE = 30 * 24 * 3600
HASH_KEY, SECRET_KEY = "web_password_hash", "web_session_secret"     # config_manager keys

def hash_password(pw: str) -> str            # bcrypt, str
def verify_password(pw: str, hashed: str) -> bool
def stored_hash() -> str | None               # cfg.get_setting(HASH_KEY) or None
def store_password(pw: str) -> None           # cfg.save_setting(HASH_KEY, hash_password(pw))
def session_secret() -> str                   # cfg SECRET_KEY, created with secrets.token_urlsafe(32) on first call

class Sessions:
    def __init__(self, secret: str, max_age: int = SESSION_MAX_AGE)
    def issue(self) -> str                     # URLSafeTimedSerializer(secret).dumps({"v": 1, "iat": time.time()})
    def check(self, token: str | None) -> bool # False on None/BadSignature/expired

class RateLimiter:
    def __init__(self, limit: int = 5, window_s: int = 900)
    def allowed(self, key: str) -> bool        # True while fewer than `limit` failures in the window
    def failure(self, key: str) -> None
    def reset(self, key: str) -> None

def client_ip(request) -> str                  # X-Forwarded-For first hop (Caddy sets it) else request.client.host
def require_session(request) -> None           # FastAPI dependency: 401 {"error":"unauthorized"} unless Sessions.check(cookie)
def check_origin(request, allowed: set[str]) -> None
    """For POST/PUT/PATCH/DELETE: Origin header (scheme://host[:port]) must equal
    f"{scheme}://{Host header}" or be in `allowed`; otherwise 403. Missing Origin on a
    non-browser client (no Sec-Fetch-Site header) is allowed."""
```

`create_app` stores `Sessions(session_secret())` and `RateLimiter()` on `app.state`; `require_session` reads them from `request.app.state`.

`scripts/set_web_password.py`: `getpass` twice, refuse mismatch or < 8 chars, `store_password`, print the config path. `--check` prints whether a hash exists and exits 0/1.

**Proof `proofs/21_auth.py`:** hash/verify round trip and mismatch; `Sessions("s").check(Sessions("s").issue())` True, wrong secret False, `check(None)` False, `Sessions("s", max_age=0)` token is rejected after `time.sleep(1.1)`; `RateLimiter(limit=2, window_s=60)`: allowed, failure, allowed, failure, not allowed, reset → allowed; `check_origin` with a fake request object (attributes `method`, `headers`, `url.scheme`): GET always passes; POST with `Origin: http://localhost:8000` and `Host: localhost:8000` passes; POST with `Origin: https://evil.example` raises `HTTPException(403)`; POST without Origin and without `Sec-Fetch-Site` passes.

---

## Task S3: `events.py`

**Files:** create `src/server/events.py`; proof `proofs/22_events.py`.

**Consumes:** `AppState`, `RunState`, `LogRing`, `data.summary_line`, `roster_sheet.apply`, `DriverManager.poll_result / get_memory_stats / send_user_response`, `SheetWatcher.events / last_ok`.

**Produces:**

```python
HANDLED_RTYPES: tuple[str, ...]   # every rtype MainWindow._handle_result handles (24) + "login_accounts_progress", "login_accounts_result"
INPUT_TIMEOUT_S = 600

class EventBridge(threading.Thread):
    def __init__(self, manager, watcher, state: AppState, logring: LogRing, poll_ms: int = 100)
    # --- fan-out (thread-safe) ---
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None
    def subscribe(self) -> asyncio.Queue          # must be called on the attached loop
    def unsubscribe(self, q: asyncio.Queue) -> None
    def broadcast(self, event: dict) -> None      # loop.call_soon_threadsafe(q.put_nowait, event) for every subscriber; also appends to self.recent (deque 200) for proofs
    # --- side effects (called on the bridge thread; proofs call them directly) ---
    def handle_result(self, result: dict) -> None
    def handle_sheet_event(self, kind: str, payload) -> None
    def refresh_system(self) -> None              # manager.get_memory_stats() -> state.system; broadcasts state on change
    def answer_input(self, answer: dict) -> bool  # {"profile_pic": id|None, "cancel": bool} -> manager.send_user_response({...paths...}); clears pending_input; False if none open
    def image_path(self, image_id: str) -> str | None
    def run(self) / def stop(self)
```

`handle_result` rules (read `src/ui/main_window.py` `_handle_result` for every branch and replicate the non-widget effects; the widget-only parts — enabling buttons — are expressed as `AppState` flags):

| rtype | AppState effect | log |
|---|---|---|
| any `*_progress` with `current`/`total` | `state.run = RunState(kind, current, total, message, profile_name)` (kind from the rtype prefix: batch→"batch", login_scan→"scan", login_accounts→"login", auto_setup_all→"auto_setup", join_group→"join", share→"share", fetch_groups→"fetch") | `message` |
| `batch_result` | `run=None`; `last_run_summary = summary_line(ok, failed)` where ok/failed are counted as `_handle_result` does; `cfg.save_setting("last_run_summary", ...)` | `_handle_result`'s summary lines |
| `login_scan_progress` / `login_scan_result` | `scan_active` True/False; `run` set/cleared | as Tk |
| `login_accounts_progress` / `login_accounts_result` | `login_run_active` True (set by the route) / False; `run` set/cleared; on result with `ok` False → broadcast `{"type":"error","text":error}` | as Tk |
| `auto_setup_result`, `auto_setup_all_result`, `join_group_bulk_result`, `share_bulk_result`, `fetch_groups_bulk_result`, `fetch_groups_result`, `logout_result`, `join_group_result`, `share_result`, `login_result` | `run=None` | as Tk |
| `auto_setup_images_preview` | `pending_input = {"kind":"image_picker","profile_name","images":[{"id": sha1(path)[:12], "url": f"/api/images/{id}"}], "needs_pic", "created_at"}`; store id→path in the allow-list; broadcast `{"type":"needs_input", ...pending_input}` | "Waiting for image choice" |
| everything else | none | `message`/`error` if present |

After every `handle_result`: broadcast the result dict verbatim (`{"type": rtype, ...}`) and, if any `AppState` field changed, `{"type":"state", **state.to_dict(), "counts": data.counts()}`.

`handle_sheet_event("rows", accounts)` → `roster_sheet.apply(accounts)` on the bridge thread, log `Roster synced from sheet: N new, M refreshed`, set `sheet_last_ok = watcher.last_ok`, broadcast `{"type":"accounts_changed"}` and state. `("error", msg)` → log `Sheet sync error: msg`.

`run()`: every `poll_ms`: drain `manager.poll_result()` (each through `handle_result`), drain `watcher.events` (if watcher), every 2 s `refresh_system()`, cancel a `pending_input` older than `INPUT_TIMEOUT_S` via `answer_input({"cancel": True})`. Wrap each iteration in try/except → `logring.write("✗ bridge error: ...")`; if the thread body itself dies, set `state.bridge_alive = False` and broadcast state.

`manager.log` wiring is the server's job (`server.py`): `manager.log = lambda m: bridge.broadcast({"type":"log", **logring.write(m)})`.

**Proof `proofs/22_events.py`:** build `DriverManager()` (not started), `AppState()`, `LogRing(log_dir=tmp)`, `EventBridge(manager, None, state, ring)`; without a loop attached `broadcast` must not raise (events still land in `bridge.recent`). Feed: `batch_progress{current:2,total:5,profile_name:"P",message:"sharing"}` → `state.run.kind=="batch"`, `current==2`; `batch_result{...}` shaped like `_do_batch` emits (read `driver_manager.py` for the real keys) → `run is None` and `last_run_summary` ends with `" ok · "`-style text; `login_accounts_result{ok:False,error:"Brave is open"}` → an `error` event in `recent`; `auto_setup_images_preview{profile_name:"P",images:[tmp1,tmp2],needs_pic:True}` → `pending_input` set with two ids and `image_path(id)` returns the path; `answer_input({"profile_pic": id1, "cancel": False})` → `manager._user_response_queue.get_nowait() == {"profile_pic": tmp1, "cancel": False}` and `pending_input is None`; `answer_input({...})` again → False; `HANDLED_RTYPES` ⊇ the 24 rtypes parsed from `main_window.py` source (regex `rtype == "(\w+)"`).

---

## Task S4: `app.py`, routes, `server.py`, launchers, requirements

**Files:** create `src/server/app.py`, `src/server/routes/__init__.py`, `src/server/routes/system.py`, `src/server/routes/accounts.py`, `server.py`, `SERVER.bat`, `BUILD_WEB.bat`; modify `requirements.txt`, `.gitignore`; proofs `proofs/23_server.py`, `proofs/24_parity.py`.

**Consumes:** S1–S3 exactly as specified.

**Produces:**

```python
# src/server/app.py
USES: tuple[str, ...] = ("login_accounts", "check_login_status", "auto_setup_profile",
    "auto_setup_all_profiles", "accept_all_pending_requests", "start_profile",
    "stop_watch", "cleanup", "send_user_response")      # manager helpers phase 1 reaches
def create_app(manager, watcher=None, *, state: AppState | None = None,
               logring: LogRing | None = None, bridge: EventBridge | None = None,
               dev: bool = False, web_dist: Path = ROOT / "web" / "dist") -> FastAPI
```

- `app.state.{manager, watcher, appstate, logring, bridge, sessions, limiter, allowed_origins}`; when `bridge` is None the app creates one (not started) so routes always have it.
- Middleware: every request path starting with `/api/` except `/api/health` and `/api/login`, and `/ws`, requires a session (401 JSON). State-changing methods pass `check_origin`. `dev=True` adds `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:8000`, `http://127.0.0.1:8000` to `allowed_origins`; config `web_public_host` (if set) is added always.
- Routes (all JSON; `202 {"accepted": true}` for commands):
  - `POST /api/login {password}` → 401 on mismatch (+`limiter.failure(ip)`), 429 when `not limiter.allowed(ip)`, 204 + `Set-Cookie: fbtool_session=<token>; HttpOnly; SameSite=Lax; Path=/; Max-Age=2592000` (+`Secure` unless `dev`). `POST /api/logout` clears it.
  - `GET /api/health` → `{"ok": true, "version": state.version}` (public).
  - `GET /api/state` → `{**state.to_dict(), "counts": data.counts()}`.
  - `GET /api/accounts` → `{"rows": data.accounts_rows()}`.
  - `POST /api/accounts/login {usernames:[...]}` → 409 `{"error":"a login run is active"}` if `state.login_run_active`; 400 if empty; else `state.login_run_active=True`, `manager.login_accounts(usernames)`.
  - `POST /api/accounts/login-pending` → usernames = `data.pending_usernames()`; 400 `{"error":"no pending accounts with a Brave profile"}` if empty; else as above.
  - `POST /api/accounts/check-login {profile_names: [...]|null}` → 409 if `state.scan_active`; `state.scan_active=True`; `manager.check_login_status(profile_names)`.
  - `POST /api/accounts/auto-setup {profile_name, target_friends=0, pinterest_query=null, bio=null}` → `manager.auto_setup_profile(...)`.
  - `POST /api/accounts/auto-setup-all {target_friends=0, pinterest_query, bio, connect_friends=true, profile_names}` → `manager.auto_setup_all_profiles(..., profile_names=...)`.
  - `POST /api/accounts/accept-pending {profile_names}` → `manager.accept_all_pending_requests(profile_names=...)`.
  - `POST /api/accounts/link {username, profile_name}` → `db.link_account`; `DELETE /api/accounts/link/{username}` → `db.link_account(username, "")`. Both `200 {"ok": true}`.
  - `POST /api/profiles/launch {profile_name}` → `manager.start_profile`.
  - `GET /api/log?tail=500` → `{"lines": logring.tail(n)}`.
  - `POST /api/input {profile_pic, cancel}` → 409 if `bridge.answer_input` returns False, else 200.
  - `POST /api/stop` → `manager.stop_watch(); manager.cleanup()`.
  - `GET /api/images/{id}` → `FileResponse(bridge.image_path(id))` or 404.
  - `WS /ws` → reject without session (close 4401); on accept: `q = bridge.subscribe()` (bridge loop attached in the app's startup event), send `{"type":"state", ...}` first, then forward queue items as JSON; `unsubscribe` on disconnect. Server → client only; client text is ignored.
  - Static: mount `web_dist/assets` at `/assets`, serve `web_dist/<file>` when it exists, else `index.html` for any non-`/api` path; when `web_dist` is missing serve a one-line HTML `web/dist not built - run BUILD_WEB.bat`.
- `server.py`: argparse `--host 127.0.0.1 --port 8000 --dev`; exits 2 with the `set_web_password.py` hint when `auth.stored_hash()` is None; builds manager, `AppState(version=<git rev-parse --short HEAD or "dev">)`, `LogRing`, `SheetWatcher`, `EventBridge`; `manager.log = ...` (S3); starts manager, watcher, bridge; `uvicorn.run(app, host, port)`; on exit stops bridge, watcher, `manager.stop()`, `logring.close()`.
- `SERVER.bat`: `start "frpc" tools\frp\frpc.exe -c tools\frp\frpc.toml` when both exist, then `python server.py`. `BUILD_WEB.bat`: `cd web && npm ci && npm run build`.
- `requirements.txt` += `fastapi>=0.115`, `uvicorn[standard]>=0.30`, `python-multipart>=0.0.9`, `itsdangerous>=2.2`, `bcrypt>=4.2`, `httpx>=0.27  # proofs: TestClient`. `.gitignore` += `web/node_modules/`, `web/dist/`, `tools/frp/frpc.toml`, `tools/frp/*.exe`, `tools/frp/*.zip`.

**Proof `proofs/23_server.py`** (FastAPI `TestClient`, manager not started; temporarily set config `web_password_hash` to `hash_password("verify-pass-123")` and restore the previous value at the end): `/api/health` 200 without cookie; `/api/state` 401; bad login 401 ×5 then 429; good login 204 with cookie; every phase-1 route with a valid body → expected status and the expected `type` on `manager.cmd_queue` (`login_accounts`, `check_login_status`, `auto_setup_profile`, `auto_setup_all`, `accept_all_pending`, `start_profile`); second `/api/accounts/login` while active → 409; `/api/accounts/link` + `DELETE` round trip on a `verify_link@example.com` row; `POST` with `Origin: https://evil.example` → 403; `/api/log?tail=2` returns ≤2; `with client.websocket_connect("/ws")` first message `type == "state"`, then `bridge.broadcast({"type":"login_accounts_progress","current":1,"total":1})` arrives within 1 s; `needs_input` round trip via `bridge.handle_result(auto_setup_images_preview)` → ws event → `POST /api/input` 200 → `manager._user_response_queue` has the answer; `GET /` returns the fallback HTML when `web_dist` does not exist (pass a temp path).

**Proof `proofs/24_parity.py`:** parse `src/ui/main_window.py` for `rtype == "..."` → set A; `events.HANDLED_RTYPES` ⊇ A; parse `main_window.py` `_connect_callbacks` for `self.manager.<name>` → set B; assert every name in B that belongs to phase 1 (`start_profile`, `auto_setup_profile`, `auto_setup_all_profiles`, `accept_all_pending_requests`, `check_login_status`) is in `app.USES`; print the phase-2 remainder as a notice, not a failure.

---

## Task F1: `web/` scaffold, shell, store, API, WS, Login, PWA, responsive

**Files:** create `web/package.json`, `web/vite.config.js`, `web/index.html`, `web/public/logo_light.png`, `web/public/logo_dark.png`, `web/public/icon-192.png`, `web/public/icon-512.png`, `web/public/apple-touch-icon.png`, `web/src/main.jsx`, `web/src/App.jsx`, `web/src/store.js`, `web/src/api.js`, `web/src/ws.js`, `web/src/theme.css`, `web/src/app.css`, `web/src/components/{Sidebar,Header,StatusBar,TabBar,Toasts,InputPrompt}.jsx`, `web/src/pages/{Login,Placeholder}.jsx`, `web/README.md`; proof `proofs/25_web_build.py`.

Seed from `mockup/react/src` (copy `theme.css`, `app.css`, `Sidebar.jsx`, `Header.jsx`, `StatusBar.jsx`, the `App.jsx` shell logic — theme dip, sidebar pin/auto-collapse, page slide) and delete the fake-data paths. Icons: generate with Pillow from `src/ui/assets/logo_light.png` centred on a white 192/512 square (a Python one-liner in the task; commit the PNGs).

**Store contract (F2 codes against this; do not rename):**

```js
// web/src/store.js
export const PAGES = [ {key:'dashboard',title:'Dashboard',glyph:'',fallback:'▣'}, {key:'accounts',...}, {key:'queue',...}, {key:'compose',...}, {key:'monitor',...}, {key:'log',...} ]
export const initialState = {
  auth: 'unknown',            // 'unknown' | 'in' | 'out'
  connected: false,           // websocket open
  server: null,               // AppState dict from GET /api/state: run, last_run_summary, pending_input, login_run_active, scan_active, sheet_last_ok, system, bridge_alive, version
  counts: null,               // {total, logged_in, pending, pending_unlinked, disabled, profiles, active}
  accounts: [],               // rows from GET /api/accounts (see data.accounts_rows keys) + client-only `live` (true/false/undefined from login_scan_progress / login_accounts_progress)
  selected: new Set(),        // usernames (or 'profile:<name>' for unlinked profiles)
  log: [],                    // {stamp, text, level}, max 2000
  toasts: [],                 // {id, level, text}
}
export function useStore(selector)          // useSyncExternalStore
export const actions = {
  bootstrap(),                              // GET /api/state (+ accounts + log tail 500) then ws.connect(); 401 -> auth 'out'
  login(password), logout(),
  refreshAccounts(), refreshState(),
  setSelected(set), toggleSelected(key), clearSelected(),
  loginPending(), loginSelected(usernames), checkLogin(profileNames|null),
  autoSetupAll(profileNames), acceptPending(profileNames), launch(profileName),
  link(username, profileName), unlink(username),
  answerInput({profile_pic, cancel}), stopAll(),
  dismissToast(id),
}
export function reduce(state, event)        // pure; exported for tests. Handles:
//  state -> server+counts; log -> append; error -> toast(error); needs_input -> server.pending_input;
//  accounts_changed -> actions.refreshAccounts() side effect scheduled by ws.js, not by reduce;
//  login_scan_progress / login_accounts_progress -> set accounts[i].live for profile_name;
//  login_scan_result / login_accounts_result -> refreshAccounts scheduled; toast on ok===false.
```

`api.js`: `get(path)`, `post(path, body)`, `del(path)` with `credentials: 'same-origin'`, JSON, throws `{status, error}`; 401 → `actions.setAuth('out')`. `ws.js`: `connect()` opens `ws(s)://<location.host>/ws`; on message → `reduce`; on close → backoff 1 s → 30 s, and on every (re)open `actions.refreshState()` + `refreshAccounts()`.

Shell: `App.jsx` renders `Login` when `auth === 'out'`, a centred spinner when `'unknown'`, else the shell. Header chip on Accounts/Queue/Compose: `N selected` or `all logged in (counts.active)`. `Toasts` bottom-right (top on phones), auto-dismiss 6 s. `InputPrompt` modal when `server.pending_input` (image grid from `images[].url`, "Use this" / "Skip"). `Placeholder` page: title + "Coming in phase 2 — use the desktop app (RUN_APP.bat) for now" for queue/compose/monitor. A red banner when `!connected` ("PC unreachable — reconnecting…") and when `server.bridge_alive === false`.

Responsive (`app.css`): `@media (max-width: 767px)`: sidebar hidden, `TabBar` fixed at the bottom with the 6 glyphs (active = brand bar on top), content padding-bottom for it, status bar folds into a second header line (activity + progress), stat cards 2 per row, three cards stacked, buttons wrap, tables scroll horizontally inside their card. `prefers-reduced-motion` disables the tweens.

PWA: `vite-plugin-pwa` with `registerType: 'autoUpdate'`, manifest `{name:"MCARSPH AutoShare", short_name:"AutoShare", display:"standalone", start_url:"/", theme_color:"#fafafa", background_color:"#fafafa", icons: 192/512 any+maskable}`, workbox `navigateFallback: '/index.html'`, `navigateFallbackDenylist: [/^\/api\//, /^\/ws/]`, runtime caching disabled for `/api`. Dev proxy in `vite.config.js`: `/api` and `/ws` (ws: true) → `http://127.0.0.1:8000`.

**Proof `proofs/25_web_build.py`:** if `shutil.which("npm")` is None → print `SKIP: node not installed` and return; else `npm ci` (or `npm install` when no lockfile) and `npm run build` in `web/` with `check=True` (timeout 600 s); assert `web/dist/index.html`, `web/dist/manifest.webmanifest` and `web/dist/sw.js` exist.

---

## Task F2: pages Dashboard, Accounts, Log

**Files:** create `web/src/pages/Dashboard.jsx`, `web/src/pages/Accounts.jsx`, `web/src/pages/Log.jsx`, `web/src/components/StatCard.jsx`; modify `web/src/App.jsx` only to import and route the three pages (F1 leaves `// F2: pages` markers).

Consumes the store contract above, no other assumptions.

- **Dashboard**: four `StatCard`s (Total / Logged in / Need login / Disabled; count-up 300 ms with `requestAnimationFrame`, respects reduced motion); `Log in N pending accounts` (disabled when `counts.pending - counts.pending_unlinked === 0` or `server.login_run_active`; confirm dialog; `actions.loginPending()`); hint line for `pending_unlinked`; Run activity (progress from `server.run`, `last_run_summary`); System (`system.ram_used_gb / ram_total_gb`, `process_count`, `counts.active`, `sheet_last_ok` as "N s ago" ticking every second, "not started" when 0); Recent alerts (last 8 `log` entries with `level === 'error'`, newest first; "Open log" → navigate). Refresh counts every 5 s while mounted via `actions.refreshState()`.
- **Accounts**: search (name / username / profile / gmail), filter `All · Logged in · Needs login · Pending · Disabled`, `Select all` / `Clear`, table with checkbox column, `#`, Name, Username, Brave profile, Status, Reason; status precedence as `mockup/react/src/data.js` `statusOf` (`sheet_status`, `restricted`, `live`/`logged_in`); action bar: `Log in selected` (checked rows with a `linked_profile`, confirm, `actions.loginSelected`), `Check login status` (checked profiles or null), `Auto setup` (checked profiles, confirm), `Accept friend requests`, `Launch` (exactly one checked profile; note "opens a Brave window on the PC"), `Link…` (one checked unlinked account → pick from unlinked profiles list), `Unlink`. Buttons disable while `server.login_run_active` / `scan_active` / `run`. Rows show `◌ Logging in…` when `sheet_status === 'LOGGING IN'`.
- **Log**: live tail of `log`, level colours, `Pause` toggle that stops auto-scroll, `Clear` (client-side only), filter box.

Proof: covered by `25_web_build.py` (build must succeed) and the integration task.

---

## Task D1: runbook, frp example, README

**Files:** create `docs/runbooks/vps.md`, `tools/frp/frpc.example.toml`, `tools/frp/README.md`; modify `README.md` (new "Web app" section: `set_web_password.py`, `BUILD_WEB.bat`, `SERVER.bat`, phone install, VPS runbook link, `main.py` fallback; Layout block gains `src/server/`, `web/`, `server.py`).

`vps.md` = spec §11 expanded into copy-paste steps for Ubuntu 24.04 (Caddy install from the official apt repo, frp v0.61 download URL pattern, systemd unit for `frps`, `ufw`, token generation `openssl rand -hex 32`, verification `curl https://<host>/api/health`, Windows side: unzip, `frpc.toml`, `SERVER.bat`, iPhone "Add to Home Screen", troubleshooting table: 502 → PC/frpc down; cert error → DNS/port 80; 401 loop → clock skew).

---

## Task I1: integration and screenshot pass

After S1–S4, F1, F2, D1 land: `python verify.py` → `ALL PROOFS PASS`; `python proofs/25_web_build.py` path exercised; start `python server.py --dev --port 8765` with a temporary password (set via `scripts/set_web_password.py` non-interactively: `python -c "from src.server import auth; auth.store_password('verify-pass-123')"` — restore the previous hash afterwards) with the manager thread running but no browser action triggered; Playwright script (scratchpad) logs in, screenshots Dashboard/Accounts/Log/Login at 1366×800 and 390×844 in both themes; view the PNGs; fix clipping, contrast or mis-wired buttons; stop the server. Record findings in the final report.

---

## Self-review

Spec §5 modules → S1–S4; §6 frontend → F1/F2; §7 routes → S4 (every row present); §8 entry points → S4 + D1; §9 exclusivity → S4 409 rules + S3 flags; §10 proofs → 20–25 (spec's `20_server`/`21_parity`/`22_web_build` renumbered 23/24/25, plus unit proofs 20–22); §11 runbook → D1; §12 phase 1 done-criterion → I1. Types: `data.counts()` keys match the store's `counts`; `AppState.to_dict()` keys match `store.server`; `accounts_rows()` keys match F2's table; `answer_input` payload `{profile_pic, cancel}` matches `ImagePickerDialog` and `/api/input`; `HANDLED_RTYPES` and `USES` are the names `24_parity.py` reads.
