"""Proof: the sheet's STATUS column is mirrored into accounts.sheet_status.

Runs under verify.py with globals `failures`, `step` and `ROOT`. Inserts
three verify_*@example.com rows into the real database and deletes them
again in a finally block, so an assertion that raises cannot leave them
behind.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - injected by verify.py

step("sheet_status mirror")  # noqa: F821
from src.storage import roster_sheet as _rs, database as _db  # noqa: E402

_rows = [["NO", "FACEBOOK NAME", "USERNAME", "PASSWORD", "STATUS"],
         ["1", "A", "verify_a@example.com", "x", "LOGGED IN"],
         ["2", "B", "verify_b@example.com", "x", ""],
         ["3", "C", "verify_c@example.com", "x"]]
_parsed = _rs.parse_accounts(_rows)
if [a.get("sheet_status") for a in _parsed] != ["LOGGED IN", "", ""]:
    failures.append(  # noqa: F821
        f"parse_accounts sheet_status: {[a.get('sheet_status') for a in _parsed]}")
_have = {r[1] for r in _db._get_conn().execute("PRAGMA table_info(accounts)")}
if "sheet_status" not in _have:
    failures.append("accounts.sheet_status column missing")  # noqa: F821
try:
    for _a in _parsed:
        _db.upsert_account(**_a)
    _pend = [a["username"] for a in _db.pending_accounts()
             if a["username"].startswith("verify_")]
    if _pend != ["verify_b@example.com", "verify_c@example.com"]:
        failures.append(f"pending_accounts: {_pend}")  # noqa: F821
    _n, _np = _db.count_pending()
    if _n < 2 or _np < 2:
        failures.append(f"count_pending: {(_n, _np)}")  # noqa: F821
    # list_accounts must carry the mirror so the Accounts table can show it.
    _listed = {a["username"]: a for a in _db.list_accounts()
               if a["username"].startswith("verify_")}
    if _listed.get("verify_a@example.com", {}).get("sheet_status") != "LOGGED IN":
        failures.append(  # noqa: F821
            f"list_accounts sheet_status: {_listed.get('verify_a@example.com')}")
finally:
    _db._get_conn().execute(
        "DELETE FROM accounts WHERE username LIKE 'verify_%@example.com'")
    _db._get_conn().commit()
if not hasattr(_rs.SheetWatcher(interval=999), "last_ok"):
    failures.append("SheetWatcher.last_ok missing")  # noqa: F821
print("ok" if not [f for f in failures  # noqa: F821
                   if "sheet_status" in f or "pending" in f or "last_ok" in f]
      else "FAILED")
