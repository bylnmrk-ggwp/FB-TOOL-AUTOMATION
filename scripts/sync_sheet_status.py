"""Mirror each account's login status into the Google Sheet as a red/green pill.

Reads the roster sheet's USERNAME column, matches each row to the local
account database, and writes the STATUS column plus a cell background:

    DISABLED        red    - Facebook disabled the account (db status)
    NOT LOGGED IN   red    - imported, no confirmed session yet
    LOGGED IN       green  - a valid cached session, or db status 'ok'
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
from src.storage import state_cache

DEFAULT_SHEET_ID = api.DEFAULT_SHEET_ID
DEFAULT_TAB = api.DEFAULT_TAB
DEFAULT_KEY = api.DEFAULT_KEY


def col_letter(idx: int) -> str:
    """0-based column index -> A1 letters (0 -> A, 26 -> AA)."""
    out = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


def resolve_columns(tok: str, sheet_id: str, tab: str) -> dict[str, int]:
    """0-based indexes of the USERNAME and STATUS columns, from the header row.

    USERNAME must exist. A missing STATUS header is created in the first
    column past the header, so the first run on a fresh sheet adds it.
    """
    header = api.get_values(tok, sheet_id, f"{tab}!1:1")
    cols = api.header_columns(header, "USERNAME", "STATUS")
    if "USERNAME" not in cols:
        raise SystemExit(f"Sheet needs a USERNAME header; found "
                         f"{header[0] if header else '(empty)'}")
    if "STATUS" not in cols:
        cols["STATUS"] = len(header[0]) if header else 1
        c = col_letter(cols["STATUS"])
        api.update_values(tok, sheet_id, f"{tab}!{c}1:{c}1", [["STATUS"]])
    return {"username": cols["USERNAME"], "status": cols["STATUS"]}

# Cell backgrounds. Red and green are the pill fills; white text reads on both.
RED = {"red": 0.80, "green": 0.16, "blue": 0.16}
GREEN = {"red": 0.11, "green": 0.53, "blue": 0.28}
AMBER = {"red": 0.90, "green": 0.62, "blue": 0.15}    # in-progress
WHITE_TEXT = {"foregroundColor": {"red": 1, "green": 1, "blue": 1}, "bold": True}
NO_FILL = {"red": 1, "green": 1, "blue": 1}
DARK_TEXT = {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "bold": False}

DISABLED = "DISABLED"
NOT_LOGGED_IN = "NOT LOGGED IN"
LOGGED_IN = "LOGGED IN"
IN_PROGRESS = "LOGGING IN"          # a live run sets this while it works a row


def status_for(account: dict | None) -> str:
    """The pill text for one sheet row, or '' when it is not in the database.

    A not-logged-in row carries its reason after a slash when one is known,
    e.g. "NOT LOGGED IN / WRONG PASSWORD", so the sheet says why.
    """
    if account is None:
        return ""
    if (account.get("status") or "") == "disabled":
        return DISABLED
    linked = account.get("linked_profile") or ""
    logged_in = (account.get("status") == "ok"
                 or (linked and state_cache.load_state(linked) is not None))
    if logged_in:
        return LOGGED_IN
    reason = (account.get("status_reason") or "").strip()
    return f"{NOT_LOGGED_IN} / {reason.upper()}" if reason else NOT_LOGGED_IN


def _fill(status: str) -> tuple[dict, dict]:
    """(backgroundColor, textFormat) for a status, by category.

    status may carry a "/ reason" suffix, so match on the prefix, not equality.
    """
    if status == DISABLED or status.startswith(NOT_LOGGED_IN):
        return RED, WHITE_TEXT
    if status == LOGGED_IN:
        return GREEN, WHITE_TEXT
    if status.startswith(IN_PROGRESS):
        return AMBER, WHITE_TEXT
    return NO_FILL, DARK_TEXT


# ── Live single-row updates (used by login_accounts.py while it runs) ──────

def resolve_gid(tok: str, sheet_id: str, tab: str) -> int | None:
    """The numeric sheetId of a tab, needed for formatting requests."""
    meta = api.call(tok, sheet_id, "?fields=sheets(properties(title,sheetId))")
    return next((s["properties"]["sheetId"] for s in meta["sheets"]
                 if s["properties"]["title"] == tab), None)


def build_row_index(tok: str, sheet_id: str, tab: str,
                    username_col: int) -> dict[str, int]:
    """Map each USERNAME (lower-cased) to its 1-based sheet row.

    username_col is the 0-based index from resolve_columns()."""
    c = col_letter(username_col)
    rng = f"{tab}!{c}2:{c}"
    rows = api.get_values(tok, sheet_id, rng)
    out = {}
    for i, row in enumerate(rows):
        u = (row[0].strip() if row else "")
        if u:
            out[u.lower()] = i + 2      # data starts at row 2
    return out


def write_status(tok: str, sheet_id: str, gid: int, tab: str,
                 row: int, text: str, status_col: int) -> None:
    """Write one STATUS cell's value and colour it by category.

    status_col is the 0-based index from resolve_columns()."""
    col = col_letter(status_col)
    api.update_values(tok, sheet_id, f"{tab}!{col}{row}:{col}{row}", [[text]])
    bg, tf = _fill(text)
    api.batch_update(tok, sheet_id, [{"repeatCell": {
        "range": {"sheetId": gid, "startRowIndex": row - 1, "endRowIndex": row,
                  "startColumnIndex": status_col,
                  "endColumnIndex": status_col + 1},
        "cell": {"userEnteredFormat": {
            "backgroundColor": bg, "horizontalAlignment": "CENTER",
            "textFormat": tf}},
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"}}])


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
