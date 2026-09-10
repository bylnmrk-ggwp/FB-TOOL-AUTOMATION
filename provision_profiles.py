"""Create Brave profiles for imported accounts and register them with the app.

For each account in the roster that has no linked Brave profile, this:

  1. picks the next free "Profile N" directory under Brave's User Data
  2. creates that directory
  3. registers it in Brave's Local State (profile.info_cache, profiles_order)
     with the account's username as the display name
  4. saves it as an app profile via config_manager.save_profile()
  5. links the account row to it via database.link_account()

Registration in Local State is not optional. config_manager.auto_sync_brave_profiles()
drops any saved profile whose path Brave does not report in info_cache, so an
unregistered directory would silently disappear from the config the next time
the Profiles tab syncs.

The created profiles are LOGGED OUT. Every app action resolves a Brave profile
path and then relies on an existing Facebook session, so a profile is only
usable once its account has been logged in.

Brave must be closed: it rewrites Local State on exit and would discard
whatever this script added.

Usage:
    python provision_profiles.py --dry-run          # plan only, writes nothing
    python provision_profiles.py --count 3          # provision the first 3
    python provision_profiles.py                    # provision all remaining
    python provision_profiles.py --restore-backup <path>
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BRAVE_USER_DATA = (Path(os.environ.get("LOCALAPPDATA", ""))
                   / "BraveSoftware" / "Brave-Browser" / "User Data")
LOCAL_STATE = BRAVE_USER_DATA / "Local State"


def brave_is_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq brave.exe"],
                             capture_output=True, text=True, timeout=10).stdout
        return "brave.exe" in out.lower()
    except Exception:
        return False


def load_local_state() -> dict:
    return json.loads(LOCAL_STATE.read_text(encoding="utf-8", errors="replace"))


def used_profile_numbers(state: dict) -> set:
    """Numbers taken by an info_cache entry or an on-disk directory.

    Both are consulted so a leftover directory from a deleted profile is never
    reused, which would silently graft an account onto someone else's data.
    """
    nums = set()
    for name in state.get("profile", {}).get("info_cache", {}):
        m = re.fullmatch(r"Profile (\d+)", name)
        if m:
            nums.add(int(m.group(1)))
    if BRAVE_USER_DATA.exists():
        for d in BRAVE_USER_DATA.iterdir():
            m = re.fullmatch(r"Profile (\d+)", d.name) if d.is_dir() else None
            if m:
                nums.add(int(m.group(1)))
    return nums


def make_info_entry(number: int, display_name: str) -> dict:
    """An info_cache entry shaped like the ones Brave writes itself."""
    return {
        "active_time": 0.0,
        "ai_subscription_tier": 0,
        "avatar_icon": "chrome://theme/IDR_PROFILE_AVATAR_26",
        "background_apps": False,
        "default_avatar_fill_color": -15261648,
        "default_avatar_stroke_color": -920588,
        "enterprise_label": "",
        "force_signin_profile_locked": False,
        "gaia_id": "",
        "is_consented_primary_account": False,
        "is_ephemeral": False,
        "is_using_default_avatar": True,
        "is_using_default_name": False,
        "managed_user_id": "",
        "metrics_bucket_index": number + 1,
        "name": display_name,
        "profile_color_seed": -15374912,
        "profile_highlight_color": -15261648,
        "serp_metrics": {
            "brave_search_engine": [],
            "google_search_engine": [],
            "other_search_engine": [],
        },
        "shortcut_name": display_name,
        "signin.with_credential_provider": False,
        "user_name": "",
    }


def restore_backup(path: str) -> int:
    src = Path(path)
    if not src.exists():
        print(f"Backup not found: {src}")
        return 1
    if brave_is_running():
        print("Brave is running. Close it before restoring Local State.")
        return 1
    shutil.copy2(src, LOCAL_STATE)
    print(f"Restored {LOCAL_STATE.name} from {src.name}")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=None,
                    help="provision at most this many accounts")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the plan, write nothing")
    ap.add_argument("--force-close", action="store_true",
                    help="kill running Brave processes first (loses open tabs)")
    ap.add_argument("--restore-backup", metavar="PATH",
                    help="restore a Local State backup and exit")
    args = ap.parse_args(argv)

    if args.restore_backup:
        return restore_backup(args.restore_backup)

    if not LOCAL_STATE.exists():
        print(f"Brave Local State not found at {LOCAL_STATE}")
        return 1

    from src.storage import config_manager as cfg
    from src.storage import database as db

    accounts = [a for a in db.list_accounts() if not a.get("linked_profile")]
    if args.count is not None:
        accounts = accounts[:args.count]
    if not accounts:
        print("No unlinked accounts to provision.")
        return 0

    state = load_local_state()
    used = used_profile_numbers(state)
    saved = {n.lower() for n in cfg.list_profiles()}
    existing_names = {v.get("name", "").lower()
                      for v in state["profile"]["info_cache"].values()}

    plan, skipped = [], []
    nxt = 1
    for a in accounts:
        name = (a.get("username") or "").strip()
        if not name:
            skipped.append((a.get("sheet_no"), "no username"))
            continue
        if name.lower() in saved or name.lower() in existing_names:
            skipped.append((name, "a profile with this name already exists"))
            continue
        while nxt in used:
            nxt += 1
        used.add(nxt)
        plan.append((nxt, name, a))

    print(f"Brave User Data : {BRAVE_USER_DATA}")
    print(f"Brave running   : {brave_is_running()}")
    print(f"Accounts unlinked in roster: {len(accounts)}")
    print(f"To provision    : {len(plan)}")
    if skipped:
        print(f"Skipped         : {len(skipped)}")
        for who, why in skipped[:10]:
            print(f"   {who}: {why}")
    if plan:
        lo, hi = plan[0][0], plan[-1][0]
        print(f"Profile numbers : {lo}..{hi} (gaps in the existing range reused)")
        print("\nFirst few:")
        for number, name, _ in plan[:5]:
            print(f"   Profile {number:<4} -> {name}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    if brave_is_running():
        if not args.force_close:
            print("\nBrave is running. It rewrites Local State on exit and would")
            print("discard these entries. Close Brave and run again, or pass")
            print("--force-close to kill it (you will lose open tabs).")
            return 1
        print("\nClosing Brave...")
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"],
                       capture_output=True, timeout=15)
        time.sleep(2)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = LOCAL_STATE.with_name(f"Local State.backup-{stamp}")
    shutil.copy2(LOCAL_STATE, backup)
    print(f"\nBacked up Local State -> {backup.name}")

    # Re-read after any taskkill, so Brave's own exit write is the base.
    state = load_local_state()
    profile = state.setdefault("profile", {})
    info = profile.setdefault("info_cache", {})
    order = profile.setdefault("profiles_order", [])

    created = 0
    for number, name, acct in plan:
        dir_name = f"Profile {number}"
        target = BRAVE_USER_DATA / dir_name
        try:
            target.mkdir(parents=False, exist_ok=True)
            info[dir_name] = make_info_entry(number, name)
            if dir_name not in order:
                order.append(dir_name)
            cfg.save_profile(name, str(target))
            db.link_account(acct["username"], name)
            created += 1
            print(f"  Profile {number:<4} {name}")
        except Exception as e:
            print(f"  FAILED Profile {number} for {name}: {e}")

    profile["profiles_created"] = profile.get("profiles_created", 0) + created
    LOCAL_STATE.write_text(json.dumps(state), encoding="utf-8")

    total, linked = db.count_accounts()
    print(f"\nCreated {created} profile(s).")
    print(f"App profiles now : {len(cfg.list_profiles())}")
    print(f"Roster           : {total} account(s), {linked} linked")
    print("\nThese profiles are LOGGED OUT. Open Brave to confirm they appear,")
    print("then log each account in before the app can drive it.")
    print(f"To undo the Local State change: python {Path(__file__).name} "
          f"--restore-backup \"{backup}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
