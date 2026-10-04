"""The STATUS column on the roster sheet: pill text, colour, and row writes.

roster_sheet.py owns the sheet -> database direction and says outright that
status is this machine's, never the sheet's. This module owns the way back:
turning a local account row into the pill the sheet shows.

    DISABLED        red    - Facebook disabled the account (db status)
    NOT LOGGED IN   red    - imported, no confirmed session yet
    LOGGED IN       green  - db status 'ok' (a login run or login check saw
                             the profile reach its Facebook home page)
    LOGGING IN      amber  - a live run is working that row right now
    (blank)         none   - the sheet row is not in the local database

USERNAME and STATUS are located by their header labels on every call, never
by a fixed column letter: a fixed index once pointed STATUS writes at the
NUMBER column after the sheet gained a column. No other column is ever
written, and no credential leaves this machine - the username is sent only to
find the row.

It lives here rather than in scripts/ because the app writes these too: a
watch that finds a disabled account pushes the verdict straight to the sheet.
scripts/sync_sheet_status.py re-exports these names and keeps the whole-sheet
CLI on top of them.
"""
from pathlib import Path

from src.storage import database as db
from src.storage import roster_import
from src.storage import sheets_api as api

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


def match_key(username: str) -> str:
    """The key a sheet cell and a database row are matched on.

    The roster is edited by hand and 127 USERNAME cells carry an invisible
    U+200E pasted in from elsewhere. The database holds the cleaned form,
    so matching the raw cell missed those rows and reported them as not in
    the database - which a whole-sheet write would then blank. Both sides
    go through the same cleaner the import uses.
    """
    return roster_import.clean_username(username or "").strip().lower()


def has_local_verdict(account: dict | None) -> bool:
    """Whether THIS machine has actually decided anything about an account.

    A fleet is split across several PCs, so most roster rows are worked by
    a machine that is not this one. A blank local status means "never
    attempted here", not "not logged in", and a caller that rewrites the
    whole STATUS column must leave those cells exactly as it found them -
    otherwise one PC erases every verdict the others recorded.
    """
    if not account:
        return False
    return bool((account.get("status") or "").strip()
                or (account.get("status_reason") or "").strip())


def status_for(account: dict | None) -> str:
    """The pill text for one sheet row, or '' when it is not in the database.

    A not-logged-in row carries its reason after a slash when one is known,
    e.g. "NOT LOGGED IN / WRONG PASSWORD", so the sheet says why.
    """
    if account is None:
        return ""
    if (account.get("status") or "") == "disabled":
        return DISABLED
    # Only a recorded verdict counts: status 'ok' is set by a login run or a
    # login check that saw the profile reach its home page. Cached cookies
    # alone say nothing about a checkpoint or email-confirmation gate.
    if account.get("status") == "ok":
        return LOGGED_IN
    reason = (account.get("status_reason") or "").strip()
    return f"{NOT_LOGGED_IN} / {reason.upper()}" if reason else NOT_LOGGED_IN


def fill(status: str) -> tuple[dict, dict]:
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


_fill = fill            # the name scripts/sync_sheet_status.py grew up with


# ── Single-row updates (a live run colouring the row it is working on) ──────

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
        u = match_key(row[0] if row else "")
        if u:
            out[u] = i + 2      # data starts at row 2
    return out


def write_status(tok: str, sheet_id: str, gid: int, tab: str,
                 row: int, text: str, status_col: int) -> None:
    """Write one STATUS cell's value and colour it by category.

    status_col is the 0-based index from resolve_columns()."""
    col = col_letter(status_col)
    api.update_values(tok, sheet_id, f"{tab}!{col}{row}:{col}{row}", [[text]])
    bg, tf = fill(text)
    api.batch_update(tok, sheet_id, [{"repeatCell": {
        "range": {"sheetId": gid, "startRowIndex": row - 1, "endRowIndex": row,
                  "startColumnIndex": status_col,
                  "endColumnIndex": status_col + 1},
        "cell": {"userEnteredFormat": {
            "backgroundColor": bg, "horizontalAlignment": "CENTER",
            "textFormat": tf}},
        "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,textFormat)"}}])


# The roster sheet is on: the operator edits the roster there, so the app
# reads it on a poll and mirrors each verdict back into its STATUS column.
# Set the "sheet_sync" setting to False to turn the mirror off on a PC that
# has no business reaching Google - the roster, the credentials and every
# verdict are already in the local database, and the accounts themselves are
# the browser profiles on this PC, so nothing stops working without it.
SHEET_SYNC = True


def sheet_enabled() -> bool:
    """Whether the roster sheet is mirrored at all."""
    try:
        from src.storage import config_manager as cfg
        return bool(cfg.get_setting("sheet_sync", SHEET_SYNC))
    except Exception:
        return SHEET_SYNC


def push_account_status(username: str,
                        sheet_id: str = api.DEFAULT_SHEET_ID,
                        tab: str = api.DEFAULT_TAB,
                        key_path: Path | str = api.DEFAULT_KEY) -> str:
    """Push one account's CURRENT database status to its sheet row.

    The database is the source: this reads the account back and writes
    whatever status_for() makes of it, so a caller cannot put a verdict on the
    sheet that the database does not already hold.

    Does nothing while the sheet is off, without touching the network.

    Returns the status text written, or '' when nothing was written - no key
    file, no matching sheet row, or an unknown account. Blocking network I/O:
    call it off the event loop.
    """
    if not username or not sheet_enabled():
        return ""
    account = next((a for a in db.list_accounts()
                    if match_key(a.get("username") or "")
                    == match_key(username)), None)
    if account is None:
        return ""
    text = status_for(account)
    if not text:
        return ""
    key = Path(key_path)
    if not key.exists():
        return ""
    tok = api.token(key)
    gid = resolve_gid(tok, sheet_id, tab)
    if gid is None:
        return ""
    cols = resolve_columns(tok, sheet_id, tab)
    row = build_row_index(tok, sheet_id, tab,
                          cols["username"]).get(match_key(username))
    if row is None:
        return ""
    write_status(tok, sheet_id, gid, tab, row, text, cols["status"])
    return text


# ── Many-row updates (a login run writing LOGGING IN before each account) ───

class SheetWriter:
    """Resolve the sheet once, then write many STATUS cells.

    push_account_status() re-reads the header and the username column on
    every call - fine for one verdict at the end of a watch, five HTTP calls
    too many when a run writes LOGGING IN before each of forty accounts.
    Construction does the network work, so build it off the event loop.
    Every failure is swallowed into .on/.error: the sheet is a mirror, never
    a reason to stop logging accounts in.
    """

    def __init__(self, sheet_id: str = api.DEFAULT_SHEET_ID,
                 tab: str = api.DEFAULT_TAB,
                 key_path: Path | str = api.DEFAULT_KEY):
        self.on = False
        self.error = ""
        self._key_path = key_path
        self._sheet_id = sheet_id
        self._tab = tab
        if not sheet_enabled():
            self.error = "sheet sync is off"
            return
        try:
            if not Path(key_path).exists():
                raise FileNotFoundError(f"no service-account key at {key_path}")
            self._tok = api.token(key_path)
            self._gid = resolve_gid(self._tok, sheet_id, tab)
            if self._gid is None:
                raise ValueError(f"tab {tab!r} not found")
            cols = resolve_columns(self._tok, sheet_id, tab)
            self._status_col = cols["status"]
            self._rows = build_row_index(self._tok, sheet_id, tab, cols["username"])
            self.on = True
        # SystemExit too: resolve_columns() exits when the sheet has no
        # USERNAME header, and that must not take the driver thread with it.
        except (Exception, SystemExit) as e:
            self.error = f"{type(e).__name__}: {e}"[:200]

    def write(self, username: str, text: str) -> bool:
        row = self._rows.get(match_key(username)) if self.on else None
        if not row:
            return False
        for attempt in range(2):
            try:
                write_status(self._tok, self._sheet_id, self._gid, self._tab,
                             row, text, self._status_col)
                return True
            except Exception as e:
                # One retry with a fresh token: the run can outlive the hour
                # the first token was good for.
                if attempt == 0:
                    try:
                        self._tok = api.token(self._key_path)
                        continue
                    except Exception:
                        pass
                self.error = f"{type(e).__name__}: {e}"[:200]
        return False

    def mark_in_progress(self, username: str) -> bool:
        return self.write(username, IN_PROGRESS)
