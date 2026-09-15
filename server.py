"""Web entry point: the same DriverManager src/app.py builds,
driven from a phone through FastAPI instead of a Tk window.

    python server.py [--host 127.0.0.1] [--port 8000] [--dev]

Binds 127.0.0.1 by default: the internet reaches this only through the
frp tunnel and Caddy on the VPS (docs/runbooks/vps.md), which is also
where TLS lives. --dev relaxes two things for `npm run dev`: the session
cookie loses Secure (Vite serves http://localhost) and the Vite origins
pass the CSRF check. Refuses to start without a password hash, since a
server anyone can log in to would hand the Brave profiles to whoever
found the tunnel.
"""
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.core.driver_manager import DriverManager  # noqa: E402
from src.server import auth  # noqa: E402
from src.server.app import create_app  # noqa: E402
from src.server.events import EventBridge  # noqa: E402
from src.server.logbuf import LogRing  # noqa: E402
from src.server.state import AppState  # noqa: E402

NO_PASSWORD_EXIT = 2


def _version() -> str:
    """The short git sha /api/health reports, or "dev" outside a checkout
    (or without git on PATH): the runbook's curl reads it to tell which
    build the tunnel is serving."""
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "dev"
    sha = out.stdout.strip()
    return sha if out.returncode == 0 and sha else "dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve the AutoShare web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dev", action="store_true",
                        help="allow http://localhost origins for `npm run dev`")
    args = parser.parse_args(argv)

    if auth.stored_hash() is None:
        print("No web password is set. Run:  python scripts\\set_web_password.py",
              file=sys.stderr)
        return NO_PASSWORD_EXIT

    import uvicorn  # after the password check: a missing package is the next error, not the first

    manager = DriverManager()
    state = AppState(version=_version())
    logring = LogRing()
    bridge = EventBridge(manager, state, logring)
    # Every worker line goes to the ring, the daily file and every phone -
    # what manager.log = log_tab.write did for the window.
    manager.log = lambda message: bridge.broadcast({"type": "log", **logring.write(message)})
    app = create_app(manager, state=state, logring=logring,
                     bridge=bridge, dev=args.dev)

    manager.start()
    bridge.start()
    logring.write("✓ FB Tool web server started")
    logring.write(f"Log file: {logring.log_path}")
    print(f"AutoShare web server {state.version} on http://{args.host}:{args.port}"
          f"{' (dev)' if args.dev else ''}")
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        # Reverse order of start: no more results to forward, then the
        # worker closes its browser, then the file.
        bridge.stop()
        manager.stop()
        logring.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
