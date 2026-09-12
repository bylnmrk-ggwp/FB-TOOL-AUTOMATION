"""Proof: the web server covers what the Tk window covers, read from source.

Runs under verify.py with globals `failures`, `step` and `ROOT`. Two lists
are diffed against src/ui/main_window.py so a branch added to the window
without a server counterpart fails loudly:

- every `rtype == "..."` MainWindow._handle_result switches on must be in
  events.HANDLED_RTYPES (the bridge replicates that branch);
- every `self.manager.<helper>` _connect_callbacks wires to a Tk button
  must, when it belongs to phase 1, be in app.USES (a route reaches it).
  The phase-2 helpers (queue, compose, groups) are printed as a notice so
  the remainder is visible, not failed.

Pure source reading: no app is built, no window, no browser.
"""
import re
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("parity with MainWindow")  # noqa: F821
from src.core.driver_manager import DriverManager as _DM  # noqa: E402
from src.server import app as _appmod  # noqa: E402
from src.server import events as _ev  # noqa: E402


def _fail(msg):
    failures.append(f"parity: {msg}")  # noqa: F821


_PHASE1 = {"start_profile", "auto_setup_profile", "auto_setup_all_profiles",
           "accept_all_pending_requests", "check_login_status"}

_src = (ROOT / "src" / "ui" / "main_window.py").read_text(encoding="utf-8")  # noqa: F821

# ── results: every rtype the window handles, the bridge handles ──────
_tk_rtypes = set(re.findall(r'rtype == "(\w+)"', _src))
if not _tk_rtypes:
    _fail("no rtype == \"...\" found in main_window.py; the regex is stale")
_missing = sorted(_tk_rtypes - set(_ev.HANDLED_RTYPES))
if _missing:
    _fail(f"HANDLED_RTYPES lacks {_missing}")
_extra = sorted(set(_ev.HANDLED_RTYPES) - _tk_rtypes)
print(f"rtypes: window {len(_tk_rtypes)}, bridge {len(_ev.HANDLED_RTYPES)}"
      f" (bridge-only: {_extra})")

# ── commands: every helper a Tk button reaches, a route reaches ──────
_m = re.search(r"def _connect_callbacks\(self\):(.*?)(?=\n    def )", _src, re.S)
if _m is None:
    _fail("MainWindow._connect_callbacks not found")
    _tk_helpers = set()
else:
    _tk_helpers = set(re.findall(r"self\.manager\.(\w+)", _m.group(1)))
if not _PHASE1 <= _tk_helpers:
    _fail(f"_connect_callbacks no longer wires {sorted(_PHASE1 - _tk_helpers)};"
          " update _PHASE1 in this proof")
_uses = set(_appmod.USES)
_unrouted = sorted((_tk_helpers & _PHASE1) - _uses)
if _unrouted:
    _fail(f"phase-1 helpers without a route (app.USES): {_unrouted}")
for _name in sorted(_uses):
    if not callable(getattr(_DM, _name, None)):
        _fail(f"app.USES names {_name!r}, which DriverManager lacks")
_phase2 = sorted(_tk_helpers - _uses)
print(f"helpers: window wires {len(_tk_helpers)}, routes reach {len(_uses & _tk_helpers)}")
print(f"notice: phase-2 helpers not yet routed: {_phase2}")

print("ok" if not [f for f in failures if f.startswith("parity:")]  # noqa: F821
      else "FAILED")
