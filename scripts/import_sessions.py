"""Inject exported Facebook sessions into this PC's Brave profiles.

The counterpart to export_sessions.py. Each bundle file is a storage_state -
plain JSON, no key material - so it carries a session across machines that a
copied profile folder cannot. Opening the destination profile and adding the
cookies makes Brave write them to its own cookie store, encrypted under THIS
machine's key. That re-encryption is the whole point: it is what a folder
copy skips and why a folder copy produces sessions that look present and are
not.

Profiles must already exist here. Run provision_profiles.py first - it picks
the Profile N directory, registers it in Brave's Local State and links the
roster row. Skipping it leaves nothing to import into, and an unregistered
directory is dropped by config_manager.auto_sync_brave_profiles() anyway.

Cookies only. `c_user` and `xs` carry the session; the `origins` localStorage
in the bundle is Facebook app cache, and restoring it would need a real page
load on facebook.com for every account - exactly the traffic --verify exists
to keep optional.

Brave must be closed. It holds a ProcessSingleton lock on the shared User
Data tree, so imports also run one at a time.

Usage:
    python scripts/import_sessions.py --in transfer
    python scripts/import_sessions.py --in transfer --dry-run
    python scripts/import_sessions.py --in transfer --verify
    python scripts/import_sessions.py --in transfer --force-close
"""
import argparse
import asyncio
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # scripts/
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from patchright.async_api import async_playwright

from src.core import browser_choice
from src.storage import config_manager as cfg


def brave_is_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq brave.exe"],
                             capture_output=True, text=True, timeout=10).stdout
        return "brave.exe" in out.lower()
    except Exception:
        return False


def load_manifest(bundle: str) -> dict:
    path = os.path.join(bundle, "manifest.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def age_note(exported_at: str) -> str:
    """How stale the bundle is, in words.

    Sessions die on Facebook-side logout, password change or a device flag,
    so the age of the export predicts how many of these imports will land on
    a login page rather than a home page.
    """
    try:
        then = time.mktime(time.strptime(exported_at, "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return "unknown age"
    hours = (time.time() - then) / 3600.0
    if hours < 1:
        return f"{int(hours * 60)} min old"
    if hours < 48:
        return f"{hours:.1f} h old"
    return f"{hours / 24:.1f} days old — expect expired sessions"


async def inject(pw, profile_path: str, state: dict, verify: bool) -> tuple[bool, str]:
    """Write one account's cookies into its Brave profile.

    Returns (ok, detail). The context is opened on the real profile so that
    closing it flushes the cookies into Brave's own store; an isolated
    context would hold them in memory and lose them on exit.
    """
    user_data_dir, profile_dir_name = _profile_layout(profile_path)
    # Hidden, not headless. --verify loads a real facebook.com page in this
    # context, and Chromium's headless modes put "HeadlessChrome" in the
    # User-Agent of that request. The window is minimised below instead; see
    # FacebookAutomation.hide_window.
    ctx = await pw.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        executable_path=browser_choice.executable_path(),
        headless=False,
        args=[*([f"--profile-directory={profile_dir_name}"] if profile_dir_name else [])],
    )
    try:
        cookies = state.get("cookies") or []
        if not cookies:
            return False, "bundle has no cookies"
        await ctx.add_cookies(cookies)

        if not verify:
            return True, f"{len(cookies)} cookies"

        from src.core.facebook_automation import FacebookAutomation
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        auto = FacebookAutomation(log_callback=lambda m: None)
        auto.page = page
        auto.context = ctx
        await auto.hide_window()
        await page.goto("https://www.facebook.com/",
                        timeout=30000, wait_until="domcontentloaded")
        await asyncio.sleep(3)
        signed_in = await auto._is_logged_in(timeout=15)
        return signed_in, (f"{len(cookies)} cookies, signed in" if signed_in
                           else f"{len(cookies)} cookies, NOT signed in")
    finally:
        # Brave flushes the cookie store on close; without this the injected
        # cookies never reach disk.
        await ctx.close()


def _profile_layout(profile_path: str) -> tuple[str, str | None]:
    """(user_data_dir, profile_directory) for opening one account.

    Same split FacebookAutomation uses: Brave keeps every profile inside one
    shared User Data tree and selects one with --profile-directory, while a
    Chromium profile IS its own user-data directory.
    """
    if browser_choice.current_browser() == browser_choice.CHROMIUM:
        return profile_path, None
    return os.path.dirname(profile_path), os.path.basename(profile_path)


async def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--in", dest="bundle", default="transfer",
                    help="bundle directory written by export_sessions.py")
    ap.add_argument("--only", nargs="*", metavar="PROFILE",
                    help="import just these profiles instead of all")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be imported, write nothing")
    ap.add_argument("--verify", action="store_true",
                    help="load facebook.com per account and confirm the session")
    ap.add_argument("--force-close", action="store_true",
                    help="kill Brave if it is running (open tabs are lost)")
    args = ap.parse_args(argv)

    bundle = os.path.abspath(args.bundle)
    sessions_dir = os.path.join(bundle, "sessions")
    if not os.path.isdir(sessions_dir):
        print(f"No bundle at {bundle} (expected a sessions/ directory).")
        return 1

    try:
        manifest = load_manifest(bundle)
    except Exception as e:
        print(f"Cannot read manifest.json: {e}")
        return 1

    entries = manifest.get("accounts") or []
    if args.only:
        wanted = set(args.only)
        entries = [e for e in entries if e.get("profile") in wanted]
    if not entries:
        print("Nothing to import.")
        return 1

    print("=" * 70)
    print(f"IMPORT SESSIONS — {len(entries)} account(s) from {bundle}")
    print(f"Exported {manifest.get('exported_at', '?')} "
          f"({age_note(manifest.get('exported_at', ''))})")
    print(f"Target browser: {browser_choice.current_browser()}")
    print("=" * 70)

    # Resolve every destination before opening a browser, so a missing
    # provision step is one clear message instead of N failures.
    plan, missing = [], []
    for e in entries:
        name = e.get("profile")
        path = cfg.get_profile_path(name)
        if not path:
            missing.append(name)
            continue
        plan.append((name, path, os.path.join(sessions_dir, e.get("file") or "")))

    if missing:
        print(f"\n{len(missing)} account(s) have no profile on this PC:")
        for name in missing[:10]:
            print(f"   {name}")
        if len(missing) > 10:
            print(f"   ... and {len(missing) - 10} more")
        print("Run 'python scripts/provision_profiles.py' first, then re-run.")
        if not plan:
            return 1

    if args.dry_run:
        print(f"\n--dry-run: {len(plan)} account(s) would be imported, "
              f"{len(missing)} skipped. Nothing written.")
        return 0

    if brave_is_running():
        if not args.force_close:
            print("\nBrave is running and locks the User Data tree. Close it and")
            print("run again, or pass --force-close to kill it (you will lose")
            print("open tabs).")
            return 1
        print("\nClosing Brave...")
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"],
                       capture_output=True, timeout=15)
        time.sleep(2)

    ok = failed = 0
    failures = []
    pw = await async_playwright().start()
    try:
        for idx, (name, path, state_file) in enumerate(plan, 1):
            try:
                with open(state_file, encoding="utf-8") as f:
                    state = json.load(f)
            except Exception as e:
                print(f"[{idx}/{len(plan)}] FAILED '{name}' — unreadable: {e}")
                failed += 1
                failures.append((name, "unreadable bundle file"))
                continue

            try:
                good, detail = await inject(pw, path, state, args.verify)
            except Exception as e:
                print(f"[{idx}/{len(plan)}] FAILED '{name}' — {e}")
                failed += 1
                failures.append((name, str(e).split("\n")[0]))
                continue

            if good:
                ok += 1
                print(f"[{idx}/{len(plan)}] OK '{name}' — {detail}")
            else:
                failed += 1
                failures.append((name, detail))
                print(f"[{idx}/{len(plan)}] FAILED '{name}' — {detail}")
    finally:
        await pw.stop()

    print("\n" + "=" * 70)
    print(f"Imported : {ok}")
    print(f"Failed   : {failed}")
    print(f"No profile here: {len(missing)}")
    if failures:
        print("\nFailed accounts:")
        for name, why in failures[:15]:
            print(f"   {name}: {why}")
        if len(failures) > 15:
            print(f"   ... and {len(failures) - 15} more")
        print("\nLog these accounts in by hand, or with scripts/login_accounts.py.")
    if not args.verify:
        print("\nCookies were written without contacting Facebook. To confirm the")
        print("sessions are live: python scripts/check_login_status.py")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
