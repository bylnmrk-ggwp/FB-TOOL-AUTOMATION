"""One-shot sync of the account roster into the database.

The roster lives in the Google Sheet; by default this pulls it through the
same header-mapped parser the running app uses every 20 s
(src/storage/roster_sheet.py). A local .xlsx can still be imported with
--xlsx for an offline machine.

Re-runnable: accounts are keyed by USERNAME, so editing the sheet and running
this again refreshes the existing rows and adds the new ones. linked_profile,
status and status_reason are never touched by an import.

Usage:
    python scripts/import_accounts.py                # Google Sheet -> database
    python scripts/import_accounts.py --dry-run      # report, write nothing
    python scripts/import_accounts.py --xlsx FILE    # a local workbook instead
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
    """The first worksheet as rows of cells, header first, in sheet order.

    Produces the same shape the Sheets API returns, so the one parser in
    roster_sheet handles both sources.
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


# ── Main ────────────────────────────────────────────────────────────────────

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--xlsx", type=Path, help="import a local workbook instead of the sheet")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args(argv)

    if args.xlsx:
        if not args.xlsx.exists():
            print(f"Spreadsheet not found: {args.xlsx}")
            return 1
        print(f"Reading {args.xlsx.name} ...")
        rows = read_xlsx_rows(args.xlsx)
        source = args.xlsx.name
    else:
        print("Reading the Google Sheet ...")
        rows = roster_sheet.fetch_rows()
        source = "Google Sheet"

    accounts = roster_sheet.parse_accounts(rows)
    header = [h.strip() for h in (rows[0] if rows else [])]
    print(f"  header: {header}")
    print(f"  {len(accounts)} row(s) with a username")
    missing = [lbl for lbl in roster_sheet.HEADERS
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

    inserted, updated = roster_sheet.apply(accounts)
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
