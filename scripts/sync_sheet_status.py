"""Mirror each account's login status into the Google Sheet as a red/green pill.

Reads the roster sheet's USERNAME column, matches each row to the local
account database, and writes the STATUS column plus a cell background:

    DISABLED        red    - Facebook disabled the account (db status)
    NOT LOGGED IN   red    - imported, no confirmed session yet
    LOGGED IN       green  - db status 'ok' (a login run or login check saw
                             the profile reach its Facebook home page)
    (blank)         none   - the sheet row is not in the local database

USERNAME and STATUS are located by their header labels on every run, never
by a fixed column letter: a fixed index once pointed STATUS writes at the
NUMBER column after the sheet gained a column. If no STATUS header exists,
one is added in the first empty column. No other column is ever written.
Credentials never leave this machine except the username, which is only
used to look the row up.

Auth: a Google service-account key, path from SHEETS_SERVICE_ACCOUNT (env) or
.secrets/sheets-service-account.json. The sheet must be shared to the service
account's email as Editor, with the Google Sheets API enabled on its project.

Usage:
    python scripts/sync_sheet_status.py
    python scripts/sync_sheet_status.py --dry-run     # print the plan, write nothing
    python scripts/sync_sheet_status.py --sheet-id <id> --tab Sheet1
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.storage import sheets_api as api
from src.storage import database as db

DEFAULT_SHEET_ID = api.DEFAULT_SHEET_ID
DEFAULT_TAB = api.DEFAULT_TAB
DEFAULT_KEY = api.DEFAULT_KEY


# The pill text, colours and single-row writes live in src/storage, because
# the app writes them too (a watch that finds a disabled account pushes the
# verdict straight to the sheet). Re-exported here under the names this
# script and the login scripts already use.
from src.storage.sheet_status import (          # noqa: E402
    col_letter, resolve_columns, status_for, fill as _fill,
    resolve_gid, build_row_index, write_status, push_account_status,
    RED, GREEN, AMBER, WHITE_TEXT, NO_FILL, DARK_TEXT,
    DISABLED, NOT_LOGGED_IN, LOGGED_IN, IN_PROGRESS,
)


def main(argv) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet-id", default=os.environ.get("SHEETS_SHEET_ID",
                                                         DEFAULT_SHEET_ID))
    ap.add_argument("--tab", default=DEFAULT_TAB)
    ap.add_argument("--key", default=os.environ.get("SHEETS_SERVICE_ACCOUNT",
                                                    str(DEFAULT_KEY)))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    key_path = Path(args.key)
    if not key_path.exists():
        print(f"Service-account key not found: {key_path}")
        return 1

    token = api.token(key_path)

    # Resolve the tab's numeric id (needed for formatting requests).
    meta = api.call(token, args.sheet_id,
                "?fields=sheets(properties(title,sheetId))")
    gid = next((s["properties"]["sheetId"] for s in meta["sheets"]
                if s["properties"]["title"] == args.tab), None)
    if gid is None:
        print(f"Tab not found: {args.tab}")
        return 1

    cols = resolve_columns(token, args.sheet_id, args.tab)
    status_col = cols["status"]
    sc = col_letter(status_col)
    print(f"USERNAME in column {col_letter(cols['username'])}, "
          f"STATUS in column {sc}")

    # Read the username column; its length fixes the data-row range.
    uc = col_letter(cols["username"])
    rng = urllib.parse.quote(f"{args.tab}!{uc}2:{uc}")
    got = api.call(token, args.sheet_id, f"/values/{rng}").get("values", [])
    usernames = [(row[0].strip() if row else "") for row in got]
    n = len(usernames)
    if n == 0:
        print("No usernames in the sheet; nothing to do.")
        return 0

    accounts = {a["username"].strip().lower(): a for a in db.list_accounts()}
    statuses = [status_for(accounts.get(u.lower()) if u else None)
                for u in usernames]

    from collections import Counter
    tally = Counter(s or "(blank)" for s in statuses)
    print(f"Sheet rows: {n}   " + "   ".join(f"{k}: {v}" for k, v in tally.items()))

    if args.dry_run:
        print("--dry-run: nothing written.")
        return 0

    # 1. Write the STATUS column values (header + one cell per data row).
    values = [["STATUS"]] + [[s] for s in statuses]
    api.update_values(token, args.sheet_id, f"{args.tab}!{sc}1:{sc}{n + 1}",
                      values)

    # 2. Colour each STATUS cell. Contiguous rows of the same status collapse
    #    into one repeatCell request so the batch stays small.
    requests = []

    def push(row_start, row_end, status):
        bg, text = _fill(status)
        requests.append({"repeatCell": {
            "range": {"sheetId": gid, "startRowIndex": row_start,
                      "endRowIndex": row_end,
                      "startColumnIndex": status_col,
                      "endColumnIndex": status_col + 1},
            "cell": {"userEnteredFormat": {
                "backgroundColor": bg,
                "horizontalAlignment": "CENTER",
                "textFormat": text}},
            "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"}})

    run_start = 0  # 0-based data index; sheet row = index + 2 (row 1 is header)
    for i in range(1, n + 1):
        if i == n or statuses[i] != statuses[run_start]:
            push(run_start + 1, i + 1, statuses[run_start])  # +1 to skip header row
            run_start = i

    # Header cell: bold, no fill.
    requests.insert(0, {"repeatCell": {
        "range": {"sheetId": gid, "startRowIndex": 0, "endRowIndex": 1,
                  "startColumnIndex": status_col,
                  "endColumnIndex": status_col + 1},
        "cell": {"userEnteredFormat": {
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER"}},
        "fields": "userEnteredFormat(textFormat,horizontalAlignment)"}})

    api.call(token, args.sheet_id, ":batchUpdate", method="POST",
         body={"requests": requests})

    print(f"Wrote STATUS to {n} row(s) with {len(requests)} format block(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except urllib.error.HTTPError as e:
        print("Sheets API error", e.code, e.read().decode("utf-8", "replace")[:300])
        raise SystemExit(1)
