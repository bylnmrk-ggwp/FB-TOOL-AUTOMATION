"""Minimal Google Sheets v4 access shared by the roster scripts.

One service-account token, plain urllib against the REST API - no gspread. The
key path, spreadsheet id and tab have defaults that match this project and can
be overridden by the SHEETS_SERVICE_ACCOUNT / SHEETS_SHEET_ID env vars.

Credentials read through here (passwords included) are held in memory for the
length of the run only and never written anywhere.
"""
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_SHEET_ID = os.environ.get(
    "SHEETS_SHEET_ID", "1oKKPnfTCn7LXqO9kboS3Jx2Aw8aWYeVh9PordjNxFeM")
DEFAULT_TAB = "Sheet1"
DEFAULT_KEY = Path(os.environ.get(
    "SHEETS_SERVICE_ACCOUNT", str(ROOT / ".secrets" / "sheets-service-account.json")))


def token(key_path: Path | str = DEFAULT_KEY) -> str:
    """A fresh OAuth access token for the service account."""
    from google.oauth2.service_account import Credentials
    import google.auth.transport.requests as gtr
    creds = Credentials.from_service_account_file(
        str(key_path), scopes=["https://www.googleapis.com/auth/spreadsheets"])
    creds.refresh(gtr.Request())
    return creds.token


def call(tok: str, sheet_id: str, path: str, method: str = "GET",
         body: dict | None = None) -> dict:
    """One REST call; returns the parsed JSON body."""
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok}",
        "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def get_values(tok: str, sheet_id: str, a1: str) -> list[list[str]]:
    """The rows in an A1 range (missing trailing cells simply absent)."""
    return call(tok, sheet_id,
                f"/values/{urllib.parse.quote(a1)}").get("values", [])


def update_values(tok: str, sheet_id: str, a1: str,
                  values: list[list], raw: bool = True) -> dict:
    """Overwrite an A1 range with the given rows."""
    opt = "RAW" if raw else "USER_ENTERED"
    return call(tok, sheet_id,
                f"/values/{urllib.parse.quote(a1)}?valueInputOption={opt}",
                method="PUT",
                body={"range": a1, "majorDimension": "ROWS", "values": values})


def batch_update(tok: str, sheet_id: str, requests: list[dict]) -> dict:
    """Apply a list of spreadsheet batchUpdate requests (e.g. formatting)."""
    return call(tok, sheet_id, ":batchUpdate", method="POST",
                body={"requests": requests})


def header_columns(rows: list[list[str]], *labels: str) -> dict[str, int]:
    """Map each wanted header label (upper-cased) to its 0-based column index.

    rows[0] is the header. A label not present is absent from the result.
    """
    if not rows:
        return {}
    want = {l.upper() for l in labels}
    out = {}
    for i, cell in enumerate(rows[0]):
        up = (cell or "").strip().upper()
        if up in want:
            out[up] = i
    return out
