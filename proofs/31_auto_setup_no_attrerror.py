"""Proof (BUG 2): _do_auto_setup must not call a non-existent method.

driver_manager referenced self._automation.connect_profiles_as_friends(...),
which is not defined anywhere on FacebookAutomation. With 2+ saved profiles
the auto-setup command ended in AttributeError and reported failure even
though the setup itself succeeded. Friending is already covered by
auto_setup_profile(connect_friends=True) (its default), so the whole
"Step 3" block was removed.

This is a source-scan regression guard: the symbol must not appear anywhere
in driver_manager.py. No browser, no Google, no Brave dir.
"""
import sys

sys.path.insert(0, str(ROOT))

step("auto-setup has no connect_profiles_as_friends call")

_src = (ROOT / "src" / "core" / "driver_manager.py").read_text(encoding="utf-8")

if "connect_profiles_as_friends" in _src:
    failures.append(
        "auto-setup: driver_manager.py still references "
        "connect_profiles_as_friends (method does not exist -> AttributeError)")

# Cross-check: FacebookAutomation genuinely lacks the method, so the guard is
# meaningful and not just guarding a symbol that happens to exist.
from src.core.facebook_automation import FacebookAutomation  # noqa: E402
if hasattr(FacebookAutomation, "connect_profiles_as_friends"):
    failures.append(
        "auto-setup: FacebookAutomation unexpectedly grew "
        "connect_profiles_as_friends; revisit the fix")

print("ok" if not [f for f in failures if f.startswith("auto-setup")] else "FAILED")
