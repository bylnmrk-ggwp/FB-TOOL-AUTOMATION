"""Assisted Facebook login for provisioned Brave profiles.

Walks the roster accounts that have a linked Brave profile, opens each profile
in a VISIBLE browser, types the credentials, and hands control to you whenever
Facebook raises a checkpoint or 2FA challenge. Nothing is retried unattended.

Passwords are read from the spreadsheet at run time and never written anywhere:
not to the database, not to the config, not to the log.

Why it works one account at a time: Chromium's ProcessSingleton locks the
shared Brave "User Data" directory, so two profiles cannot be driven at once.
This is the same constraint that forces login-state extraction to be
sequential elsewhere in the app.

The typing and navigation are the existing
FacebookAutomation.login_with_credentials(), which already detects
checkpoint / twofactor / approvals URLs and waits for you. This script adds
the per-profile loop, the credential lookup, and an unlimited manual window
when the built-in 120s wait runs out.

Usage:
    python login_accounts.py --dry-run        # show who would be attempted
    python login_accounts.py --count 1        # try one account
    python login_accounts.py                  # walk every linked account
    python login_accounts.py --only <username>
"""
import argparse
import asyncio
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_SHEET = "FB ACCOUNTS.xlsx"


def read_credentials(xlsx: Path) -> dict:
    """username -> password, straight from the spreadsheet.

    Held in memory for the length of the run only. Column letters are resolved
    from the header labels so a reordered sheet cannot pair the wrong password
    with an account.
    """
    with zipfile.ZipFile(xlsx) as z:
        try:
            raw = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
            shared = ["".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))
                      for si in re.findall(r"<si>(.*?)</si>", raw, re.S)]
        except KeyError:
            shared = []
        name = next((n for n in z.namelist()
                     if n.startswith("xl/worksheets/sheet")), None)
        if not name:
            raise SystemExit(f"No worksheet inside {xlsx}")
        sheet = z.read(name).decode("utf-8", "replace")

    def cells(row_xml):
        out = {}
        for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(.*?)</c>', row_xml, re.S):
            col, attrs, inner = c.group(1), c.group(2), c.group(3)
            v = re.search(r"<v>([^<]*)</v>", inner)
            if not v:
                continue
            val = v.group(1)
            if 't="s"' in attrs:
                i = int(val)
                val = shared[i] if 0 <= i < len(shared) else ""
            out[col] = val.strip()
        return out

    rows = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S)
    if not rows:
        raise SystemExit(f"{xlsx} has no rows")
    header = cells(rows[0])
    col_user = col_pass = None
    for col, label in header.items():
        up = label.upper().strip()
        if up == "USERNAME":
            col_user = col
        elif up == "PASSWORD":
            col_pass = col
    if not col_user or not col_pass:
        raise SystemExit(f"{xlsx}: need USERNAME and PASSWORD columns, "
                         f"found {sorted(header.values())}")

    creds = {}
    for row_xml in rows[1:]:
        d = cells(row_xml)
        u = d.get(col_user, "")
        p = d.get(col_pass, "")
        if u and p:
            creds[u.lower()] = p
    return creds


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "s"


SESSION_COOKIES = ("c_user", "xs")


async def has_session(auto) -> bool:
    """True only if Facebook actually issued a logged-in session.

    _is_logged_in() infers login from the absence of a login form or overlay,
    which can pass transiently on a page that never authenticated: a real
    test run reported "Login successful" while the profile ended up holding
    only datr/fr/sb/wd, i.e. device identifiers and no session at all.
    c_user (the account id) and xs (the session token) are the two cookies
    that constitute a session, so check for those instead of guessing.
    """
    try:
        cookies = await auto.context.cookies()
    except Exception:
        return False
    names = {c.get("name") for c in cookies
             if "facebook" in (c.get("domain") or "")}
    return all(n in names for n in SESSION_COOKIES)


async def login_one(account: dict, password: str, log) -> tuple[bool, str]:
    """Open this account's Brave profile and log it in, assisted."""
    from src.core.facebook_automation import (FacebookAutomation,
                                              LOGIN_FLAGS)
    from src.storage import config_manager as cfg

    profile_name = account["linked_profile"]
    brave_path = cfg.get_profile_path(profile_name)
    if not brave_path:
        return False, f"profile '{profile_name}' has no Brave path"

    auto = FacebookAutomation()
    auto.log = log
    try:
        # Visible: a checkpoint cannot be cleared in a headless window, and
        # start_browser is headless by default.
        await auto.start_browser(brave_path, headless=False,
                                 flags=LOGIN_FLAGS)
        await auto.go_to_facebook()

        if await has_session(auto):
            return True, "already logged in - skipped"

        ok, msg = await auto.login_with_credentials(account["username"], password)

        # Trust cookies over the DOM heuristic, whichever way they disagree.
        if ok and not await has_session(auto):
            ok, msg = False, ("reported success but no session cookies "
                              "(c_user/xs missing) - not logged in")

        if ok:
            return True, msg

        # Give the operator as long as they need on a challenge, rather than
        # failing the account at the built-in 120s wait.
        while True:
            try:
                url = auto.page.url[:80]
            except Exception:
                url = "?"
            print(f"    not logged in. current page: {url}")
            choice = ask("    [Enter] I cleared it, re-check  /  [s] skip: ")
            if choice == "s":
                return False, f"skipped - {msg}"
            if await has_session(auto):
                return True, "logged in after manual step"
    except Exception as e:
        return False, f"error: {e}"
    finally:
        try:
            await auto.quit()
        except Exception:
            pass


async def run(args) -> int:
    from src.storage import database as db

    xlsx = Path(args.sheet) if args.sheet else Path(__file__).resolve().parent / DEFAULT_SHEET
    if not xlsx.exists():
        print(f"Spreadsheet not found: {xlsx}")
        return 1

    accounts = [a for a in db.list_accounts() if a.get("linked_profile")]
    if args.only:
        accounts = [a for a in accounts
                    if a["username"].lower() == args.only.lower()]
    if args.count is not None:
        accounts = accounts[:args.count]

    if not accounts:
        print("No accounts with a linked Brave profile. Run "
              "provision_profiles.py first.")
        return 0

    creds = read_credentials(xlsx)
    missing = [a["username"] for a in accounts
               if a["username"].lower() not in creds]

    print(f"Accounts with a Brave profile : {len(accounts)}")
    print(f"Passwords found in sheet      : {len(accounts) - len(missing)}")
    if missing:
        print(f"No password in sheet          : {len(missing)}")
        for u in missing[:5]:
            print(f"   {u}")

    todo = [a for a in accounts if a["username"].lower() in creds]
    if args.dry_run:
        print("\nWould attempt, in order:")
        for a in todo:
            print(f"   {a['linked_profile']}  ({a.get('facebook_name') or '?'})")
        print("\n--dry-run: no browser opened.")
        return 0

    print("\nOne at a time; Brave's profile lock allows no parallelism.")
    print("A visible window opens per account. Solve any checkpoint in it.\n")

    results = {"ok": [], "failed": []}
    for i, a in enumerate(todo, 1):
        label = a.get("facebook_name") or a["username"]
        print(f"[{i}/{len(todo)}] {label}  ->  profile '{a['linked_profile']}'")

        def log(msg, _i=i):
            print(f"    {msg}")

        ok, msg = await login_one(a, creds[a["username"].lower()], log)
        print(f"    {'OK' if ok else 'FAILED'}: {msg}\n")
        (results["ok"] if ok else results["failed"]).append((label, msg))

        if not ok and not args.keep_going:
            choice = ask("  continue with the next account? [Enter] yes, [q] stop: ")
            if choice == "q":
                print("  stopped.")
                break

    print("=" * 60)
    print(f"Logged in : {len(results['ok'])}")
    print(f"Failed    : {len(results['failed'])}")
    for label, msg in results["failed"]:
        print(f"   {label}: {msg}")
    print("\nPasswords were held in memory only; nothing was written.")
    return 0 if not results["failed"] else 2


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help=f"path to the xlsx (default: {DEFAULT_SHEET})")
    ap.add_argument("--count", type=int, help="attempt at most this many")
    ap.add_argument("--only", metavar="USERNAME", help="attempt a single account")
    ap.add_argument("--dry-run", action="store_true",
                    help="list who would be attempted, open nothing")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not pause for confirmation after a failure")
    return asyncio.run(run(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
