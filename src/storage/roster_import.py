"""Workbook rows, mapped by header label, into `accounts`.

Header labels, not column letters, decide where a cell lands, so the workbook
can be reordered or gain columns without importing the wrong field. The
columns an import owns are rewritten every time; linked_profile, status and
status_reason belong to this machine and are never touched here.

One entry point, scripts/import_accounts.py, reads a local .xlsx and hands
the rows here. The parser takes rows of cells and nothing else, so any reader
that produces that shape can feed it.
"""
import hashlib
import json
import re
import unicodedata

from src.storage import database as db

HEADERS = {
    "FACEBOOK NAME": "facebook_name",
    "USERNAME": "username",
    "PASSWORD": "password",
    "GMAIL": "gmail",
    "PASS FOR GMAIL": "gmail_password",
    "NUMBER": "number",
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def header_columns(rows: list[list[str]], *labels: str) -> dict[str, int]:
    """Map each wanted header label (upper-cased) to its 0-based column index.

    rows[0] is the header. A label not present is absent from the result.
    """
    if not rows:
        return {}
    want = {label.upper() for label in labels}
    out = {}
    for i, cell in enumerate(rows[0]):
        up = (cell or "").strip().upper()
        if up in want:
            out[up] = i
    return out


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
    """Workbook rows -> upsert_account kwargs. Rows without a USERNAME are skipped.

    sheet_no is the numeric first column when its header is blank or "NO",
    else the row's 1-based position under the header - which is what the
    workbook's own row numbers show.
    """
    if not rows:
        return []
    cols = header_columns(rows, *HEADERS)
    if "USERNAME" not in cols:
        raise ValueError(f"workbook has no USERNAME column; header is {rows[0]!r}")
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
    """Stable digest of the workbook contents, for change detection."""
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
