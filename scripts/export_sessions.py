"""Export every profile's Facebook session to machine-independent JSON.

Brave binds its cookie key to the machine and the user-data tree
(`os_crypt.app_bound_encrypted_key` in Local State), so copying profile
FOLDERS to another PC produces cookies the destination cannot decrypt -
sessions that look present and are not. A storage_state carries the same
session as plain JSON with no key material in it at all, which is what makes
it portable.

Reuses extract_storage_state(), whose verdict is "the profile reached its
Facebook home page with no login UI". Only profiles that come back logged in
are written: a logged-out state is dead weight, and importing one would
overwrite a good session on the destination with an expired one.

The written files are PLAINTEXT FACEBOOK SESSIONS. Anyone holding one is
signed in as that account without its password or second factor. Treat the
output directory like the account spreadsheet: never commit it, and hand it
over encrypted.

Usage:
    python scripts/export_sessions.py --out transfer
    python scripts/export_sessions.py --out transfer --only user1 user2
    python scripts/export_sessions.py --out transfer --include-logged-out
"""
import argparse
import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # scripts/
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.core import browser_choice
from src.storage import config_manager as cfg


def safe_filename(name: str) -> str:
    """A file name for this profile that survives both Windows and git.

    Profile names are usernames - email addresses and phone numbers - so
    they already avoid most trouble, but a stray separator would otherwise
    write outside the bundle.
    """
    return "".join(ch if (ch.isalnum() or ch in "-_.@") else "_"
                   for ch in (name or "")).strip("_") or "profile"


async def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="transfer",
                    help="bundle directory to write (default: transfer)")
    ap.add_argument("--only", nargs="*", metavar="PROFILE",
                    help="export just these profiles instead of all")
    ap.add_argument("--include-logged-out", action="store_true",
                    help="also write profiles that are not signed in")
    args = ap.parse_args(argv)

    from src.core.facebook_automation import FacebookAutomation

    profiles = args.only or cfg.list_profiles()
    if not profiles:
        print("No saved profiles found. Add profiles in the app first.")
        return 1

    out_dir = os.path.abspath(args.out)
    sessions_dir = os.path.join(out_dir, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)

    print("=" * 70)
    print(f"EXPORT SESSIONS — {len(profiles)} profile(s) -> {out_dir}")
    print("=" * 70)

    entries = []
    written = skipped_out = failed = 0

    for idx, name in enumerate(profiles, 1):
        profile_path = cfg.get_profile_path(name)
        if not profile_path:
            print(f"[{idx}/{len(profiles)}] SKIP '{name}' — no profile path")
            failed += 1
            continue

        print(f"[{idx}/{len(profiles)}] Exporting '{name}'...")
        auto = FacebookAutomation(
            log_callback=lambda m: print(f"    {m}", flush=True))
        try:
            state, logged_in = await auto.extract_storage_state(
                profile_path, return_logged_in=True)
        except Exception as e:
            print(f"[{idx}/{len(profiles)}] FAILED '{name}' — {e}")
            failed += 1
            continue

        if state is None:
            print(f"[{idx}/{len(profiles)}] FAILED '{name}' — could not extract")
            failed += 1
            continue

        if not logged_in and not args.include_logged_out:
            print(f"[{idx}/{len(profiles)}] SKIP '{name}' — not signed in")
            skipped_out += 1
            continue

        fname = safe_filename(name) + ".json"
        with open(os.path.join(sessions_dir, fname), "w", encoding="utf-8") as f:
            json.dump(state, f)
        entries.append({
            "profile": name,
            "file": fname,
            "source_profile_path": profile_path,
            "cookies": len(state.get("cookies", [])),
            "logged_in": logged_in,
        })
        written += 1
        print(f"[{idx}/{len(profiles)}] OK '{name}' — "
              f"{len(state.get('cookies', []))} cookies"
              f"{'' if logged_in else ' (NOT signed in)'}")

    manifest = {
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source_browser": browser_choice.current_browser(),
        "accounts": entries,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n" + "=" * 70)
    print(f"Written  : {written}")
    print(f"Skipped  : {skipped_out} (not signed in)")
    print(f"Failed   : {failed}")
    print(f"Bundle   : {out_dir}")
    print("\nThese files are plaintext Facebook sessions — anyone holding one is")
    print("signed in as that account. Never commit them; transfer encrypted.")
    print("Sessions expire. Import soon after exporting, not weeks later.")
    print("\nOn the destination PC, in order:")
    print("   python scripts/provision_profiles.py")
    print(f"   python scripts/import_sessions.py --in {os.path.basename(out_dir)}")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1:])))
