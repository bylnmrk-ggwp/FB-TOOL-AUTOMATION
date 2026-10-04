"""The automation drives Brave, and says so in one place.

There were two browsers for a while. Playwright's own Chromium was added
because Brave binds cookie encryption to the user-data-dir, so only one
profile can be driven at a time and a copied profile comes up with cookies
nothing can decrypt; a Chromium profile is self-contained, so one directory
per account could log in side by side. Every session the fleet actually banks
lives in Brave's tree, so that second path is gone.

What must hold now: one module answers which binary to launch and where its
profiles live, every launch asks it instead of naming a path, and nothing
claims Brave can run profiles in parallel - Chromium's ProcessSingleton locks
the shared User Data tree, so an overlapping launch is handed to the running
instance and reports "Opening in existing browser session".
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("browser choice")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402

if bc.current_browser() != "brave":
    failures.append(f"browser choice: the driven browser must be brave, "  # noqa: F821
                    f"got {bc.current_browser()!r}")

exe = bc.executable_path()
if not exe or "brave" not in str(exe).lower():
    failures.append(f"browser choice: must launch the Brave binary, got {exe!r}")  # noqa: F821

# None would hand Playwright its own bundled build, which shares no cookie
# store with Brave: a launch there opens a profile with no session in it.
if exe is None:
    failures.append("browser choice: executable_path must never be None - that "  # noqa: F821
                    "launches Playwright's bundled Chromium, whose cookie store "
                    "is not Brave's")

root = str(bc.user_data_root()).lower()
if "brave" not in root or not root.endswith("user data"):
    failures.append(f"browser choice: profiles must live in Brave's User Data "  # noqa: F821
                    f"tree, got {bc.user_data_root()!r}")

if bc.supports_parallel_login():
    failures.append("browser choice: Brave cannot log in several profiles at once - "  # noqa: F821
                    "one ProcessSingleton guards the shared User Data tree")

# The removed browser must leave nothing behind that a caller could branch on.
for gone in ("CHROMIUM", "CHROMIUM_USER_DATA", "KNOWN", "profile_dir"):
    if hasattr(bc, gone):
        failures.append(f"browser choice: browser_choice.{gone} still exists, so a "  # noqa: F821
                        f"caller can still ask for a browser that is not driven")

# No launch may keep pointing at the old constant.
for rel in ("src/core/facebook_automation.py", "src/core/driver_manager.py"):
    text = (ROOT / rel).read_text(encoding="utf-8")  # noqa: F821
    if "executable_path=CHROME_PATH" in text:
        failures.append(f"browser choice: {rel} still launches the hard-coded Brave path")  # noqa: F821

# Per-profile launches must not overlap: each one takes its own persistent
# context on the shared tree, and the second loses.
setup = (ROOT / "src/core/driver_manager.py").read_text(encoding="utf-8")  # noqa: F821
if "MAX_CONCURRENT = 2 if browser_choice.supports_parallel_login() else 1" not in setup:
    failures.append("browser choice: auto-setup still fixes its own concurrency "  # noqa: F821
                    "instead of asking whether the browser allows overlap")

print("FAILED" if [f for f in failures if "browser choice" in f] else "ok")  # noqa: F821
