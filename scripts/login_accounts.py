"""Assisted Facebook login for provisioned Brave profiles.

Walks the roster accounts that have a linked Brave profile, opens each profile
in a VISIBLE browser, types the credentials, and hands control to you whenever
Facebook raises a checkpoint or 2FA challenge. Nothing is retried unattended.

Passwords are read from the local workbook at run time and never written
anywhere: not to the database, not to the config, not to the log.

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
    python scripts/login_accounts.py --challenges --headless
        # ONLY the accounts a previous run left waiting on a 2FA code or a
        # captcha, back to back, each raising its window when it needs you
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

DEFAULT_WORKBOOK = "FB ACCOUNTS.xlsx"


def read_credentials(xlsx: Path) -> dict:
    """username -> password, straight from the workbook.

    Held in memory for the length of the run only. Column letters are resolved
    from the header labels so a reordered workbook cannot pair the wrong password
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


def short_reason(msg: str) -> str:
    """A brief detail for a failed login.

    Technical/transient failures (a headless browser that closed, a login form
    that did not render) collapse to short tags rather than dumping a raw
    Playwright stack line into a status field. These stay non-'ok' in the database,
    so the next pass retries them.
    """
    if msg == DISABLED:
        return ""                       # the DISABLED status already says it
    if msg == NEEDS_2FA:
        return "needs 2FA"
    if msg == NEEDS_CAPTCHA:
        return "needs captcha"
    if msg == NEEDS_EMAIL_CONFIRM:
        return "needs email confirmation"
    if msg == NO_HOME_PAGE:
        return "no home page"
    if msg == BAD_PASSWORD:
        return "wrong password"
    if msg == BAD_IDENTIFIER:
        return "bad username"
    m = (msg or "").lower()
    if "checkpoint" in m:
        return "checkpoint"
    if ("launch" in m or "browser has been closed" in m
            or "target page" in m or "context or browser" in m):
        return "browser error - retry"
    if "not found" in m or "no session cookies" in m:
        return "login form not ready - retry"
    if "timeout" in m or "timed out" in m:
        return "timeout - retry"
    if m.startswith("error:"):
        return "error - retry"
    return (msg or "").strip()[:40]


# Outcomes worth telling apart, because the follow-up action differs:
# a disabled account is dead, a wrong password is a workbook fix, and a
# 2FA prompt means the credentials were accepted and only a code is missing.
DISABLED = "ACCOUNT DISABLED by Facebook - no login possible"
NEEDS_2FA = "credentials accepted, needs a 2FA code"
NEEDS_CAPTCHA = "credentials accepted, a captcha has to be solved by hand"
NEEDS_EMAIL_CONFIRM = "credentials accepted, Facebook wants the email confirmed first"
NO_HOME_PAGE = "signed in but Facebook never let the account reach its home page"
BAD_PASSWORD = "wrong password in the workbook"
BAD_IDENTIFIER = "username is not a valid Facebook login"


# The verdicts a person can personally clear, as short_reason() writes them
# into accounts.status_reason. Derived rather than typed out: if the wording
# of a reason ever changes, the queue follows it instead of quietly emptying.
def challenge_reasons() -> set[str]:
    return {short_reason(NEEDS_2FA).lower(),
            short_reason(NEEDS_CAPTCHA).lower()}


def challenge_queue(accounts: list[dict]) -> list[dict]:
    """The accounts an earlier run left stuck on a challenge a person can clear.

    A 2FA prompt and a captcha are the only two verdicts where the account is
    fine, the password is right, and the single missing thing is a human -
    Facebook has already accepted the credentials in both. Everything else in
    a run's summary is either self-clearing (a timeout, a browser error) or
    not fixable at the keyboard (a disabled account, a wrong password), so
    walking the whole roster to reach the handful that need a person costs a
    login attempt per account for nothing. Those attempts are not free: they
    are exactly the repeated failed logins that make Facebook gate an account
    harder.

    The queue is read from accounts.status_reason, which the previous run
    already wrote. Nothing new is stored.
    """
    wanted = challenge_reasons()
    return [a for a in accounts
            if (a.get("status_reason") or "").strip().lower() in wanted]


class Live:
    """Pushes each account's status to the Google Sheet as the run works it.

    A thin shell over src/storage/sheet_status.SheetWriter, which resolves
    the sheet once and holds the row map, so the run costs one write per
    account rather than five. Best-effort by design: a sheet write must
    never abort a login run, so a writer that could not start leaves every
    method a no-op and the run goes on.
    """

    def __init__(self, enabled: bool):
        self.on = False
        self.rows = 0
        self.error = "disabled" if not enabled else ""
        if not enabled:
            return
        from src.storage import sheet_status
        self.sheet = sheet_status
        self.writer = sheet_status.SheetWriter()
        self.on = self.writer.on
        self.rows = len(getattr(self.writer, "_rows", {}) or {})
        self.error = self.writer.error
        if not self.on:
            print(f"  (live sheet updates off: {self.error})")

    def mark_in_progress(self, username: str):
        if self.on:
            self.writer.mark_in_progress(username)

    def clear(self, username: str):
        """Revert a row to plain NOT LOGGED IN (e.g. an aborted attempt)."""
        if self.on:
            self.writer.write(username, self.sheet.NOT_LOGGED_IN)

    def mark_result(self, username: str, ok: bool, msg: str):
        if not self.on:
            return
        if ok:
            text = self.sheet.LOGGED_IN
        elif msg == DISABLED:
            text = self.sheet.DISABLED
        else:
            reason = short_reason(msg)
            text = (f"{self.sheet.NOT_LOGGED_IN} / {reason.upper()}"
                    if reason else self.sheet.NOT_LOGGED_IN)
        self.writer.write(username, text)


def is_infra_error(msg: str) -> bool:
    """True for a browser-launch/lock failure, not a Facebook login verdict.

    Once the shared Brave User Data directory is locked (an orphaned brave.exe
    holding Chromium's process singleton), every launch_persistent_context
    fails the same way. That is infrastructure, not the account - the run must
    stop rather than march the rest of the queue into false failures.
    """
    m = (msg or "").lower()
    return any(k in m for k in (
        "launch_persistent", "browsertype", "browser has been closed",
        "target page, context or browser", "failed to load login page"))


def brave_running() -> bool:
    """True if any brave.exe is alive (it would hold the profile lock)."""
    try:
        import psutil
        return any((p.info.get("name") or "").lower() == "brave.exe"
                   for p in psutil.process_iter(["name"]))
    except Exception:
        return False        # cannot tell -> do not block the run


def classify(url: str, msg: str) -> str | None:
    """Name the failure from the final URL and Facebook's own error text."""
    u = (url or "").lower()
    m = (msg or "").lower()
    if "checkpoint/disabled" in u or "account has been disabled" in m:
        return DISABLED
    # The message says what was ON the page; the URL only says where the page
    # lives. Facebook serves its "I am not a robot" box ON the
    # two_step_verification path, so keying on the URL first reported every
    # captcha as a missing 2FA code - and sent the operator looking for an
    # authenticator app for an account that only needed a puzzle answered.
    # The page's own verdict wins.
    if "captcha" in m:
        return NEEDS_CAPTCHA
    if "two_step_verification" in u or "twofactor" in u:
        return NEEDS_2FA
    if "confirmemail" in u:
        return NEEDS_EMAIL_CONFIRM
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


def auto_on_gate(auto) -> bool:
    """True when the browser is parked on a Facebook gate, not the home page.

    Tells "the login produced no session at all" apart from "the login
    worked but Facebook is holding the account at a checkpoint / email
    confirmation", which are different problems for whoever reads the roster.
    """
    try:
        return auto._is_gated_url(auto.page.url)
    except Exception:
        return False


async def has_session(auto) -> bool:
    """True only if this account can actually use Facebook right now.

    Two things have to hold, and each catches what the other misses:

    c_user (the account id) and xs (the session token) must exist - a real
    test run reported "Login successful" while the profile ended up holding
    only datr/fr/sb/wd, i.e. device identifiers and no session at all.

    And the browser must be sitting on the Facebook HOME page - Facebook
    issues both cookies before a checkpoint or an email-confirmation gate,
    so cookies alone marked gated accounts 'ok' and the roster said LOGGED
    IN for accounts that could not load their own feed.
    """
    try:
        cookies = await auto.context.cookies()
    except Exception:
        return False
    names = {c.get("name") for c in cookies
             if "facebook" in (c.get("domain") or "")}
    if not all(n in names for n in SESSION_COOKIES):
        return False
    try:
        return auto._is_home_url(auto.page.url)
    except Exception:
        return False


def _mark_ok(account: dict):
    """Clear any earlier 'disabled' mark: this account just proved it works."""
    from src.storage import database as db
    db.set_account_status(account["username"], "ok")


async def login_one(account: dict, password: str, log,
                    unattended: bool = False,
                    hand_off_2fa: bool = False,
                    headless: bool = False) -> tuple[bool, str]:
    """Open this account's Brave profile and log it in.

    Assisted by default: a challenge waits for the operator. With
    `unattended` nothing ever waits - a challenge is recorded and skipped, so
    the run finishes on its own and the summary says who still needs a hand.
    With `hand_off_2fa`, an unattended run still stops on the challenges an
    operator can actually clear - a 2FA prompt, where they hold the code, and
    a captcha, where they can answer the puzzle - so they settle it in the
    browser and the run continues on its own.
    With `headless`, the browser window is minimised rather than absent, so a
    hand-off can still raise it; the run is otherwise unattended.
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
        # Visible by default so a checkpoint can be cleared by hand; headless
        # only when the caller runs unattended in the background.
        await auto.start_browser(brave_path, headless=headless,
                                 flags=LOGIN_FLAGS)
        await auto.go_to_facebook()

        if await has_session(auto):
            _mark_ok(account)
            return True, "already logged in - skipped"

        ok, msg = await auto.login_with_credentials(account["username"], password)

        # Trust cookies over the DOM heuristic, whichever way they disagree.
        if ok and not await has_session(auto):
            ok, msg = False, (NO_HOME_PAGE if auto_on_gate(auto) else
                              "reported success but no session cookies "
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
            if reason in (NEEDS_2FA, NEEDS_CAPTCHA) and hand_off_2fa:
                label = account.get("facebook_name") or account["username"]
                # The window is minimised, so "the open Brave window" is not
                # on screen until this puts it there.
                try:
                    await auto._focus_for_human()
                except Exception as e:  # noqa: BLE001 - never lose the login
                    print(f"    (could not raise the window: "
                          f"{type(e).__name__}: {e})")
                print("\n" + "!" * 60)
                if reason == NEEDS_CAPTCHA:
                    print(f"  CAPTCHA NEEDED for {label}")
                    print(f"  Solve the picture challenge in the Brave window "
                          f"for profile '{account['linked_profile']}'.")
                    prompt = ("    [Enter] I solved it, re-check  /  "
                              "[s] skip this account: ")
                else:
                    print(f"  2FA NEEDED for {label}")
                    print(f"  Enter the code in the open Brave window for "
                          f"profile '{account['linked_profile']}'.")
                    prompt = ("    [Enter] I entered the code, re-check  /  "
                              "[s] skip this account: ")
                print("!" * 60)
                choice = ask(prompt)
                try:
                    await auto._back_to_tile()
                except Exception:
                    pass
                if choice == "s":
                    return False, reason
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

    # Credential source: the database, which the roster import fills and which
    # is the roster now. --workbook still reads an xlsx directly, for a machine
    # whose database has not been imported yet.
    xlsx = Path(args.workbook) if args.workbook else None

    # Disabled accounts are excluded: Facebook says the decision cannot be
    # appealed, so re-attempting them only adds failed logins.
    accounts = [a for a in db.list_accounts(include_disabled=args.include_disabled)
                if a.get("linked_profile")]
    # list_accounts() is ordered by sheet_no, so a floor on that number is
    # "start at this roster row and keep going" - the same row the operator
    # reads off the sheet.
    if args.from_no is not None:
        accounts = [a for a in accounts
                    if a.get("sheet_no") is not None
                    and a["sheet_no"] >= args.from_no]
    if args.only:
        wanted = {u.strip().lower() for u in args.only if u.strip()}
        accounts = [a for a in accounts
                    if a["username"].lower() in wanted]

    if args.challenges:
        # One sitting, only the accounts that need a person. See
        # challenge_queue for why this is not the same as re-running the
        # roster and waiting for the blocked ones to come round again.
        before = len(accounts)
        accounts = challenge_queue(accounts)
        print(f"Challenge queue: {len(accounts)} of {before} account(s) are "
              f"waiting on a person ({', '.join(sorted(challenge_reasons()))})")
        if not accounts:
            print("Nothing is blocked on a challenge - run without "
                  "--challenges to attempt the roster.")
            return 0

    # Accounts already marked logged in (status 'ok') are skipped up front so a
    # re-run does not reopen a browser for them - the status the previous run
    # committed is trusted. --relogin (or --only) forces them back in.
    if not args.relogin and not args.only:
        already = [a for a in accounts if a.get("status") == "ok"]
        if already:
            print(f"Skipping already logged in (status=ok): {len(already)}  "
                  f"(--relogin to include them)")
        accounts = [a for a in accounts if a.get("status") != "ok"]

    if not accounts:
        print("No accounts to attempt (all linked accounts are already "
              "logged in; use --relogin to force).")
        return 0

    if xlsx is not None:
        try:
            creds = read_credentials(xlsx)
        except Exception as e:
            print(f"Could not read credentials from {xlsx}: {e}")
            return 1
        source = xlsx.name
    else:
        # credentials_for_profile() is the only way a password leaves the
        # database: list_accounts() omits the column on purpose, so that no
        # roster view or log line can carry one. Asked per account, as there.
        creds = {}
        for a in accounts:
            got = db.credentials_for_profile(a.get("linked_profile") or "")
            if got:
                creds[a["username"].lower()] = got[1]
        source = "database"
    print(f"Credential source             : {source}")
    missing = [a["username"] for a in accounts
               if a["username"].lower() not in creds]

    print(f"Accounts with a Brave profile : {len(accounts)}")
    print(f"Passwords found               : {len(accounts) - len(missing)}")
    if missing:
        print(f"No password                   : {len(missing)}")
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

    # Preflight: any running brave.exe holds Chromium's process-singleton lock
    # on the shared User Data directory, so every launch_persistent_context
    # would fail. Refuse to start rather than mark the whole queue as failed.
    if brave_running():
        print("Brave is running and locks the shared profile directory, so no "
              "login can launch.\nClose every Brave window, or run:\n"
              "    taskkill /F /IM brave.exe /T\nthen start this again.")
        return 1

    print("\nOne at a time; Brave's profile lock allows no parallelism.")
    if args.unattended:
        print("Unattended: challenges are skipped and listed at the end.\n")
    else:
        print("A visible window opens per account. Solve any checkpoint in it.\n")

    aborted = False
    live = Live(not args.no_live_sheet)
    if live.on:
        print(f"Live sheet updates: {live.rows} row(s) matched.\n")

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
        live.mark_in_progress(a["username"])

        def log(msg, _i=i):
            print(f"    {msg}")

        ok, msg = await login_one(a, creds[a["username"].lower()], log,
                                  unattended=args.unattended,
                                  hand_off_2fa=args.hand_off_2fa,
                                  headless=args.headless)
        # A browser-launch failure means the shared profile is locked; every
        # later account would fail identically. Stop now, and do NOT record it
        # as an account verdict - the account was never really attempted.
        if not ok and is_infra_error(msg):
            live.clear(a["username"])
            print(f"    ABORTED: {msg}")
            print("\nThe shared Brave profile is locked (an orphaned brave.exe "
                  "holds it).\nClose Brave / run: taskkill /F /IM brave.exe /T, "
                  "then start again.\nAccounts already done keep their status; "
                  "the rest are untouched.")
            aborted = True
            break

        # Persist why it failed so the roster and the sheet can show it. A
        # success already cleared the status inside login_one via _mark_ok,
        # and DISABLED was recorded there too; everything else lands here.
        if not ok and msg != DISABLED:
            db.set_account_status(a["username"], "", short_reason(msg))
        live.mark_result(a["username"], ok, msg)
        print(f"    {'OK' if ok else 'FAILED'}: {msg}\n")
        (results["ok"] if ok else results["failed"]).append((label, msg))

        if not ok and not args.keep_going and not args.unattended:
            choice = ask("  continue with the next account? [Enter] yes, [q] stop: ")
            if choice == "q":
                print("  stopped.")
                break

    print("=" * 60)
    if aborted:
        print("RUN ABORTED early on a browser-lock error - see above.")
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

    # Final reconcile: live cell writes are best-effort, so a dropped one
    # could leave the sheet a step behind the database. Rewrite every STATUS
    # cell from the database once at the end so the sheet always matches
    # when a run ends.
    if live.on:
        try:
            import sync_sheet_status as sync
            sync.main([])
            print("Sheet reconciled with the database.")
        except Exception as e:
            print(f"(sheet reconcile skipped: {e})")

    if aborted:
        return 3
    return 0 if not results["failed"] else 2


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workbook",
                    help=f"path to the credential xlsx (default: {DEFAULT_WORKBOOK})")
    ap.add_argument("--no-live-sheet", action="store_true",
                    help="do not update the Google Sheet STATUS column live "
                         "as the run works each account (on by default)")
    ap.add_argument("--headless", action="store_true",
                    help="run with no visible browser window (background run); "
                         "implies --unattended and cannot hand off a 2FA prompt")
    ap.add_argument("--from-no", type=int, default=None, metavar="N",
                    help="only accounts whose roster number is N or higher "
                         "(the sheet's own row number)")
    ap.add_argument("--count", type=int, help="attempt at most this many")
    ap.add_argument("--include-disabled", action="store_true",
                    help="also attempt accounts already marked disabled")
    ap.add_argument("--skip", type=int, default=0,
                    help="skip the first N of the queue, so a known-bad "
                         "account is not re-attempted")
    ap.add_argument("--only", nargs="*", metavar="USERNAME", default=None,
                    help="attempt only these accounts, by username")
    ap.add_argument("--challenges", action="store_true",
                    help="only the accounts an earlier run left waiting on a "
                         "2FA code or a captcha; implies --hand-off-2fa")
    ap.add_argument("--relogin", action="store_true",
                    help="also attempt accounts already marked logged in "
                         "(by default status=ok accounts are skipped)")
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
    if args.challenges:
        # The queue exists so a person can clear these, so the hand-off is
        # the whole point of the mode rather than an extra flag to remember.
        args.hand_off_2fa = True
        args.unattended = True
    if args.headless:
        # --headless used to mean "no window at all", which is why it refused
        # to hand a challenge over. It now means a real window that is
        # minimised, and a challenge raises it (see
        # FacebookAutomation._focus_for_human), so the hand-off works here
        # too. The run stays unattended: it stops only for the challenges an
        # operator can actually clear.
        args.unattended = True
    if args.hand_off_2fa and not args.unattended:
        ap.error("--hand-off-2fa only applies with --unattended")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
