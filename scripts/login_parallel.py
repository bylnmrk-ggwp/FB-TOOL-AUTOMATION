"""Log in several Brave profiles at once, safely, despite the shared-root lock.

Every provisioned profile lives under ONE Brave "User Data" root, and Chromium's
process singleton locks that root, so the normal login runs one profile at a
time. This runner sidesteps that: each worker copies an account's profile
directory into its OWN isolated user-data-dir (a separate root, hence a separate
singleton), logs in there headless, and - only on success - copies the updated
session back over the real profile. N workers therefore run genuinely in
parallel.

Safety:
  * The real profile is written back ONLY when login succeeded, and the write is
    staged (move aside, copy in, drop the old) so an interruption can be undone.
  * --backup-dir first copies every targeted profile aside, untouched.
  * A 2FA/checkpoint account cannot be solved headless, so its login is capped
    (--twofa-timeout, default 45s) instead of the core's 120s wait, and it is
    recorded as needing 2FA for a later visible run.

Status is saved to the database and the Google Sheet the moment each account
resolves, exactly like scripts/login_accounts.py, and already-'ok' accounts are
skipped, so this continues wherever a sequential run left off.

Usage:
    python scripts/login_parallel.py --limit 3 --backup-dir .parallel-backup
        # prove on 3 accounts, backing them up first
    python scripts/login_parallel.py --workers 5
        # all leftover (non-ok) accounts, 5 at a time
"""
import argparse
import asyncio
import os
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ importable

from patchright.async_api import async_playwright

from src.core.facebook_automation import (FacebookAutomation, CHROME_PATH,
                                           LOGIN_FLAGS)
from src.storage import config_manager as cfg
from src.storage import database as db

import login_accounts as la     # has_session, short_reason, is_infra_error, Live, ...


def _stage_copy_back(new_dir: str, real_dir: str) -> None:
    """Replace real_dir with new_dir, recoverably.

    Move the current profile aside, copy the new one into place, then drop the
    old. If the copy fails after the move, the old is restored, so the real
    profile is never left missing.
    """
    old = real_dir + ".old"
    if os.path.exists(old):
        shutil.rmtree(old, ignore_errors=True)
    os.rename(real_dir, old)
    try:
        shutil.copytree(new_dir, real_dir)
    except Exception:
        if not os.path.exists(real_dir) and os.path.exists(old):
            os.rename(old, real_dir)      # undo: put the original back
        raise
    shutil.rmtree(old, ignore_errors=True)


def _is_retryable(msg: str) -> bool:
    """True for a transient failure worth another immediate attempt.

    short_reason() tags exactly these with a trailing '- retry' (form not
    ready, browser error, timeout). Deterministic verdicts - wrong password,
    needs 2FA, bad username, disabled - are never retried.
    """
    return la.short_reason(msg).endswith("- retry")


def _has_cookie_store(path: Path) -> bool:
    return any((path / c).exists() for c in ("Network/Cookies", "Cookies"))


def _session_on_disk(profile_dir: Path) -> bool:
    """True only if c_user AND xs are written to the profile's cookie DB.

    A fresh Facebook login often issues a non-persistent (session-only) cookie
    that lives in memory and is never flushed to disk. has_session() sees it in
    the live context and reports success, but once the browser closes the disk
    profile has no session - so a copy-back would persist a logged-out profile.
    Checking the on-disk cookie names is what tells a durable login from that.
    """
    import sqlite3
    for c in ("Network/Cookies", "Cookies"):
        f = profile_dir / c
        if not f.exists():
            continue
        try:
            con = sqlite3.connect(f"file:{f}?mode=ro&immutable=1", uri=True)
            names = {r[0] for r in con.execute(
                "SELECT name FROM cookies WHERE host_key LIKE '%facebook%'")}
            con.close()
            return "c_user" in names and "xs" in names
        except Exception:
            return False
    return False


def _profile_damaged(path: str, backup: Path | None) -> bool:
    """True only if the profile lost something it had before the run.

    A freshly provisioned profile is an empty directory with no cookie store,
    so "no cookie DB" alone is not damage. Damage is: the directory is gone,
    or the backup had a cookie store and the live profile no longer does.
    """
    p = Path(path)
    if not p.is_dir():
        return True
    if backup is None or not backup.is_dir():
        return False                    # nothing to compare against
    return _has_cookie_store(backup) and not _has_cookie_store(p)


async def _attempt(pw, wid: int, account: dict, password: str,
                   workroot: Path, twofa_timeout: float, log) -> tuple[bool, str]:
    """Copy the profile into an isolated root, log in, copy back on success."""
    profile = account["linked_profile"]
    src = cfg.get_profile_path(profile)
    if not src or not os.path.isdir(src):
        return False, f"profile '{profile}' has no directory"

    iso = workroot / f"w{wid}"
    if iso.exists():
        shutil.rmtree(iso, ignore_errors=True)
    dst = iso / profile
    shutil.copytree(src, dst)                     # session in (~20 MiB, ~0.4s)

    ctx = None
    try:
        # A real window, minimised - not Chromium's headless mode. Headless
        # reports "HeadlessChrome/<version>" in the User-Agent, which is what
        # Facebook answers with a captcha on the login form. See
        # FacebookAutomation.start_browser for the measurements.
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(iso), executable_path=CHROME_PATH, headless=False,
            args=[f"--profile-directory={profile}", "--window-position=50,50",
                  *LOGIN_FLAGS])
        auto = FacebookAutomation(log_callback=log)
        auto.context = ctx
        auto.page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        # _hidden, not just minimised: it is what tells _back_to_tile to put
        # the window down again after a challenge raises it.
        auto._hidden = True
        await auto.hide_window()
        await auto.go_to_facebook()

        if await la.has_session(auto):
            return True, "already logged in - skipped"

        try:
            ok, msg = await asyncio.wait_for(
                auto.login_with_credentials(account["username"], password),
                timeout=twofa_timeout)
        except asyncio.TimeoutError:
            # The only thing that takes this long is the core's 2FA wait loop.
            return False, la.NEEDS_2FA

        if ok and not await la.has_session(auto):
            ok, msg = False, (la.NO_HOME_PAGE if la.auto_on_gate(auto) else
                              "reported success but no session cookies "
                              "(c_user/xs missing)")
        if not ok:
            # Normalise Facebook's raw copy the same way the sequential run
            # does, so the sheet shows "wrong password" / "bad username" / etc.
            try:
                url = auto.page.url
            except Exception:
                url = ""
            msg = la.classify(url, msg) or msg
        return ok, msg
    finally:
        # Close the browser so the isolated dir is unlocked; the caller copies
        # the session back (on success) and removes the isolated dir.
        if ctx is not None:
            try:
                await ctx.close()
            except Exception:
                pass


async def _worker(wid: int, q: asyncio.Queue, pw, creds: dict, workroot: Path,
                  twofa_timeout: float, retries: int, results: list,
                  lock: asyncio.Lock):
    while True:
        try:
            account = q.get_nowait()
        except asyncio.QueueEmpty:
            return
        label = account.get("facebook_name") or account["username"]
        started = time.strftime("%H:%M:%S")
        print(f"[w{wid} {started}] start {label}")

        def log(m, _l=label, _w=wid):
            print(f"    [w{_w}] {m}")

        profile = account["linked_profile"]
        src = cfg.get_profile_path(profile)
        iso = workroot / f"w{wid}"
        dst = iso / profile
        pw_str = creds[account["username"].lower()]
        try:
            # Retry a transient failure (form not ready, browser error, timeout)
            # on the same account before moving on; each attempt re-copies a
            # fresh profile, so a retry starts clean.
            for attempt in range(1, retries + 2):
                ok, msg = await _attempt(pw, wid, account, pw_str,
                                         workroot, twofa_timeout, log)
                if ok or not _is_retryable(msg) or attempt > retries:
                    break           # success, deterministic, or no retries left
                print(f"    [w{wid}] retry {attempt}/{retries} ({la.short_reason(msg)})")
            # A login that Facebook only granted a non-persistent session for
            # leaves nothing on disk, so a copy-back would save a logged-out
            # profile and mark it ok. Require the session on disk before
            # trusting the success.
            if ok and os.path.isdir(dst) and not _session_on_disk(dst):
                ok, msg = False, ("session did not persist to disk "
                                  "(Facebook issued a non-persistent session)")
            # Copy the updated session back only when login actually succeeded.
            if ok and os.path.isdir(dst) and src:
                _stage_copy_back(str(dst), src)
        except Exception as e:
            ok, msg = False, f"error: {e}"
        finally:
            shutil.rmtree(iso, ignore_errors=True)

        # Persist status (same rules as the sequential run).
        if ok:
            la._mark_ok(account)
        elif msg != la.DISABLED and not la.is_infra_error(msg):
            db.set_account_status(account["username"], "", la.short_reason(msg))
        elif msg == la.DISABLED:
            db.set_account_status(account["username"], "disabled")

        print(f"[w{wid} {time.strftime('%H:%M:%S')}] {'OK' if ok else 'FAIL'} "
              f"{label}: {msg}")
        results.append((label, ok, msg))
        q.task_done()


async def run(args) -> int:
    accounts = [a for a in db.list_accounts(include_disabled=args.include_disabled)
                if a.get("linked_profile")]
    if not args.relogin:
        accounts = [a for a in accounts if a.get("status") != "ok"]
    if args.untried or args.plain_only:
        # --untried: accounts with no verdict yet (blank reason) or a transient
        # one ("... - retry"). Deterministic failures - needs 2FA, wrong
        # password, bad username - are skipped: re-running cannot change them.
        # --plain-only: stricter - blank reason only, i.e. the sheet shows
        # exactly NOT LOGGED IN with no "/ reason" suffix at all.
        def _wanted(a):
            r = (a.get("status_reason") or "").strip()
            return r == "" or (args.untried and r.endswith("- retry"))
        skipped = [a for a in accounts if not _wanted(a)]
        accounts = [a for a in accounts if _wanted(a)]
        if skipped:
            what = "any recorded reason" if args.plain_only else                    "a known failure (2FA / wrong password / bad username)"
            print(f"Skipping {len(skipped)} account(s) with {what}")

    creds = la.read_credentials_from_sheet()
    todo = [a for a in accounts if a["username"].lower() in creds]
    if args.limit is not None:
        todo = todo[:args.limit]
    if not todo:
        print("Nothing to do (no non-ok accounts with a password).")
        return 0

    print(f"Parallel login: {len(todo)} account(s), {args.workers} worker(s).")

    if args.backup_dir:
        bdir = Path(args.backup_dir)
        bdir.mkdir(parents=True, exist_ok=True)
        for a in todo:
            src = cfg.get_profile_path(a["linked_profile"])
            if src and os.path.isdir(src):
                dest = bdir / a["linked_profile"]
                if not dest.exists():
                    shutil.copytree(src, dest)
        print(f"Backed up {len(todo)} profile(s) to {bdir}")

    workroot = Path(args.work_dir)
    workroot.mkdir(parents=True, exist_ok=True)


    results: list = []
    q: asyncio.Queue = asyncio.Queue()
    for a in todo:
        q.put_nowait(a)

    t0 = time.time()
    pw = await async_playwright().start()
    try:
        lock = asyncio.Lock()
        await asyncio.gather(*[
            _worker(i + 1, q, pw, creds, workroot, args.twofa_timeout,
                    args.retries, results, lock)
            for i in range(min(args.workers, len(todo)))])
    finally:
        await pw.stop()
        shutil.rmtree(workroot, ignore_errors=True)
    elapsed = time.time() - t0

    ok = sum(1 for _, k, _ in results if k)
    print("=" * 60)
    print(f"Attempted : {len(results)}   Logged in : {ok}   "
          f"Failed : {len(results) - ok}")
    print(f"Wall clock: {elapsed:.0f}s  (~{elapsed / max(1, len(results)):.0f}s/account "
          f"across {args.workers} workers)")

    if args.backup_dir:
        bdir = Path(args.backup_dir)
        bad = [a["linked_profile"] for a in todo
               if _profile_damaged(cfg.get_profile_path(a["linked_profile"]) or "",
                                   bdir / a["linked_profile"])]
        if bad:
            print(f"INTEGRITY WARNING: {len(bad)} profile(s) lost their cookie "
                  f"store: {bad}")
            print(f"Restore from {args.backup_dir}.")
        else:
            print(f"Integrity: none of the {len(todo)} targeted profiles lost "
                  f"anything it had before the run.")

    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5, help="concurrent logins")
    ap.add_argument("--limit", type=int, help="attempt at most this many")
    ap.add_argument("--relogin", action="store_true",
                    help="also attempt accounts already marked logged in")
    ap.add_argument("--untried", action="store_true",
                    help="only accounts with no verdict yet (plain NOT LOGGED IN) "
                         "or a transient '- retry' one; skip known 2FA / wrong "
                         "password / bad username")
    ap.add_argument("--plain-only", action="store_true",
                    help="only accounts whose STATUS is exactly NOT LOGGED IN "
                         "(no '/ reason' suffix at all, transient retries "
                         "included in the skip)")
    ap.add_argument("--include-disabled", action="store_true")
    ap.add_argument("--no-live-sheet", action="store_true")
    ap.add_argument("--twofa-timeout", type=float, default=45.0,
                    help="seconds to allow a login before treating it as 2FA")
    ap.add_argument("--retries", type=int, default=2,
                    help="retry a transient failure (form not ready / browser "
                         "error / timeout) this many times before moving on")
    ap.add_argument("--backup-dir", help="copy every targeted profile here first")
    ap.add_argument("--work-dir",
                    default=str(ROOT / ".parallel-work"),
                    help="scratch area for isolated user-data-dirs")
    args = ap.parse_args(argv)
    if args.workers < 1:
        ap.error("--workers must be >= 1")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
