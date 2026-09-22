"""One-shot import of the account roster into the database.

Reads a local .xlsx through the header-mapped parser in
src/storage/roster_import.py: labels, not column letters, decide where each
cell lands, so a reordered workbook cannot import the wrong field.

Re-runnable: accounts are keyed by USERNAME, so editing the workbook and
running this again refreshes the existing rows and adds the new ones.
linked_profile, status and status_reason are never touched by an import.

A --sheet import reads the live Google Sheet instead, taking each cell as the
sheet DISPLAYS it. That matters for more than convenience: half this roster's
usernames are phone numbers, which Sheets stores as numbers and every .xlsx
export renders "9.709293808E9" - not an address Facebook will accept.

Usage:
    python scripts/import_accounts.py --xlsx FILE    # workbook -> database
    python scripts/import_accounts.py --xlsx FILE --dry-run
    python scripts/import_accounts.py --sheet        # the project's roster sheet
    python scripts/import_accounts.py --sheet URL    # any other sheet
    python scripts/import_accounts.py --sheet URL --dry-run
"""
import argparse
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

from src.storage import roster_import  # noqa: E402
from src.storage import roster_sheet  # noqa: E402


# ── Local .xlsx fallback ────────────────────────────────────────────────────

def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        raw = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")
    except KeyError:
        return []
    return ["".join(re.findall(r"<t[^>]*>([^<]*)</t>", si))
            for si in re.findall(r"<si>(.*?)</si>", raw, re.S)]


def _cells(row_xml: str, shared: list[str]) -> dict[str, str]:
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


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - ord("A") + 1)
    return n - 1


def read_xlsx_rows(xlsx: Path) -> list[list[str]]:
    """The first worksheet as rows of cells, header first, in workbook order.

    Produces the rows-of-cells shape the parser in roster_import expects.
    """
    with zipfile.ZipFile(xlsx) as z:
        shared = _shared_strings(z)
        name = next((n for n in z.namelist()
                     if n.startswith("xl/worksheets/sheet")), None)
        if not name:
            raise SystemExit(f"No worksheet found inside {xlsx}")
        sheet = z.read(name).decode("utf-8", "replace")
    rows = []
    for row_xml in re.findall(r"<row[^>]*>(.*?)</row>", sheet, re.S):
        cells = _cells(row_xml, shared)
        if not cells:
            continue
        width = max(_col_index(c) for c in cells) + 1
        row = [""] * width
        for col, val in cells.items():
            row[_col_index(col)] = val
        rows.append(row)
    if not rows:
        raise SystemExit(f"{xlsx} has no rows")
    return rows


# ── Google Sheet ───────────────────────────────────────────────────────────────

# The sheet reader lives in src/storage/roster_sheet.py, because the running
# app polls the same sheet through it every 20 s. Both paths there return the
# cell as the sheet DISPLAYS it, which is what keeps a phone-number username
# from arriving as "9.709293808E9".
sheet_id_and_gid = roster_sheet.sheet_id_and_gid
read_sheet_rows = roster_sheet.fetch_rows


# ── Main ────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--xlsx", type=Path, help="the workbook to import")
    src.add_argument("--sheet", metavar="URL_OR_ID", nargs="?",
                     const=roster_sheet.api.DEFAULT_SHEET_ID,
                     help="import straight from a Google Sheet; bare --sheet "
                          "uses the project's own roster sheet")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args(argv)

    if args.sheet:
        sid, gid = sheet_id_and_gid(args.sheet)
        print(f"Reading sheet {sid} (gid {gid}) ...")
        rows = read_sheet_rows(sheet_id=sid, gid=gid)
        source = f"sheet:{sid}"
    else:
        if not args.xlsx.exists():
            print(f"Workbook not found: {args.xlsx}")
            return 1
        print(f"Reading {args.xlsx.name} ...")
        rows = read_xlsx_rows(args.xlsx)
        source = args.xlsx.name

    accounts = roster_import.parse_accounts(rows)
    header = [h.strip() for h in (rows[0] if rows else [])]
    print(f"  header: {header}")
    print(f"  {len(accounts)} row(s) with a username")
    missing = [lbl for lbl in roster_import.HEADERS
               if lbl not in {h.upper() for h in header}]
    if missing:
        print(f"  note: columns not present, importing as blank: {', '.join(missing)}")

    seen, dupes = set(), []
    for a in accounts:
        key = a["username"].lower()
        if key in seen:
            dupes.append(a["username"])
        seen.add(key)
    if dupes:
        print(f"  duplicate username(s), last row wins: {', '.join(dupes)}")

    if args.dry_run:
        print("\n--dry-run: nothing written.")
        return 0

    from src.storage import config_manager as cfg
    from src.storage import database as db

    inserted, updated = roster_import.apply(accounts)
    total, linked = db.count_accounts()
    profiles = cfg.list_profiles()
    print(f"\nImported from {source}: {inserted} new, {updated} refreshed")
    print(f"Database now holds {total} account(s), {linked} linked to a Brave profile")
    print(f"Brave profiles configured on this machine: {len(profiles)}")
    if total and not linked:
        print("\nNone are linked yet, so no imported account can be driven by the app:")
        print("every action resolves a Brave profile path. Link them from the")
        print("Profiles tab, or add the matching Brave profile first.")
    print("\nThe running app keeps the database current with the sheet every 20 s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
