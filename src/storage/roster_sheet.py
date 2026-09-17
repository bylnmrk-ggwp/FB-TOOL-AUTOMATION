"""Roster rows from the Google Sheet, mapped by header label, into `accounts`.

Header labels, not column letters, decide where a cell lands, so the sheet can
be reordered or gain columns without importing the wrong field. The columns
the sheet owns are rewritten on every sync; linked_profile, status and
status_reason belong to this machine and are never touched here. STATUS
-> sheet_status is a mirror only: the app reads the verdict cell back so
it can count blank rows as pending, and writes it solely through
src/storage/sheet_status.py.

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
import re
import unicodedata
import json
import queue
import threading
import time

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
    # Read-only mirror of the cell the login runs write. "" means the row
    # has never been given a verdict - the "pending" set the dashboard counts.
    "STATUS": "sheet_status",
}

POLL_SECONDS = 20


def fetch_rows(tok: str | None = None, sheet_id: str = api.DEFAULT_SHEET_ID,
               tab: str = api.DEFAULT_TAB) -> list[list[str]]:
    """Every row of the tab, header first. Trailing empty cells are absent."""
    tok = tok or api.token()
    return api.get_values(tok, sheet_id, f"{tab}!A1:Z")


# The roster is edited by hand and operators annotate the USERNAME cell
# itself - a tick when an account is done, "(Na oopen)" beside one that would
# not open, an invisible left-to-right mark pasted in from elsewhere. Taken
# literally, those notes make a second account out of one address (the twin
# carries no password) and get typed into Facebook, which answers "Input
# Email or mobile number is invalid". The address is the account; the note is
# not part of it.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def clean_username(raw: str) -> str:
    """The account identifier inside a USERNAME cell, without the notes.

    An email anywhere in the cell wins, since that is what Facebook is given.
    Otherwise the cell keeps its own text (names and phone numbers are valid
    identifiers) minus invisible formatting characters and outer whitespace.
    """
    text = "".join(ch for ch in (raw or "") if unicodedata.category(ch) != "Cf")
    found = _EMAIL_RE.search(text)
    return found.group(0) if found else text.strip()


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
        username = clean_username(cell(cols["USERNAME"]))
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


# urllib3 wraps a failed name lookup in three nested exceptions and prints all
# of them; the operator only needs to know the PC cannot reach Google.
_OFFLINE_MARKERS = ("nameresolutionerror", "failed to resolve", "getaddrinfo",
                    "temporary failure in name resolution", "max retries exceeded",
                    "connection refused", "network is unreachable",
                    "connection aborted", "timed out")


def _reason(error: Exception) -> str:
    """One short line for a failed poll."""
    text = f"{error}".lower()
    if any(marker in text for marker in _OFFLINE_MARKERS):
        return "offline - cannot reach Google"
    return f"{type(error).__name__}: {error}"[:160]


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
        # time.time() of the last poll that reached the sheet, 0.0 before
        # the first; the dashboard shows it as "Sheet synced N s ago".
        self.last_ok: float = 0.0
        # Consecutive failures, and the wait they have earned. A PC that
        # loses its network answers every poll with the same DNS failure, and
        # polling it every 20 s for an hour only fills the log.
        self._failures = 0

    # Longest wait between retries while the sheet is unreachable.
    MAX_BACKOFF = 300.0

    def _retry_wait(self) -> float:
        """The wait before the next poll: the normal interval while healthy,
        doubling per consecutive failure up to MAX_BACKOFF."""
        if not self._failures:
            return self.interval
        return min(self.MAX_BACKOFF, self.interval * (2 ** min(self._failures, 8)))

    def run(self):
        from src.storage.sheet_status import sheet_enabled
        if not sheet_enabled():
            # Nothing to watch: the roster is the local database, and the
            # accounts are the browser profiles on this PC.
            return
        while not self._stop.is_set():
            self._poll_once()
            self._stop.wait(self._retry_wait())

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
            if self._failures:
                self.events.put(("error", "back online - the sheet is reachable again"))
            self._failures = 0
            self._last_error = None
            self.last_ok = time.time()
        except Exception as e:  # network, auth, parse - all recoverable
            self._failures += 1
            msg = _reason(e)
            wait = self._retry_wait()
            if msg != self._last_error:
                self._last_error = msg
                self.events.put(("error", f"{msg} - retrying every {wait:.0f}s"))

    def stop(self):
        self._stop.set()
