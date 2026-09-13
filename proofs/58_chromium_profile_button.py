"""Creating profiles follows the selected browser, in both UIs.

The web route used to run scripts/provision_profiles.py unconditionally, so
with Chromium selected it registered Brave profiles that no run would ever
open - and it refused to start while Brave was open, which has nothing to do
with Chromium. The desktop Profiles tab gained the same action as a button,
because a parallel login needs one directory per account first.
"""
import inspect
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("chromium profile button")  # noqa: F821

from src.core import browser_choice as bc  # noqa: E402
from src.server.routes import accounts as routes  # noqa: E402
from src.storage import config_manager as cfg  # noqa: E402
from src.ui.profiles_tab import ProfilesTab  # noqa: E402

_saved = cfg.get_setting(bc.SETTING_KEY, None)
try:
    # With Chromium selected the route creates directories, never Brave profiles.
    cfg.save_setting(bc.SETTING_KEY, "chromium")
    seen = []
    import src.core.chromium_profiles as cp
    real_provision = cp.provision_all
    cp.provision_all = lambda log=print: (seen.append("chromium"),
                                          {"created": 1, "already": 0, "skipped": 0})[1]
    try:
        code = routes._provision_run(lambda line: None)
    finally:
        cp.provision_all = real_provision
    if seen != ["chromium"]:
        failures.append("chromium profile button: with Chromium selected the route "  # noqa: F821
                        "did not create Chromium profiles")
    if code != 0:
        failures.append(f"chromium profile button: the route reported exit {code}")  # noqa: F821

    # Brave's "close every window first" guard must not block a Chromium run:
    # Brave is not involved and its Local State is never written.
    src = inspect.getsource(routes.provision)
    if "brave and deps" not in src:
        failures.append("chromium profile button: the route still refuses to create "  # noqa: F821
                        "profiles while Brave is open, whatever browser is selected")

    # The desktop tab has the button, and it refuses on Brave rather than
    # creating directories no Brave run would ever open.
    if not hasattr(ProfilesTab, "_on_create_chromium_profiles"):
        failures.append("chromium profile button: the Profiles tab has no button "  # noqa: F821
                        "to create Chromium profiles")
    else:
        btn = inspect.getsource(ProfilesTab._on_create_chromium_profiles)
        if "CHROMIUM" not in btn:
            failures.append("chromium profile button: the desktop button does not "  # noqa: F821
                            "check which browser is selected")
        if "provision_all" not in btn:
            failures.append("chromium profile button: the desktop button does not "  # noqa: F821
                            "provision every roster account")
    build = inspect.getsource(ProfilesTab._build_ui)
    if "make_profiles_btn" not in build:
        failures.append("chromium profile button: the button is never placed in the tab")  # noqa: F821
finally:
    if _saved is None:
        conf = cfg._load_config()
        conf.pop(bc.SETTING_KEY, None)
        cfg._save_config(conf)
    else:
        cfg.save_setting(bc.SETTING_KEY, _saved)

print("FAILED" if [f for f in failures if "chromium profile button" in f] else "ok")  # noqa: F821
