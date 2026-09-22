"""Which browser the automation drives is a setting, not a hard-coded path.

Every launch pointed at one absolute Brave path. Brave binds cookie
encryption to the user-data-dir, which is what forces logins to run one at a
time inside the real Brave directory and makes profile copying produce dead
sessions. Chromium does not, so the operator asked to move - and that move is
impossible while the binary is a constant in the source.

browser_choice() answers both halves: which executable to launch (None means
Playwright's own bundled Chromium) and which user-data root its profiles live
under. Brave and Chromium keep separate roots: their cookie stores are not
interchangeable, so they must never share a directory.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("browser choice")  # noqa: F821

from src.storage import config_manager as cfg  # noqa: E402
from src.core import browser_choice as bc  # noqa: E402

_saved = cfg.get_setting(bc.SETTING_KEY, None)
try:
    cfg.save_setting(bc.SETTING_KEY, "brave")
    if bc.current_browser() != "brave":
        failures.append(f"browser choice: setting 'brave' gave {bc.current_browser()!r}")  # noqa: F821
    exe = bc.executable_path()
    if not exe or "brave" not in str(exe).lower():
        failures.append(f"browser choice: brave must launch the Brave binary, got {exe!r}")  # noqa: F821
    brave_root = bc.user_data_root()

    cfg.save_setting(bc.SETTING_KEY, "chromium")
    if bc.current_browser() != "chromium":
        failures.append(f"browser choice: setting 'chromium' gave {bc.current_browser()!r}")  # noqa: F821
    # None tells Playwright to use the Chromium it installed and version-matched.
    if bc.executable_path() is not None:
        failures.append(f"browser choice: chromium must use the bundled build "  # noqa: F821
                        f"(None), got {bc.executable_path()!r}")
    chromium_root = bc.user_data_root()

    if str(chromium_root).lower() == str(brave_root).lower():
        failures.append("browser choice: Chromium and Brave must not share a user-data "  # noqa: F821
                        "root - neither can decrypt the other's cookies")
    if "brave" in str(chromium_root).lower():
        failures.append(f"browser choice: chromium root sits inside Brave's tree: {chromium_root}")  # noqa: F821

    # An unknown value must not silently launch something unexpected.
    cfg.save_setting(bc.SETTING_KEY, "netscape")
    if bc.current_browser() not in ("brave", "chromium"):
        failures.append(f"browser choice: unknown setting must fall back to a known "  # noqa: F821
                        f"browser, got {bc.current_browser()!r}")
finally:
    if _saved is None:
        conf = cfg._load_config()
        conf.pop(bc.SETTING_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.SETTING_KEY, _saved)

# No launch may keep pointing at the old constant.
import pathlib  # noqa: E402
for rel in ("src/core/facebook_automation.py", "src/core/driver_manager.py"):
    text = (ROOT / rel).read_text(encoding="utf-8")  # noqa: F821
    if "executable_path=CHROME_PATH" in text:
        failures.append(f"browser choice: {rel} still launches the hard-coded Brave path")  # noqa: F821

print("FAILED" if [f for f in failures if "browser choice" in f] else "ok")  # noqa: F821
