"""Comment on one post from several Brave profiles, without sharing it.

FacebookAutomation._auto_comment() already posts a comment, but both of its
call sites sit at the end of a share flow, so there was no way to comment on a
post without first sharing it. This script is that missing caller: open an
account's Brave profile, confirm the session is real, navigate to the post and
comment.

Nothing is typed that the caller did not pass: --text is required, and a
multi-line --text is handed to _auto_comment as-is, which picks one line at
random per account.

Why it runs one account at a time: Chromium's ProcessSingleton locks the
shared Brave "User Data" directory, the same constraint that makes
login_accounts.py sequential. Brave must not be running.

Usage:
    python scripts/comment_post.py URL --text "up" --count 3 --dry-run
    python scripts/comment_post.py URL --text "up" --count 3
    python scripts/comment_post.py URL --text "up" --only user@example.com
"""
import argparse
import asyncio
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))   # scripts/ importable

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import login_accounts as la        # has_session, SESSION_COOKIES, brave_running


async def comment_one(account: dict, post_url: str, text: str, log,
                      headless: bool = False) -> tuple[bool, str]:
    """Open this account's profile and comment on post_url.

    The session check is login_accounts.has_session(): c_user + xs present AND
    the browser sitting on the Facebook home page. Cookies alone call a gated
    account logged in, so a profile that cannot load its own feed is reported
    as such instead of being driven into a comment box that is not there.
    """
    from src.core.facebook_automation import FacebookAutomation, LOGIN_FLAGS
    from src.storage import config_manager as cfg

    profile_name = account["linked_profile"]
    brave_path = cfg.get_profile_path(profile_name)
    if not brave_path:
        return False, f"profile '{profile_name}' has no Brave path"

    auto = FacebookAutomation()
    auto.log = log
    try:
        await auto.start_browser(brave_path, headless=headless, flags=LOGIN_FLAGS)
        await auto.go_to_facebook()

        if not await la.has_session(auto):
            # Per the project's own note this verdict is wrong about 1 in 6;
            # it is reported, never acted on by disabling the account.
            return False, "not logged in (re-check with check_login_status.py)"

        ok = await auto._auto_comment(post_url, text)
        if not ok:
            return False, (getattr(auto, "last_comment_error", "")
                           or "comment failed")
        return True, "commented"
    except Exception as e:
        return False, f"error: {e}"
    finally:
        try:
            await auto.quit()
        except Exception:
            pass


async def run(args) -> int:
    from src.storage import database as db

    if la.brave_running():
        print("Brave is running. Close it first: it locks the profile root.")
        return 1

    accounts = [a for a in db.list_accounts()
                if a.get("linked_profile") and a.get("status") == "ok"]
    if args.only:
        accounts = [a for a in accounts if a["username"] == args.only]
    if args.count:
        accounts = accounts[:args.count]

    if not accounts:
        print("No matching accounts (need status 'ok' and a linked profile).")
        return 1

    lines = [ln.strip() for ln in args.text.strip().splitlines() if ln.strip()]
    print(f"Post    : {args.post_url}")
    print(f"Text    : {lines if len(lines) > 1 else args.text!r}")
    print(f"Accounts: {len(accounts)}")
    for a in accounts:
        print(f"   {a['username']}  ({a.get('facebook_name')})")

    if args.dry_run:
        print("\n--dry-run: no browser opened, nothing posted.")
        return 0

    results = {"ok": [], "failed": []}
    for i, a in enumerate(accounts, 1):
        label = f"{a['username']} ({a.get('facebook_name')})"
        print(f"\n[{i}/{len(accounts)}] {label}")

        def log(msg, _i=i):
            print(f"    {msg}")

        ok, msg = await comment_one(a, args.post_url, args.text, log,
                                    headless=args.headless)
        print(f"    {'OK' if ok else 'FAILED'}: {msg}")
        (results["ok"] if ok else results["failed"]).append((label, msg))

        if i < len(accounts):
            gap = random.uniform(args.gap_min, args.gap_max)
            print(f"    waiting {gap:.0f}s before the next account ...")
            await asyncio.sleep(gap)

    print(f"\nCommented: {len(results['ok'])}   Failed: {len(results['failed'])}")
    for label, msg in results["failed"]:
        print(f"   {label}: {msg}")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("post_url")
    ap.add_argument("--text", required=True,
                    help="comment text; multiple lines = one picked at random")
    ap.add_argument("--count", type=int, help="use at most this many accounts")
    ap.add_argument("--only", metavar="USERNAME", help="a single account")
    ap.add_argument("--headless", action="store_true",
                    help="no visible browser window")
    ap.add_argument("--gap-min", type=float, default=45.0,
                    help="min seconds between accounts (default 45)")
    ap.add_argument("--gap-max", type=float, default=120.0,
                    help="max seconds between accounts (default 120)")
    ap.add_argument("--dry-run", action="store_true",
                    help="show who would comment, open nothing")
    args = ap.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
