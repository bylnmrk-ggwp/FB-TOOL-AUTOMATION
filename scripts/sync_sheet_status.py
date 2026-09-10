"""Mirror each account's login status into the Google Sheet as a red/green pill.

Reads the roster sheet's USERNAME column, matches each row to the local
account database, and writes one STATUS column (G) plus a cell background:

    DISABLED        red    - Facebook disabled the account (db status)
    NOT LOGGED IN   red    - imported, no confirmed session yet
    LOGGED IN       green  - a valid cached session, or db status 'ok'
    (blank)         none   - the sheet row is not in the local database

Only column G is ever written. Columns A-F (including PASSWORD) are read to
match rows and never modified. Credentials never leave this machine except
the username, which is only used to look the row up.

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

from src.storage import database as db
from src.storage import state_cache

DEFAULT_SHEET_ID = "1oKKPnfTCn7LXqO9kboS3Jx2Aw8aWYeVh9PordjNxFeM"
DEFAULT_TAB = "Sheet1"
DEFAULT_KEY = ROOT / ".secrets" / "sheets-service-account.json"
USERNAME_COL = "C"          # the column holding the Facebook login id
STATUS_COL_INDEX = 6        # 0-based: column G

# Cell backgrounds. Red and green are the pill fills; white text reads on both.
RED = {"red": 0.80, "green": 0.16, "blue": 0.16}
GREEN = {"red": 0.11, "green": 0.53, "blue": 0.28}
WHITE_TEXT = {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
NO_FILL = {"red": 1, "green": 1, "blue": 1}
DARK_TEXT = {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": False}

DISABLED = "DISABLED"
NOT_LOGGED_IN = "NOT LOGGED IN"
LOGGED_IN = "LOGGED IN"


def _token(key_path: Path) -> str:
    from google.oauth2.service_account import Credentials
    import google.auth.transport.requests as gtr
    creds = Credentials.from_service_account_file(
        str(key_path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(gtr.Request())
    return creds.token


def _api(token: str, sheet_id: str, path: str, method: str = "GET",
         body: dict | None = None) -> dict:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def status_for(account: dict | None) -> str:
    """The pill text for one sheet row, or '' when it is not in the database."""
    if account is None:
        return ""
    if (account.get("status") or "") == "disabled":
        return DISABLED
    linked = account.get("linked_profile") or ""
    logged_in = (account.get("status") == "ok"
                 or (linked and state_cache.load_state(linked) is not None))
    return LOGGED_IN if logged_in else NOT_LOGGED_IN


def _fill(status: str) -> tuple[dict, dict]:
    """(backgroundColor, textFormat) for a status."""
    if status in (DISABLED, NOT_LOGGED_IN):
        return RED, WHITE_TEXT
    if status == LOGGED_IN:
        return GREEN, WHITE_TEXT
    return NO_FILL, DARK_TEXT


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

    token = _token(key_path)

    # Resolve the tab's numeric id (needed for formatting requests).
    meta = _api(token, args.sheet_id,
                "?fields=sheets(properties(title,sheetId))")
    gid = next((s["properties"]["sheetId"] for s in meta["sheets"]
                if s["properties"]["title"] == args.tab), None)
    if gid is None:
        print(f"Tab not found: {args.tab}")
        return 1

    # Read the username column; its length fixes the data-row range.
    rng = urllib.parse.quote(f"{args.tab}!{USERNAME_COL}2:{USERNAME_COL}")
    got = _api(token, args.sheet_id, f"/values/{rng}").get("values", [])
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
    body = {"range": f"{args.tab}!G1:G{n + 1}",
            "majorDimension": "ROWS", "values": values}
    _api(token, args.sheet_id,
         f"/values/{urllib.parse.quote(f'{args.tab}!G1:G{n + 1}')}"
         "?valueInputOption=RAW", method="PUT", body=body)

    # 2. Colour each STATUS cell. Contiguous rows of the same status collapse
    #    into one repeatCell request so the batch stays small.
    requests = []

    def push(row_start, row_end, status):
        bg, text = _fill(status)
        requests.append({"repeatCell": {
            "range": {"sheetId": gid, "startRowIndex": row_start,
                      "endRowIndex": row_end,
                      "startColumnIndex": STATUS_COL_INDEX,
                      "endColumnIndex": STATUS_COL_INDEX + 1},
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
                  "startColumnIndex": STATUS_COL_INDEX,
                  "endColumnIndex": STATUS_COL_INDEX + 1},
        "cell": {"userEnteredFormat": {
            "textFormat": {"bold": True},
            "horizontalAlignment": "CENTER"}},
        "fields": "userEnteredFormat(textFormat,horizontalAlignment)"}})

    _api(token, args.sheet_id, ":batchUpdate", method="POST",
         body={"requests": requests})

    print(f"Wrote STATUS to {n} row(s) with {len(requests)} format block(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except urllib.error.HTTPError as e:
        print("Sheets API error", e.code, e.read().decode("utf-8", "replace")[:300])
        raise SystemExit(1)
