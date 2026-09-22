"""The sheet is on by default, and the off switch still means off.

The roster is edited in the Google Sheet, so the mirror is on: the app polls
the sheet and pushes each verdict back into its STATUS column. A PC with no
business reaching Google turns that off with one setting, and off has to mean
off at the source - no token, no credentials, no socket - not a call that
fails politely. A PC without DNS was once spending a round trip per account
to be told it has no network.

Nothing under test here touches the network on either path: with the mirror
on but no service-account key, construction short-circuits before the first
HTTP call; with the mirror off, it short-circuits earlier still.
"""
import socket
import sys
import time

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("sheet off")  # noqa: F821

from src.storage import sheet_status as ss  # noqa: E402
from src.storage.roster_sheet import SheetWatcher  # noqa: E402

# On by default: the operator's roster lives in the sheet.
if not ss.SHEET_SYNC:
    failures.append("sheet off: the sheet mirror is off by default")  # noqa: F821
if not ss.sheet_enabled():
    failures.append("sheet off: sheet_enabled() is false with the mirror on")  # noqa: F821

# Now switch it off and prove that nothing reaches for Google.
opened = []
_real_connection = socket.create_connection
_real_socket = socket.socket


class _NoSocket(_real_socket):
    def connect(self, address):
        opened.append(address)
        raise AssertionError(f"the sheet is off but something dialled {address}")


def _no_connection(address, *a, **kw):
    opened.append(address)
    raise AssertionError(f"the sheet is off but something dialled {address}")


_saved_sync = ss.SHEET_SYNC
ss.SHEET_SYNC = False
socket.create_connection = _no_connection
socket.socket = _NoSocket
try:
    if ss.sheet_enabled():
        failures.append("sheet off: sheet_enabled() is true with the mirror off")  # noqa: F821
    started = time.monotonic()
    if ss.push_account_status("someone@example.com") != "":
        failures.append("sheet off: a status push wrote something")  # noqa: F821
    writer = ss.SheetWriter()
    if writer.on or "off" not in writer.error.lower():
        failures.append(f"sheet off: the writer is not off: {writer.error!r}")  # noqa: F821
    if writer.write("someone@example.com", "LOGGED IN"):
        failures.append("sheet off: an off writer reported a successful write")  # noqa: F821

    watcher = SheetWatcher(interval=0.1)
    watcher.start()
    watcher.join(timeout=3)
    if watcher.is_alive():
        failures.append("sheet off: the roster watcher is still polling")  # noqa: F821
        watcher.stop()
    if time.monotonic() - started > 5:
        failures.append("sheet off: the off path is slow, so it is doing work")  # noqa: F821
finally:
    socket.create_connection = _real_connection
    socket.socket = _real_socket
    ss.SHEET_SYNC = _saved_sync

if opened:
    failures.append(f"sheet off: {len(opened)} network connection(s) attempted: "  # noqa: F821
                    f"{opened[:2]}")

if not ss.sheet_enabled():
    failures.append("sheet off: the mirror cannot be switched back on")  # noqa: F821

print("FAILED" if [f for f in failures if "sheet off" in f] else "ok")  # noqa: F821
