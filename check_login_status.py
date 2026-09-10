"""
Live login-status scan for all saved Brave profiles.

Reuses the overlay-aware extract_storage_state() so the 'See more on
Facebook' login dialog is detected as logged-out (the URL alone can lie).
Reports which profiles are still logged in and which need re-login.

Usage:
    python check_login_status.py
    python check_login_status.py "profile name" "other profile" ...
"""
import asyncio
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.storage import config_manager as cfg


async def main(only: list[str] | None = None) -> int:
    from src.core.facebook_automation import FacebookAutomation

    profiles = only or cfg.list_profiles()
    if not profiles:
        print("❌ No saved profiles found. Add profiles in the app first.")
        return 1

    print("=" * 70)
    print(f"LOGIN STATUS CHECK — {len(profiles)} profile(s)")
    print("=" * 70)

    results = []
    for idx, name in enumerate(profiles, 1):
        brave_path = cfg.get_profile_path(name)
        if not brave_path:
            print(f"[{idx}/{len(profiles)}] ❌ '{name}' — no Brave path")
            results.append((name, False, "no path"))
            continue

        print(f"[{idx}/{len(profiles)}] Checking '{name}'...")
        auto = FacebookAutomation(
            log_callback=lambda m: print(f"    {m}", flush=True))
        try:
            state, logged_in = await auto.extract_storage_state(
                brave_path, return_logged_in=True)
            if state is None:
                print(f"[{idx}/{len(profiles)}] ❌ '{name}' — could not extract session")
                results.append((name, False, "extract failed"))
            elif logged_in:
                print(f"[{idx}/{len(profiles)}] ✅ '{name}' — LOGGED IN")
                results.append((name, True, ""))
            else:
                print(f"[{idx}/{len(profiles)}] ❌ '{name}' — NOT LOGGED IN (needs re-login)")
                results.append((name, False, "login overlay / session expired"))
        except Exception as e:
            print(f"[{idx}/{len(profiles)}] ❌ '{name}' — error: {e}")
            results.append((name, False, str(e)))
        finally:
            try:
                await auto.cleanup()
            except Exception:
                pass

        if idx < len(profiles):
            pause = random.uniform(2.0, 4.0)
            print(f"    ⏳ pausing {pause:.1f}s before next profile (anti-throttle)...")
            await asyncio.sleep(pause)

    logged_in_count = sum(1 for _, ok, _ in results if ok)
    needs = [(n, r) for n, ok, r in results if not ok]

    print("=" * 70)
    print(f"SUMMARY — {logged_in_count}/{len(profiles)} logged in")
    if needs:
        print(f"❌ NEED RE-LOGIN ({len(needs)}):")
        for name, reason in needs:
            print(f"   • {name}  ({reason})")
        print("\n💡 Open the app → Profiles tab → Launch Profile → log in manually.")
        print("=" * 70)
        return 1  # non-zero so scripts can detect profiles needing re-login
    print("🎉 All profiles are logged in!")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(asyncio.run(main(args or None)))
