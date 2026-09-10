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
    python scripts/login_accounts.py --dry-run        # show who would be attempted
    python scripts/login_accounts.py --count 1        # try one account
    python scripts/login_accounts.py                  # walk every linked account
    python scripts/login_accounts.py --only <username>
    python scripts/login_accounts.py --unattended --batch 10 --pause 20
        # no prompts: log in what logs in, skip and report the rest;
        # 10 accounts, then a 20 minute pause, repeat
    python scripts/login_accounts.py --unattended --hand-off-2fa
        # unattended, but stop and ask you for the code on a 2FA prompt
"""
import argparse
import asyncio
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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


def read_credentials_from_sheet() -> dict:
    """username -> password, straight from the Google Sheet via the API.

    Used when no local .xlsx is present: the roster now lives in the sheet.
    USERNAME and PASSWORD columns are located by their header labels, so a
    reordered sheet cannot pair the wrong password with an account. Passwords
    are held in memory for the run only.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # ensure scripts/ importable
    import sheets_api as api
    tok = api.token()
    rows = api.get_values(tok, api.DEFAULT_SHEET_ID, f"{api.DEFAULT_TAB}!A1:Z")
    cols = api.header_columns(rows, "USERNAME", "PASSWORD")
    if "USERNAME" not in cols or "PASSWORD" not in cols:
        raise SystemExit("Sheet needs USERNAME and PASSWORD columns; found "
                         f"{rows[0] if rows else '(empty)'}")
    cu, cp = cols["USERNAME"], cols["PASSWORD"]
    creds = {}
    for row in rows[1:]:
        u = row[cu].strip() if len(row) > cu else ""
        p = row[cp].strip() if len(row) > cp else ""
        if u and p:
            creds[u.lower()] = p
    return creds


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "s"


SESSION_COOKIES = ("c_user", "xs")


def short_reason(msg: str) -> str:
    """A brief, sheet-friendly detail for a failed login."""
    if msg == DISABLED:
        return ""                       # the DISABLED status already says it
    if msg == NEEDS_2FA:
        return "needs 2FA"
    if msg == BAD_PASSWORD:
        return "wrong password"
    if msg == BAD_IDENTIFIER:
        return "bad username"
    m = (msg or "").lower()
    if "checkpoint" in m:
        return "checkpoint"
    return (msg or "").strip()[:40]


# Outcomes worth telling apart, because the follow-up action differs:
# a disabled account is dead, a wrong password is a spreadsheet fix, and a
# 2FA prompt means the credentials were accepted and only a code is missing.
DISABLED = "ACCOUNT DISABLED by Facebook - no login possible"
NEEDS_2FA = "credentials accepted, needs a 2FA code"
BAD_PASSWORD = "wrong password in the spreadsheet"
BAD_IDENTIFIER = "username is not a valid Facebook login"


def classify(url: str, msg: str) -> str | None:
    """Name the failure from the final URL and Facebook's own error text."""
    u = (url or "").lower()
    m = (msg or "").lower()
    if "checkpoint/disabled" in u or "account has been disabled" in m:
        return DISABLED
    if "two_step_verification" in u or "twofactor" in u:
        return NEEDS_2FA
    # Facebook's copy varies ("...is invalid", "...you've entered is
    # incorrect", "...isn't connected to an account"), so key on the subject
    # word plus any rejection word rather than one exact sentence.
    rejected = any(w in m for w in ("invalid", "incorrect", "didn't match",
                                    "isn't connected", "not connected"))
    if rejected and ("email" in m or "mobile" in m or "username" in m):
        return BAD_IDENTIFIER
    if rejected and "password" in m:
        return BAD_PASSWORD
    if "checkpoint" in u:
        return "checkpoint - Facebook wants identity confirmation"
    return None


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


def _mark_ok(account: dict):
    """Clear any earlier 'disabled' mark: this account just proved it works."""
    from src.storage import database as db
    db.set_account_status(account["username"], "ok")


async def login_one(account: dict, password: str, log,
                    unattended: bool = False,
                    hand_off_2fa: bool = False) -> tuple[bool, str]:
    """Open this account's Brave profile and log it in.

    Assisted by default: a challenge waits for the operator. With
    `unattended` nothing ever waits - a challenge is recorded and skipped, so
    the run finishes on its own and the summary says who still needs a hand.
    With `hand_off_2fa`, an unattended run still stops on a 2FA prompt (only
    a 2FA prompt) so the operator can type the code, then continues on its own.
    """
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
            _mark_ok(account)
            return True, "already logged in - skipped"

        ok, msg = await auto.login_with_credentials(account["username"], password)

        # Trust cookies over the DOM heuristic, whichever way they disagree.
        if ok and not await has_session(auto):
            ok, msg = False, ("reported success but no session cookies "
                              "(c_user/xs missing) - not logged in")

        if ok:
            _mark_ok(account)
            return True, msg

        # Give the operator as long as they need on a challenge, rather than
        # failing the account at the built-in 120s wait.
        while True:
            try:
                url = auto.page.url
            except Exception:
                url = ""
            reason = classify(url, msg)

            # A disabled account cannot be recovered by waiting, so do not
            # sit at a prompt for it. Record it so --purge-disabled can
            # remove the account and its Brave profile later.
            if reason == DISABLED:
                from src.storage import database as db
                db.set_account_status(account["username"], "disabled")
                return False, DISABLED

            print(f"    not logged in: {reason or msg}")
            print(f"    page: {url[:80]}")
            if reason in (BAD_PASSWORD, BAD_IDENTIFIER):
                return False, reason
            # 2FA is the one challenge the operator can actually clear (they
            # hold the code). With --hand-off-2fa an unattended run stops here
            # so they can enter it in the open browser, then continues.
            if reason == NEEDS_2FA and hand_off_2fa:
                label = account.get("facebook_name") or account["username"]
                print("\n" + "!" * 60)
                print(f"  2FA NEEDED for {label}")
                print(f"  Enter the code in the open Brave window for "
                      f"profile '{account['linked_profile']}'.")
                print("!" * 60)
                choice = ask("    [Enter] I entered the code, re-check  /  "
                             "[s] skip this account: ")
                if choice == "s":
                    return False, NEEDS_2FA
                if await has_session(auto):
                    _mark_ok(account)
                    return True, "logged in after 2FA"
                # Not in yet: loop and re-evaluate the current page.
                msg = ""
                continue
            # Every other challenge is Facebook's decision; only a person can
            # clear it, so an unattended run records it and moves on.
            if unattended:
                return False, reason or msg
            choice = ask("    [Enter] I cleared it, re-check  /  [s] skip: ")
            if choice == "s":
                return False, reason or msg
            if await has_session(auto):
                _mark_ok(account)
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

    # Credential source: an explicit --sheet path, else the local xlsx if it
    # is still there, else the Google Sheet over the API. The roster now lives
    # in the sheet, so a missing xlsx is normal, not an error.
    xlsx = Path(args.sheet) if args.sheet else ROOT / DEFAULT_SHEET
    use_sheet = args.from_sheet or not xlsx.exists()

    # Disabled accounts are excluded: Facebook says the decision cannot be
    # appealed, so re-attempting them only adds failed logins.
    accounts = [a for a in db.list_accounts(include_disabled=args.include_disabled)
                if a.get("linked_profile")]
    if args.only:
        accounts = [a for a in accounts
                    if a["username"].lower() == args.only.lower()]

    if not accounts:
        print("No accounts with a linked Brave profile. Run "
              "scripts/provision_profiles.py first.")
        return 0

    try:
        creds = read_credentials_from_sheet() if use_sheet else read_credentials(xlsx)
    except Exception as e:
        src = "Google Sheet" if use_sheet else str(xlsx)
        print(f"Could not read credentials from {src}: {e}")
        return 1
    print(f"Credential source             : "
          f"{'Google Sheet' if use_sheet else xlsx.name}")
    missing = [a["username"] for a in accounts
               if a["username"].lower() not in creds]

    print(f"Accounts with a Brave profile : {len(accounts)}")
    print(f"Passwords found in sheet      : {len(accounts) - len(missing)}")
    if missing:
        print(f"No password in sheet          : {len(missing)}")
        for u in missing[:5]:
            print(f"   {u}")

    todo = [a for a in accounts if a["username"].lower() in creds]
    if args.skip:
        todo = todo[args.skip:]
    if args.count is not None:
        todo = todo[:args.count]
    if args.dry_run:
        print("\nWould attempt, in order:")
        for a in todo:
            print(f"   {a['linked_profile']}  ({a.get('facebook_name') or '?'})")
        print("\n--dry-run: no browser opened.")
        return 0

    print("\nOne at a time; Brave's profile lock allows no parallelism.")
    if args.unattended:
        print("Unattended: challenges are skipped and listed at the end.\n")
    else:
        print("A visible window opens per account. Solve any checkpoint in it.\n")

    results = {"ok": [], "failed": []}
    for i, a in enumerate(todo, 1):
        # Batch pacing: a long run of fresh logins from one machine is the
        # pattern most likely to draw a checkpoint on every account at once.
        # Spacing them out is the only lever that is ours to pull.
        if args.batch and i > 1 and (i - 1) % args.batch == 0:
            print(f"  batch of {args.batch} done - pausing {args.pause:g} min "
                  f"({i - 1}/{len(todo)} attempted)\n")
            await asyncio.sleep(args.pause * 60)

        label = a.get("facebook_name") or a["username"]
        print(f"[{i}/{len(todo)}] {label}  ->  profile '{a['linked_profile']}'")

        def log(msg, _i=i):
            print(f"    {msg}")

        ok, msg = await login_one(a, creds[a["username"].lower()], log,
                                  unattended=args.unattended,
                                  hand_off_2fa=args.hand_off_2fa)
        # Persist why it failed so the roster and the sheet can show it. A
        # success already cleared the status inside login_one via _mark_ok,
        # and DISABLED was recorded there too; everything else lands here.
        if not ok and msg != DISABLED:
            db.set_account_status(a["username"], "", short_reason(msg))
        print(f"    {'OK' if ok else 'FAILED'}: {msg}\n")
        (results["ok"] if ok else results["failed"]).append((label, msg))

        if not ok and not args.keep_going and not args.unattended:
            choice = ask("  continue with the next account? [Enter] yes, [q] stop: ")
            if choice == "q":
                print("  stopped.")
                break

    print("=" * 60)
    print(f"Logged in : {len(results['ok'])}")
    print(f"Failed    : {len(results['failed'])}")
    import collections
    by_reason = collections.defaultdict(list)
    for label, msg in results["failed"]:
        by_reason[msg].append(label)
    for reason, who in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
        print("")
        print(f"  {reason}  ({len(who)})")
        for label in who[:12]:
            print(f"     {label}")
        if len(who) > 12:
            print(f"     ... {len(who) - 12} more")
    print("\nPasswords were held in memory only; nothing was written.")
    return 0 if not results["failed"] else 2


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help=f"path to a local xlsx (default: {DEFAULT_SHEET})")
    ap.add_argument("--from-sheet", action="store_true",
                    help="read credentials from the Google Sheet API even if a "
                         "local xlsx exists (default when no xlsx is present)")
    ap.add_argument("--count", type=int, help="attempt at most this many")
    ap.add_argument("--include-disabled", action="store_true",
                    help="also attempt accounts already marked disabled")
    ap.add_argument("--skip", type=int, default=0,
                    help="skip the first N of the queue, so a known-bad "
                         "account is not re-attempted")
    ap.add_argument("--only", metavar="USERNAME", help="attempt a single account")
    ap.add_argument("--dry-run", action="store_true",
                    help="list who would be attempted, open nothing")
    ap.add_argument("--keep-going", action="store_true",
                    help="do not pause for confirmation after a failure")
    ap.add_argument("--unattended", action="store_true",
                    help="never prompt: skip any checkpoint/2FA and list "
                         "those accounts in the summary for a later --only run")
    ap.add_argument("--hand-off-2fa", action="store_true",
                    help="with --unattended, still stop on a 2FA prompt so you "
                         "can type the code, then keep going on your own")
    ap.add_argument("--batch", type=int, default=0, metavar="N",
                    help="pause after every N accounts (0 = no pausing)")
    ap.add_argument("--pause", type=float, default=15.0, metavar="MIN",
                    help="minutes to wait between batches (default 15)")
    args = ap.parse_args(argv)
    if args.batch < 0 or args.pause < 0:
        ap.error("--batch and --pause must be >= 0")
    if args.hand_off_2fa and not args.unattended:
        ap.error("--hand-off-2fa only applies with --unattended")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
