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

from playwright.async_api import async_playwright

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


def _profile_intact(path: str) -> bool:
    """A rough integrity check: the profile dir exists and carries a cookie DB."""
    p = Path(path)
    if not p.is_dir():
        return False
    return any((p / c).exists() for c in ("Network/Cookies", "Cookies"))


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
        ctx = await pw.chromium.launch_persistent_context(
            user_data_dir=str(iso), executable_path=CHROME_PATH, headless=True,
            args=[f"--profile-directory={profile}", *LOGIN_FLAGS])
        auto = FacebookAutomation(log_callback=log)
        auto.context = ctx
        auto.page = ctx.pages[0] if ctx.pages else await ctx.new_page()
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
            ok, msg = False, ("reported success but no session cookies "
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
                  twofa_timeout: float, live, results: list, lock: asyncio.Lock):
    while True:
        try:
            account = q.get_nowait()
        except asyncio.QueueEmpty:
            return
        label = account.get("facebook_name") or account["username"]
        started = time.strftime("%H:%M:%S")
        print(f"[w{wid} {started}] start {label}")
        live.mark_in_progress(account["username"])

        def log(m, _l=label, _w=wid):
            print(f"    [w{_w}] {m}")

        profile = account["linked_profile"]
        src = cfg.get_profile_path(profile)
        iso = workroot / f"w{wid}"
        dst = iso / profile
        try:
            ok, msg = await _attempt(pw, wid, account, creds[account["username"].lower()],
                                     workroot, twofa_timeout, log)
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
        live.mark_result(account["username"], ok, msg)

        print(f"[w{wid} {time.strftime('%H:%M:%S')}] {'OK' if ok else 'FAIL'} "
              f"{label}: {msg}")
        results.append((label, ok, msg))
        q.task_done()


async def run(args) -> int:
    accounts = [a for a in db.list_accounts(include_disabled=args.include_disabled)
                if a.get("linked_profile")]
    if not args.relogin:
        accounts = [a for a in accounts if a.get("status") != "ok"]

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

    live = la.Live(not args.no_live_sheet)
    if live.on:
        print(f"Live sheet updates: {live.rows} row(s) matched.")

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
                    live, results, lock)
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
        bad = [a["linked_profile"] for a in todo
               if not _profile_intact(cfg.get_profile_path(a["linked_profile"]) or "")]
        if bad:
            print(f"INTEGRITY WARNING: {len(bad)} profile(s) look damaged: {bad}")
            print(f"Restore from {args.backup_dir} if needed.")
        else:
            print(f"Integrity: all {len(todo)} targeted profiles still carry a "
                  f"cookie store.")

    if live.on:
        try:
            import sync_sheet_status as sync
            sync.main([])
            print("Sheet reconciled with the database.")
        except Exception as e:
            print(f"(sheet reconcile skipped: {e})")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=5, help="concurrent logins")
    ap.add_argument("--limit", type=int, help="attempt at most this many")
    ap.add_argument("--relogin", action="store_true",
                    help="also attempt accounts already marked logged in")
    ap.add_argument("--include-disabled", action="store_true")
    ap.add_argument("--no-live-sheet", action="store_true")
    ap.add_argument("--twofa-timeout", type=float, default=45.0,
                    help="seconds to allow a login before treating it as 2FA")
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
