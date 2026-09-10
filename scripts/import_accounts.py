"""Import the account roster from FB ACCOUNTS.xlsx into the database.

Re-runnable: accounts are keyed by USERNAME, so editing the spreadsheet and
running this again refreshes the existing rows and adds the new ones. Any
account already linked to a Brave profile keeps that link.

The PASSWORD column is read past and never stored. Nothing in the app reads
saved passwords, so persisting them would only create a second plaintext copy
of the spreadsheet's most sensitive column.

Usage:
    python scripts/import_accounts.py                    # uses "FB ACCOUNTS.xlsx"
    python scripts/import_accounts.py path/to/file.xlsx
    python import_accounts.py --dry-run          # report, write nothing
"""
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_SHEET = "FB ACCOUNTS.xlsx"

# Header label -> column letter is resolved at run time, so inserting or
# reordering spreadsheet columns does not silently import the wrong field.
WANTED = {
    "NO": "sheet_no",
    "FACEBOOK NAME": "facebook_name",
    "USERNAME": "username",
    "EMAIL": "email",
    "NUMBER": "number",
}


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        raw = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    except KeyError:
        return []
    return ["".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))
            for si in re.findall(r"<si>(.*?)</si>", raw, re.S)]


def _cells(row_xml: str, shared: list[str]) -> dict:
    out = {}
    for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*)>(.*?)</c>', row_xml, re.S):
        col, attrs, inner = c.group(1), c.group(2), c.group(3)
        v = re.search(r"<v>([^<]*)</v>", inner)
        if not v:
            continue
        val = v.group(1)
        if 't="s"' in attrs:
            idx = int(val)
            val = shared[idx] if 0 <= idx < len(shared) else ""
        out[col] = val.strip()
    return out


def read_accounts(xlsx: Path) -> list[dict]:
    """Parse the sheet into account dicts. Rows without a username are skipped."""
    with zipfile.ZipFile(xlsx) as z:
        shared = _shared_strings(z)
        name = next((n for n in z.namelist()
                     if n.startswith("xl/worksheets/sheet")), None)
        if not name:
            raise SystemExit(f"No worksheet found inside {xlsx}")
        sheet = z.read(name).decode("utf-8", "replace")

    rows = re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S)
    if not rows:
        raise SystemExit(f"{xlsx} has no rows")

    header = _cells(rows[0], shared)
    colmap = {}
    for col, label in header.items():
        key = WANTED.get(label.upper().strip())
        if key:
            colmap[key] = col
    missing = [lbl for lbl, key in WANTED.items() if key not in colmap]
    if "username" not in colmap:
        raise SystemExit(f"{xlsx}: no USERNAME column (found: {sorted(header.values())})")
    if missing:
        print(f"  note: columns not present, importing as blank: {', '.join(missing)}")

    out = []
    for row_xml in rows[1:]:
        d = _cells(row_xml, shared)
        username = d.get(colmap["username"], "")
        if not username:
            continue
        raw_no = d.get(colmap.get("sheet_no", ""), "")
        try:
            sheet_no = int(float(raw_no)) if raw_no else None
        except ValueError:
            sheet_no = None
        out.append({
            "sheet_no": sheet_no,
            "facebook_name": d.get(colmap.get("facebook_name", ""), ""),
            "username": username,
            "email": d.get(colmap.get("email", ""), ""),
            "number": d.get(colmap.get("number", ""), ""),
        })
    return out


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]
    xlsx = Path(args[0]) if args else ROOT / DEFAULT_SHEET
    if not xlsx.exists():
        print(f"Spreadsheet not found: {xlsx}")
        return 1

    print(f"Reading {xlsx.name} ...")
    accounts = read_accounts(xlsx)
    print(f"  {len(accounts)} row(s) with a username")

    seen, dupes = set(), []
    for a in accounts:
        key = a["username"].lower()
        if key in seen:
            dupes.append(a["username"])
        seen.add(key)
    if dupes:
        print(f"  duplicate username(s), last row wins: {', '.join(dupes)}")

    if dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    from src.storage import config_manager as cfg
    from src.storage import database as db

    inserted = updated = 0
    for a in accounts:
        if db.upsert_account(**a) == "inserted":
            inserted += 1
        else:
            updated += 1

    total, linked = db.count_accounts()
    profiles = cfg.list_profiles()
    print(f"\nImported: {inserted} new, {updated} refreshed")
    print(f"Database now holds {total} account(s), {linked} linked to a Brave profile")
    print(f"Brave profiles configured on this machine: {len(profiles)}")
    if total and not linked:
        print("\nNone are linked yet, so no imported account can be driven by the app:")
        print("every action resolves a Brave profile path. Link them from the")
        print("Profiles tab, or add the matching Brave profile first.")
    print("\nPasswords were not imported by design; they remain only in the spreadsheet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
