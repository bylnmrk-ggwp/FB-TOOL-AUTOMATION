"""Remove roster rows whose username is a phone number mangled by Excel.

A phone number typed into the spreadsheet is stored as a NUMBER, and an .xlsx
export renders it in scientific notation - "9.709293808E9". That reaches
Facebook as those literal characters and fails as an invalid identifier, so
every such row is a login attempt spent to no purpose, charged against an
account that was never really tried.

src/storage/roster_import.clean_username now expands that notation back to
plain digits on import, so new imports are clean. This repairs the rows a
past import already left behind.

Every mangled row on this roster turned out to be an exact DUPLICATE: the same
number is also present in plain-digit form (9283402278 alongside
9.283402278E9), because a later --sheet import added the correct version
without removing the broken one. So the safe repair is to DELETE the mangled
duplicate, never to rename it - a rename would collide with the good row.

A mangled row is only deleted when:
  * its cleaned form is a different, valid identifier, AND
  * a row with that cleaned username already exists, AND
  * the mangled row carries no work of its own - no linked_profile, no
    status, no status_reason. A row someone has invested in is reported and
    left for a human, never quietly removed.

Dry by default. Pass --apply to delete.

Usage:
    python scripts/clean_mangled_usernames.py            # show what would go
    python scripts/clean_mangled_usernames.py --apply    # delete them
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from src.storage import database as db  # noqa: E402
from src.storage.roster_import import clean_username  # noqa: E402

_SCI = re.compile(r"\d+(?:\.\d+)?[Ee][+-]?\d+")


def plan(conn) -> tuple[list, list]:
    """(deletable, kept_back) mangled rows.

    deletable: (mangled, cleaned) pairs safe to remove.
    kept_back: (mangled, reason) rows a human should look at instead.
    """
    existing = {r[0] for r in conn.execute("SELECT username FROM accounts")}
    rows = conn.execute(
        "SELECT username, linked_profile, status, status_reason FROM accounts")
    deletable, kept_back = [], []
    for username, profile, status, reason in rows:
        if not _SCI.fullmatch(username or ""):
            continue
        cleaned = clean_username(username)
        if cleaned == username:
            kept_back.append((username, "notation did not resolve to digits"))
        elif cleaned not in existing:
            kept_back.append(
                (username, f"no existing row for {cleaned!r} - this is the "
                           f"only copy; re-import to fix it in place"))
        elif (profile or "").strip() or (status or "").strip() or (reason or "").strip():
            kept_back.append(
                (username, "has local work (profile/status) - left for a human"))
        else:
            deletable.append((username, cleaned))
    return deletable, kept_back


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default is a dry run)")
    args = ap.parse_args(argv)

    conn = db._get_conn()
    deletable, kept_back = plan(conn)

    print(f"mangled duplicate rows to remove : {len(deletable)}")
    for mangled, cleaned in deletable:
        print(f"   {mangled:22} (good copy: {cleaned})")
    if kept_back:
        print(f"\nleft in place for review         : {len(kept_back)}")
        for mangled, why in kept_back:
            print(f"   {mangled:22} {why}")

    if not deletable:
        print("\nnothing to delete.")
        return 0
    if not args.apply:
        print("\n--dry-run: nothing deleted. Re-run with --apply to remove.")
        return 0

    removed = 0
    for mangled, _ in deletable:
        removed += conn.execute(
            "DELETE FROM accounts WHERE username = ?", (mangled,)).rowcount
    conn.commit()
    print(f"\ndeleted {removed} mangled duplicate row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
