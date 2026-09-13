"""The desktop app has a button that re-logs in every account that needs it.

The web page grew "Re-login not logged in" first, but `python main.py` now
opens the Tk window, so the same action has to be reachable there: one press
that takes every roster account with a usable Brave profile whose session is
not live, and runs the login for all of them.
"""
import sys
import tkinter as tk

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("desktop re-login button")  # noqa: F821

from src.ui.profiles_tab import ProfilesTab  # noqa: E402

for name in ("set_on_relogin_all", "set_relogin_enabled"):
    if not callable(getattr(ProfilesTab, name, None)):
        failures.append(f"desktop re-login: ProfilesTab.{name} missing")  # noqa: F821

root = tk.Tk()
root.withdraw()
try:
    tab = ProfilesTab(root)
    if not hasattr(tab, "relogin_btn"):
        failures.append("desktop re-login: the Re-login button widget is missing")  # noqa: F821
    else:
        label = str(tab.relogin_btn.cget("text")).lower()
        if "log in" not in label and "login" not in label:
            failures.append(f"desktop re-login: button label reads {label!r}")  # noqa: F821

        got = []
        tab.set_on_relogin_all(lambda usernames: got.append(usernames))
        # Fixed targets: this proves the button wiring, not the roster query,
        # and stays true whatever another proof left patched.
        tab._needs_login = lambda: [{"username": "verify_a@example.com"},
                                    {"username": "verify_b@example.com"}]
        # Pressing it must hand a list of usernames to the callback, never
        # profile names: the worker looks each one up in the roster.
        tab._on_relogin_all(confirm=False)
        if not got:
            failures.append("desktop re-login: pressing the button called no callback")  # noqa: F821
        elif not isinstance(got[0], list):
            failures.append(f"desktop re-login: callback got {type(got[0]).__name__}, wanted a list")  # noqa: F821

        # Disabling must actually grey the widget, so a second press cannot
        # start a parallel run while one is driving Brave.
        tab.set_relogin_enabled(False)
        if str(tab.relogin_btn.cget("state")) != "disabled":
            failures.append("desktop re-login: set_relogin_enabled(False) left it clickable")  # noqa: F821
        tab.set_relogin_enabled(True)
        if str(tab.relogin_btn.cget("state")) == "disabled":
            failures.append("desktop re-login: set_relogin_enabled(True) did not re-enable it")  # noqa: F821
finally:
    root.destroy()

# The window must wire the button to the worker's login command.
import inspect  # noqa: E402
from src.ui.main_window import MainWindow  # noqa: E402
wiring = inspect.getsource(MainWindow._connect_callbacks)
if "set_on_relogin_all" not in wiring:
    failures.append("desktop re-login: MainWindow never wires set_on_relogin_all")  # noqa: F821

print("FAILED" if [f for f in failures if "desktop re-login" in f] else "ok")  # noqa: F821
