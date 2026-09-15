"""Bring a freshly cloned checkout up to a working fleet, in one command.

Four steps that have to happen in this order, each already owned by its own
script - this only sequences them and stops at the first real failure:

  1. import_accounts   the workbook fills the roster
  2. provision_profiles every account gets a Brave "Profile N", registered in
                       Brave's Local State (an unregistered directory is
                       dropped again by auto_sync_brave_profiles)
  3. import_sessions   the exported cookies are written into those profiles,
                       re-encrypted under THIS machine's key
  4. check_login_status how many of them actually came back signed in

Order is not a preference. Provisioning has nothing to create until the
roster exists, and there is nowhere to inject a session until the profile
does. The roster import is what leaves linked_profile blank, which is
exactly what provisioning looks for - so importing a copied database
instead would make step 2 find nothing to do.

Carry two things from the old PC: the workbook, and the transfer/ bundle
written by export_sessions.py. The bundle is plaintext Facebook sessions.

Usage:
    python scripts/setup_machine.py --xlsx "FB ACCOUNTS.xlsx"
    python scripts/setup_machine.py --xlsx FILE --in transfer
    python scripts/setup_machine.py --xlsx FILE --dry-run
    python scripts/setup_machine.py --xlsx FILE --force-close
    python scripts/setup_machine.py --skip-import --in transfer
"""
import argparse
import asyncio
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # scripts/
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def brave_is_running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq brave.exe"],
                             capture_output=True, text=True, timeout=10).stdout
        return "brave.exe" in out.lower()
    except Exception:
        return False


def banner(number: int, total: int, title: str) -> None:
    print("\n" + "=" * 70)
    print(f"STEP {number}/{total}  {title}")
    print("=" * 70)


def run_step(number: int, total: int, title: str, call) -> int:
    """Run one step. Returns its exit code; 1 if it raised."""
    banner(number, total, title)
    started = time.time()
    try:
        rc = call()
    except SystemExit as e:
        # argparse and the scripts' own hard exits both land here.
        rc = int(e.code or 0)
    except Exception as e:
        print(f"\n{title} failed: {type(e).__name__}: {e}")
        return 1
    print(f"\n({title}: exit {rc}, {time.time() - started:.0f}s)")
    return int(rc or 0)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--xlsx", help="the roster workbook to import")
    ap.add_argument("--in", dest="bundle", default="transfer",
                    help="session bundle from export_sessions.py (default: transfer)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report every step, write nothing")
    ap.add_argument("--force-close", action="store_true",
                    help="kill Brave if it is running (open tabs are lost)")
    ap.add_argument("--skip-import", action="store_true",
                    help="the roster is already in the database")
    ap.add_argument("--skip-sessions", action="store_true",
                    help="provision profiles but inject no sessions")
    ap.add_argument("--skip-check", action="store_true",
                    help="do not run the closing login-status scan")
    args = ap.parse_args(argv)

    if not args.skip_import and not args.xlsx:
        print("--xlsx is required (or pass --skip-import if the roster is "
              "already in the database).")
        return 1
    if not args.skip_import and not os.path.exists(args.xlsx):
        print(f"Workbook not found: {args.xlsx}")
        return 1

    bundle = os.path.abspath(args.bundle)
    have_bundle = os.path.isdir(os.path.join(bundle, "sessions"))
    if not args.skip_sessions and not have_bundle:
        print(f"No session bundle at {bundle} (expected a sessions/ directory).")
        print("Run export_sessions.py on the old PC and copy the folder across,")
        print("or pass --skip-sessions to provision logged-out profiles.")
        return 1

    # Both writing steps need the Brave tree unlocked. Fail here rather than
    # halfway through, when the roster has been imported and nothing else has.
    if not args.dry_run and brave_is_running():
        if not args.force_close:
            print("Brave is running and locks the User Data tree. Close every")
            print("Brave window and run again, or pass --force-close.")
            return 1
        print("Closing Brave...")
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"],
                       capture_output=True, timeout=15)
        time.sleep(2)

    import import_accounts
    import provision_profiles
    import import_sessions
    import check_login_status

    steps = []
    if not args.skip_import:
        argv_i = ["--xlsx", args.xlsx] + (["--dry-run"] if args.dry_run else [])
        steps.append(("Import the roster", lambda: import_accounts.main(argv_i)))
    argv_p = ["--dry-run"] if args.dry_run else []
    steps.append(("Provision Brave profiles", lambda: provision_profiles.main(argv_p)))
    if not args.skip_sessions:
        argv_s = ["--in", bundle] + (["--dry-run"] if args.dry_run else [])
        steps.append(("Inject the exported sessions",
                      lambda: asyncio.run(import_sessions.main(argv_s))))
    if not args.skip_check and not args.dry_run:
        steps.append(("Check who is signed in",
                      lambda: asyncio.run(check_login_status.main())))

    total = len(steps)
    print(f"Setting up this machine in {total} step(s).")
    if args.dry_run:
        print("--dry-run: every step reports and writes nothing.")

    for i, (title, call) in enumerate(steps, 1):
        rc = run_step(i, total, title, call)
        if rc != 0:
            print("\n" + "=" * 70)
            print(f"Stopped at step {i}/{total}: {title} (exit {rc}).")
            print("Fix that step, then re-run - the earlier steps are all")
            print("re-runnable and will skip what they already did.")
            return rc

    print("\n" + "=" * 70)
    print("Machine ready.")
    if args.dry_run:
        print("Nothing was written. Re-run without --dry-run to apply.")
    else:
        print("Accounts the scan could not sign in need a manual login:")
        print("   python scripts/login_accounts.py --only <username>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
