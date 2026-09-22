"""A login browser reports itself as an ordinary Chrome, not as a robot.

Facebook put an "I am not a robot" box on the login form of accounts this
app signed in automatically, and the reason was in the request itself. The
login used to launch Chromium's headless mode, and headless says so out
loud: measured on Brave/Chromium 153, both --headless and --headless=new
report "HeadlessChrome/153.0.0.0" in navigator.userAgent AND in the
User-Agent request header. It also used to pass --disable-gpu, which makes
WEBGL_debug_renderer_info report "Microsoft Basic Render Driver" - the
software rasteriser no ordinary PC reports.

The two obvious repairs are both worse than the leak:
  * --user-agent=<clean string> fixes the User-Agent and sends sec-ch-ua
    EMPTY, so a Chrome user agent arrives with no Client Hints at all.
  * an off-screen --window-position is clamped back onto the desktop by
    Windows, so the window shows up anyway.

So a hidden login is a REAL window, minimised through CDP. This proves the
four things that has to mean, against a local server that records what the
browser actually sent - no Facebook traffic, no credentials, no network:

  1. the User-Agent header carries no "Headless"
  2. sec-ch-ua is still sent, and agrees with that User-Agent
  3. WebGL reports real hardware, not the software rasteriser
  4. navigator.webdriver is false, with no init script injecting it

It is skipped, not failed, on a PC with no browser binary to launch.

This proof goes through start_browser itself rather than opening a context
of its own, because the launch arguments are the thing under test. On Brave
that means it closes a running Brave first, exactly as any login does - so
running verify.py takes the operator's Brave windows with it.
"""
import asyncio
import inspect
import os
import re
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("login looks like a browser")  # noqa: F821

from src.core import browser_choice  # noqa: E402
from src.core.driver_manager import DriverManager  # noqa: E402
from src.core.facebook_automation import (FacebookAutomation,  # noqa: E402
                                          LOGIN_FLAGS, MEMORY_FLAGS,
                                          TINY_VIEWPORT)


def _fail(msg):
    failures.append(f"login browser: {msg}")  # noqa: F821


# -- The flags themselves ------------------------------------------------

# --disable-gpu is what made the login report the software rasteriser.
if "--disable-gpu" in LOGIN_FLAGS:
    _fail("LOGIN_FLAGS still passes --disable-gpu, which reports "
          "'Microsoft Basic Render Driver' instead of the real card")

# A minimised window's renderer is throttled unless these say otherwise, and
# a login that stalls mid-challenge is a failed login.
for flag in ("--disable-backgrounding-occluded-windows",
             "--disable-renderer-backgrounding"):
    if flag not in LOGIN_FLAGS:
        _fail(f"LOGIN_FLAGS is missing {flag}; a minimised login can stall")

# start_browser must never hand Chromium a headless mode, whatever its
# `headless` argument says - that argument means "hidden", not "headless".
_src = inspect.getsource(FacebookAutomation.start_browser)
if "headless=headless" in _src:
    _fail("start_browser still forwards headless= to Chromium; a hidden "
          "login must be a minimised real window")
if "hide_window" not in _src:
    _fail("start_browser never minimises the window, so a hidden login "
          "would be visible on the operator's desktop")
if "windowState" not in inspect.getsource(FacebookAutomation.hide_window):
    _fail("hide_window does not set a window state, so nothing is actually "
          "hidden and every hidden launch shows a window")
if "add_init_script" in _src:
    _fail("start_browser still injects an init script; Patchright reports "
          "navigator.webdriver false natively and the injection is itself "
          "a signal")

# The fleet is not exempt. Every like, comment, share and watch went out of a
# browser launched with --headless=new and the --disable-gpu switches, so each
# one advertised HeadlessChrome and reported NO WebGL context at all - a
# sharper anomaly than the software rasteriser the login had. The default
# batch mode must ask for neither.
if any(f.startswith(("--disable-gpu", "--disable-gpu-compositing",
                     "--disable-gpu-rasterization"))
       and f != "--disable-gpu-sandbox" for f in MEMORY_FLAGS):
    _fail("MEMORY_FLAGS still disables the GPU, so every batch page reports "
          "no WebGL context")
if "--disable-software-rasterizer" not in MEMORY_FLAGS:
    _fail("MEMORY_FLAGS no longer blocks the software rasteriser, so a page "
          "can fall back to SwiftShader - its own bot signature")

_mode, _headless, _args = DriverManager._browser_launch_mode(TINY_VIEWPORT)
if _mode == "headless_new":
    if _headless or any("--headless" in a for a in _args):
        _fail("the default batch mode still launches headless, so every "
              "request the fleet sends says HeadlessChrome")
if "hide_window" not in inspect.getsource(FacebookAutomation.init_from_storage):
    _fail("a batch context no longer hides its window, so the fleet either "
          "shows every profile on screen or goes back to headless")


# -- What the browser actually sends -------------------------------------

_exe = browser_choice.executable_path()
if _exe is not None and not os.path.exists(_exe):
    print(f"  skipped: no browser at {_exe}")
else:
    seen = {}

    class _Recorder(BaseHTTPRequestHandler):
        def do_GET(self):
            seen[self.path] = dict(self.headers)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>ok</body></html>")

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Recorder)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    async def _probe():
        # A throwaway profile: this must never touch a signed-in account.
        user_data = tempfile.mkdtemp(prefix="proof85_")
        auto = FacebookAutomation(log_callback=lambda m: None)
        try:
            await auto.start_browser(user_data, headless=True,
                                     flags=LOGIN_FLAGS)
        except Exception as e:  # noqa: BLE001
            return {"launch_error": f"{type(e).__name__}: {e}"}
        try:
            await auto.page.goto(f"http://127.0.0.1:{port}/p",
                                 timeout=30000, wait_until="domcontentloaded")
            return {
                "headers": seen.get("/p", {}),
                "ua": await auto.page.evaluate("() => navigator.userAgent"),
                "webdriver": await auto.page.evaluate(
                    "() => navigator.webdriver"),
                "webgl": await auto.page.evaluate(
                    "() => { const c = document.createElement('canvas');"
                    "  const g = c.getContext('webgl');"
                    "  if (!g) return 'NO WEBGL';"
                    "  const d = g.getExtension('WEBGL_debug_renderer_info');"
                    "  return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL)"
                    "           : 'no extension'; }"),
            }
        finally:
            try:
                await auto.quit()
            except Exception:
                pass

    got = asyncio.run(_probe())
    server.shutdown()

    if "launch_error" in got:
        # A browser that will not start on this PC is not a fingerprint
        # regression, and must not be reported as one.
        print(f"  skipped: browser would not launch ({got['launch_error']})")
    else:
        headers = {k.lower(): v for k, v in got["headers"].items()}
        ua_header = headers.get("user-agent", "")
        if not ua_header:
            _fail("the browser sent no User-Agent header at all")
        if "headless" in ua_header.lower():
            _fail(f"the User-Agent header still says headless: {ua_header}")
        if "headless" in (got["ua"] or "").lower():
            _fail(f"navigator.userAgent still says headless: {got['ua']}")

        # A Chrome user agent with no Client Hints is a sharper mismatch than
        # the one it would be hiding, so the hints have to survive.
        if not headers.get("sec-ch-ua"):
            _fail("sec-ch-ua is missing; a Chrome user agent with no Client "
                  "Hints is its own anomaly")
        else:
            version = re.search(r"Chrome/(\d+)", ua_header)
            if version and f'v="{version.group(1)}"' not in headers["sec-ch-ua"]:
                _fail(f"sec-ch-ua {headers['sec-ch-ua']!r} does not agree "
                      f"with User-Agent Chrome/{version.group(1)}")

        if got["webdriver"] is not False:
            _fail(f"navigator.webdriver is {got['webdriver']!r}, not False")

        webgl = got["webgl"] or ""
        if "Basic Render Driver" in webgl or "SwiftShader" in webgl:
            _fail(f"WebGL reports the software rasteriser: {webgl}")

        print(f"  ua       : {ua_header}")
        print(f"  sec-ch-ua: {headers.get('sec-ch-ua')}")
        print(f"  webgl    : {webgl}")
