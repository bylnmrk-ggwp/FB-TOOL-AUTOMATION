"""Reading the roster Google Sheet, one shot or on a poll.

The sheet is where the operator edits the roster; the database is where the
roster lives. This module owns the sheet -> database direction. The parsing
belongs to src/storage/roster_import.py, which takes rows of cells and nothing
else, so a workbook import and a sheet sync map headers to columns the same
way and cannot disagree about what a row means. STATUS -> sheet_status is a
mirror only: it is read back so a blank cell can be counted as pending, and it
is written solely through src/storage/sheet_status.py.

Two ways to read the sheet, picked by whether a service-account key is present:

    CSV export      no credentials, works for any link-shared sheet
    Sheets v4 API   a service-account token; what a private sheet needs, and
                    the same credential the STATUS write-back uses

Both ask for the cell as the sheet DISPLAYS it. That matters for more than
convenience: many USERNAME cells hold phone numbers, which Sheets stores as
numbers and every .xlsx export renders "9.709293808E9" - not an address
Facebook will accept.

Two entry points share the reader:

    sync()          one shot - scripts/import_accounts.py
    SheetWatcher    a daemon thread that polls the sheet and hands changed
                    rows to the consuming thread through a queue; that thread
                    does the database writes, so SQLite is only ever written
                    from the thread that also reads it.

Google offers no push channel to a desktop app without a public HTTPS
endpoint, so "live" here means within one poll interval. POLL_SECONDS = 20 is
two reads a minute, well inside any quota and free on the CSV path.
"""
import csv
import io
import json
import os
import queue
import re
import threading
import time
import urllib.request
from pathlib import Path

from src.storage import roster_import
from src.storage import sheets_api as api

# The parser and its header map live in roster_import; re-exported here so a
# caller that already imports roster_sheet does not need both.
HEADERS = roster_import.HEADERS
clean_username = roster_import.clean_username
parse_accounts = roster_import.parse_accounts
fingerprint = roster_import.fingerprint
apply = roster_import.apply

POLL_SECONDS = 20

_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")


def sheet_id_and_gid(url_or_id: str) -> tuple[str, str]:
    """(spreadsheet id, gid) from a full edit URL or a bare id."""
    m = _SHEET_ID_RE.search(url_or_id or "")
    sid = m.group(1) if m else (url_or_id or "").strip()
    g = re.search(r"[#&?]gid=(\d+)", url_or_id or "")
    return sid, (g.group(1) if g else "0")


def read_csv_export(sheet_id: str, gid: str = "0") -> list[list[str]]:
    """Rows from the sheet's CSV export - displayed text, no credentials.

    Works for any sheet shared by link. A private sheet answers with Google's
    sign-in HTML instead, which the caller sees as a header without USERNAME.
    """
    url = (f"https://docs.google.com/spreadsheets/d/{sheet_id}"
           f"/export?format=csv&gid={gid}")
    with urllib.request.urlopen(url, timeout=60) as r:
        text = r.read().decode("utf-8", "replace")
    return list(csv.reader(io.StringIO(text)))


def read_api_key(sheet_id: str, api_key: str, tab: str = api.DEFAULT_TAB
                 ) -> list[list[str]]:
    """Rows through the v4 API with a plain API key (read-only, public sheet)."""
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
           f"/values/{tab}!A:Z?key={api_key}&valueRenderOption=FORMATTED_VALUE")
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("values", [])


def fetch_rows(tok: str | None = None, sheet_id: str = api.DEFAULT_SHEET_ID,
               tab: str = api.DEFAULT_TAB, gid: str = "0") -> list[list[str]]:
    """Every row of the tab, header first, by whichever path is available.

    An explicit service-account token wins, then GOOGLE_API_KEY, then the
    credential-free CSV export. Trailing empty cells are absent on every path.
    """
    if tok:
        return api.get_values(tok, sheet_id, f"{tab}!A1:Z")
    key = os.environ.get("GOOGLE_API_KEY") or ""
    if key:
        return read_api_key(sheet_id, key, tab)
    return read_csv_export(sheet_id, gid)


def sync(sheet_id: str = api.DEFAULT_SHEET_ID, tab: str = api.DEFAULT_TAB,
         dry_run: bool = False, gid: str = "0") -> dict:
    """One fetch-parse-apply pass. dry_run parses and counts, writes nothing."""
    rows = fetch_rows(sheet_id=sheet_id, tab=tab, gid=gid)
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
                    "connection aborted", "timed out", "urlopen error")


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
    drain `events` on the thread that owns the database and call apply() there.

    The poll uses a service-account token when a key file is present and the
    credential-free CSV export otherwise, so a link-shared sheet needs no
    setup at all to stay in sync.
    """

    def __init__(self, interval: float = POLL_SECONDS,
                 sheet_id: str = api.DEFAULT_SHEET_ID,
                 tab: str = api.DEFAULT_TAB, gid: str = "0"):
        super().__init__(name="SheetWatcher", daemon=True)
        self.interval = interval
        self.sheet_id = sheet_id
        self.tab = tab
        self.gid = gid
        self.events: queue.Queue = queue.Queue()
        # Not _stop: threading.Thread already has a private _stop() method,
        # and shadowing it makes Thread.join() raise "'Event' object is not
        # callable" the moment the thread has finished.
        self._stopped = threading.Event()
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

    def _token(self) -> str | None:
        """A service-account token, or None to fall back to the keyless read."""
        if not Path(api.DEFAULT_KEY).exists():
            return None
        if self._creds is None:
            self._creds = api.credentials()
        return api.refresh(self._creds)

    def run(self):
        from src.storage.sheet_status import sheet_enabled
        if not sheet_enabled():
            # Nothing to watch: the roster is the local database, and the
            # accounts are the browser profiles on this PC.
            return
        while not self._stopped.is_set():
            self._poll_once()
            self._stopped.wait(self._retry_wait())

    def _poll_once(self):
        try:
            rows = fetch_rows(self._token(), self.sheet_id, self.tab, self.gid)
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
        self._stopped.set()
