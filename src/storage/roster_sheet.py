"""Roster rows from the Google Sheet, mapped by header label, into `accounts`.

Header labels, not column letters, decide where a cell lands, so the sheet can
be reordered or gain columns without importing the wrong field. The columns
the sheet owns are rewritten on every sync; linked_profile, status and
status_reason belong to this machine and are never touched here.

Two entry points share the parser:

    sync()          one shot - scripts/import_accounts.py
    SheetWatcher    a daemon thread that polls the sheet and hands changed
                    rows to the UI thread through a queue; the UI thread does
                    the database writes, so SQLite is only ever written from
                    the thread that also reads it.

Google offers no push channel to a desktop app without a public HTTPS
endpoint, so "live" here means within one poll interval. POLL_SECONDS = 20 is
two reads a minute against a 300-a-minute project quota.
"""
import hashlib
import json
import queue
import threading

from src.storage import database as db
from src.storage import sheets_api as api

# Sheet header (upper-cased, stripped) -> accounts column. Every entry is a
# column the sheet owns. The first column carries the row number under a
# blank or "NO" header and is handled separately.
HEADERS = {
    "FACEBOOK NAME": "facebook_name",
    "USERNAME": "username",
    "PASSWORD": "password",
    "GMAIL": "gmail",
    "PASS FOR GMAIL": "gmail_password",
    "NUMBER": "number",
}

POLL_SECONDS = 20


def fetch_rows(tok: str | None = None, sheet_id: str = api.DEFAULT_SHEET_ID,
               tab: str = api.DEFAULT_TAB) -> list[list[str]]:
    """Every row of the tab, header first. Trailing empty cells are absent."""
    tok = tok or api.token()
    return api.get_values(tok, sheet_id, f"{tab}!A1:Z")


def parse_accounts(rows: list[list[str]]) -> list[dict]:
    """Sheet rows -> upsert_account kwargs. Rows without a USERNAME are skipped.

    sheet_no is the numeric first column when its header is blank or "NO",
    else the row's 1-based position under the header - which is what the
    sheet's own row numbers show.
    """
    if not rows:
        return []
    cols = api.header_columns(rows, *HEADERS)
    if "USERNAME" not in cols:
        raise ValueError(f"sheet has no USERNAME column; header is {rows[0]!r}")
    first = (rows[0][0] if rows[0] else "").strip().upper()
    no_col = 0 if first in ("", "NO") else None

    out = []
    for i, row in enumerate(rows[1:], start=1):
        def cell(idx):
            return row[idx].strip() if idx is not None and idx < len(row) else ""
        username = cell(cols["USERNAME"])
        if not username:
            continue
        raw_no = cell(no_col)
        try:
            sheet_no = int(float(raw_no)) if raw_no else i
        except ValueError:
            sheet_no = i
        acct = {"sheet_no": sheet_no, "username": username}
        for label, column in HEADERS.items():
            if column != "username":
                acct[column] = cell(cols.get(label))
        out.append(acct)
    return out


def fingerprint(rows: list[list[str]]) -> str:
    """Stable digest of the sheet contents, for change detection."""
    blob = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def apply(accounts: list[dict]) -> tuple[int, int]:
    """Upsert parsed rows. Returns (inserted, updated). Call on the DB thread."""
    inserted = updated = 0
    for acct in accounts:
        if db.upsert_account(**acct) == "inserted":
            inserted += 1
        else:
            updated += 1
    return inserted, updated


def sync(sheet_id: str = api.DEFAULT_SHEET_ID, tab: str = api.DEFAULT_TAB,
         dry_run: bool = False) -> dict:
    """One fetch-parse-apply pass. dry_run parses and counts, writes nothing."""
    rows = fetch_rows(sheet_id=sheet_id, tab=tab)
    accounts = parse_accounts(rows)
    result = {"rows": max(len(rows) - 1, 0), "accounts": len(accounts),
              "header": rows[0] if rows else [], "inserted": 0, "updated": 0}
    if not dry_run:
        result["inserted"], result["updated"] = apply(accounts)
    return result


class SheetWatcher(threading.Thread):
    """Poll the sheet; queue ("rows", accounts) when it changes.

    Also queues ("error", message) once per distinct failure and keeps
    polling, so a dropped connection is visible but never fatal. Consumers
    drain `events` on the UI thread and call apply() there.
    """

    def __init__(self, interval: float = POLL_SECONDS,
                 sheet_id: str = api.DEFAULT_SHEET_ID,
                 tab: str = api.DEFAULT_TAB):
        super().__init__(name="SheetWatcher", daemon=True)
        self.interval = interval
        self.sheet_id = sheet_id
        self.tab = tab
        self.events: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._creds = None
        self._last_fingerprint = None
        self._last_error = None

    def run(self):
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(self.interval)

    def _poll_once(self):
        try:
            if self._creds is None:
                self._creds = api.credentials()
            tok = api.refresh(self._creds)
            rows = fetch_rows(tok, self.sheet_id, self.tab)
            fp = fingerprint(rows)
            if fp != self._last_fingerprint:
                self._last_fingerprint = fp
                self.events.put(("rows", parse_accounts(rows)))
            self._last_error = None
        except Exception as e:  # network, auth, parse - all recoverable
            msg = f"{type(e).__name__}: {e}"[:200]
            if msg != self._last_error:
                self._last_error = msg
                self.events.put(("error", msg))

    def stop(self):
        self._stop.set()
