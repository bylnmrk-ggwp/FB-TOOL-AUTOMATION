"""A workspace for reaching one account out of forty-nine.

The Profiles tab is built for maintaining a roster - link, rename, scan,
re-login - and reaching one particular account through it means scrolling a
listbox of paths. The workspace answers the other question: open THAT
account, now. Cards, a search that filters as you type, a status colour per
account, and one click to open its real browser window.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("accounts workspace")  # noqa: F821

from src.ui.main_window import MainWindow  # noqa: E402
from src.ui.workspace import AccountsWorkspace  # noqa: E402

# It lists this browser's profiles, with the status the roster recorded.
refresh = inspect.getsource(AccountsWorkspace.refresh)
if "list_profiles_for_browser" not in refresh:
    failures.append("accounts workspace: it lists profiles of both browsers, so it "  # noqa: F821
                    "offers accounts this browser cannot open")
if "logged_in_profiles" not in refresh:
    failures.append("accounts workspace: no card shows whether the session is live")  # noqa: F821

# Search filters on what an operator actually remembers.
visible = inspect.getsource(AccountsWorkspace._visible)
for field in ("label", "profile", "username"):
    if field not in visible:
        failures.append(f"accounts workspace: search ignores the {field}")  # noqa: F821

# Opening goes through the caller's launcher - the workspace drives nothing.
source = inspect.getsource(AccountsWorkspace)
for forbidden in ("FacebookAutomation", "async_playwright", "page.goto"):
    if forbidden in source:
        failures.append(f"accounts workspace: it reaches for {forbidden} itself "  # noqa: F821
                        f"instead of handing the profile to the launcher")
if "self._on_open(profile)" not in source:
    failures.append("accounts workspace: clicking a card opens nothing")  # noqa: F821

# Many at once, because forty-nine is the point.
if not hasattr(AccountsWorkspace, "_open_selected"):
    failures.append("accounts workspace: accounts can only be opened one at a time")  # noqa: F821

# The app offers it, and only ever one window.
opener = inspect.getsource(MainWindow._open_workspace)
if "AccountsWorkspace" not in opener:
    failures.append("accounts workspace: the app never opens the workspace")  # noqa: F821
if "winfo_exists" not in opener or "lift" not in opener:
    failures.append("accounts workspace: a second press opens a second window with "  # noqa: F821
                    "its own stale selection")
build = inspect.getsource(MainWindow._build_ui) if hasattr(MainWindow, "_build_ui") \
    else inspect.getsource(MainWindow)
if "workspace_btn" not in build:
    failures.append("accounts workspace: there is no way into it from the app")  # noqa: F821

print("FAILED" if [f for f in failures if "accounts workspace" in f] else "ok")  # noqa: F821
