"""Launcher. Default: the web UI (the sidebar admin shell) in your browser.

    python main.py            build web/dist if needed, start the server,
                              open http://127.0.0.1:8000 in the browser
    python main.py --port N   serve on a different port
    python main.py --no-open  start the server but do not open a browser
    python main.py --tk       the old Tkinter window instead (fallback)

The web UI and the Tk window drive the SAME DriverManager, SQLite database
and Brave profiles on this PC; the web build just lets a phone or another
computer reach them through the tunnel (docs/runbooks/vps.md). The Tk window
stays as a no-Node fallback until the web UI has full feature parity.
"""
import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _ensure_web_build() -> bool:
    """Make sure web/dist exists so the server serves the real UI, not the
    'not built' placeholder. Returns True when a build is present.

    A first run (or a git pull that touched web/) has no dist; build it with
    npm. When Node is absent we cannot build, so we say so and let the server
    come up on its placeholder rather than refusing to start.
    """
    dist = ROOT / "web" / "dist" / "index.html"
    if dist.exists():
        return True
    npm = "npm.cmd" if os.name == "nt" else "npm"
    print("web/dist not found - building the web UI (first run only)...")
    try:
        for cmd in (["ci"], ["run", "build"]):
            subprocess.run([npm, *cmd], cwd=ROOT / "web", check=True)
    except FileNotFoundError:
        print("Node/npm is not installed, so the web UI cannot be built.\n"
              "Install Node 18+ (https://nodejs.org) and run BUILD_WEB.bat,\n"
              "or run  python main.py --tk  for the desktop window instead.",
              file=sys.stderr)
        return False
    except subprocess.CalledProcessError:
        print("The web build failed; see the npm output above.", file=sys.stderr)
        return False
    return dist.exists()


def _ensure_password() -> bool:
    """The server refuses to start without an operator password. Set one
    interactively on first run; when there is no console to prompt at, point
    the operator at the script and stop."""
    from src.server import auth
    if auth.stored_hash() is not None:
        return True
    if not sys.stdin or not sys.stdin.isatty():
        print("No web password is set. Run:  python scripts\\set_web_password.py",
              file=sys.stderr)
        return False
    print("First run: set the password the web login page will accept.")
    from scripts import set_web_password
    return set_web_password.main([]) == 0


def _open_browser_when_up(url: str, health: str) -> None:
    """Open the browser once the server answers, so the first page load is
    the app and not a connection error. Runs in a daemon thread; gives up
    quietly after ~15 s (the server still runs, the operator can open it)."""
    import urllib.request
    for _ in range(60):
        time.sleep(0.25)
        try:
            with urllib.request.urlopen(health, timeout=1) as r:
                if r.status == 200:
                    break
        except Exception:
            continue
    else:
        return
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the FB Tool UI.")
    parser.add_argument("--tk", action="store_true",
                        help="run the old Tkinter window instead of the web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-open", action="store_true",
                        help="do not open a browser (web mode)")
    args = parser.parse_args(argv)

    if args.tk:
        from src.app import run
        run()
        return 0

    _ensure_web_build()  # a failed build still serves the placeholder; carry on
    if not _ensure_password():
        return 2

    url = f"http://{args.host}:{args.port}"
    if not args.no_open:
        threading.Thread(target=_open_browser_when_up,
                         args=(url, f"{url}/api/health"), daemon=True).start()

    import server
    return server.main(["--host", args.host, "--port", str(args.port)])


if __name__ == "__main__":
    sys.exit(main())
