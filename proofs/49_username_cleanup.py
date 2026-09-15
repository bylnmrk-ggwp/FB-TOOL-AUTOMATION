"""A USERNAME cell is cleaned of the notes people type into it.

The roster is edited by hand, and operators annotate the USERNAME cell
itself: a green tick when an account is done, "(Na oopen)" beside one that
would not open, and invisible left-to-right marks pasted in from elsewhere.
The importer used to take the cell literally, which cost three ways:

  * `user@x.com` and `user@x.com<tick>` became two accounts, so one email
    got two Brave profiles and the annotated twin carried no password -
    "no password on the roster row - cannot re-login automatically";
  * the annotated address was typed into Facebook verbatim, which answers
    "Input Email or mobile number is invalid";
  * an invisible U+200E made a row silently fail to match its own profile.

clean_username() keeps the address and drops the note.
"""
import sys

sys.path.insert(0, str(ROOT))  # noqa: F821 - verify.py injects ROOT

step("username cleanup")  # noqa: F821

from src.storage.roster_import import clean_username, parse_accounts  # noqa: E402

CASES = [
    ("n38tq48zln8@dispmail.org✅", "n38tq48zln8@dispmail.org", "trailing tick emoji"),
    ("9ynr5@dispmail.org (Na oopen) ✔", "9ynr5@dispmail.org", "parenthesised note"),
    ("‎sobranglatina298@gmail.com", "sobranglatina298@gmail.com", "leading LTR mark"),
    ("  spaced@example.com  ", "spaced@example.com", "surrounding spaces"),
    ("UPPER@Example.COM", "UPPER@Example.COM", "case is preserved"),
    ("plain@example.com", "plain@example.com", "already clean"),
    ("jane", "jane", "not an email, left alone"),
    ("0970 223 2237", "0970 223 2237", "phone number kept whole"),
    ("‎", "", "nothing but an invisible mark"),
    ("", "", "empty"),
]
for raw, want, why in CASES:
    got = clean_username(raw)
    if got != want:
        failures.append(f"username cleanup ({why}): {raw!r} -> {got!r}, wanted {want!r}")  # noqa: F821

# The two spellings must collapse to one account, not two.
rows = [
    ["NO", "FACEBOOK NAME", "USERNAME", "PASSWORD", "STATUS"],
    ["1", "A", "dup@dispmail.org✅", "", ""],
    ["1", "A", "dup@dispmail.org", "secret", ""],
]
parsed = parse_accounts(rows)
names = [a["username"] for a in parsed]
if names != ["dup@dispmail.org", "dup@dispmail.org"]:
    failures.append(f"username cleanup: parse_accounts gave {names}")  # noqa: F821
# The row carrying the password must be the one that survives an upsert, so
# the cleaned pair has to be ordered as the workbook had them.
if parsed and parsed[-1].get("password") != "secret":
    failures.append("username cleanup: the password row must come last so it wins the upsert")  # noqa: F821

# A row whose USERNAME is only an annotation is not an account at all.
only_note = parse_accounts([rows[0], ["3", "B", "‎", "pw", ""]])
if only_note:
    failures.append(f"username cleanup: an annotation-only cell became an account: {only_note}")  # noqa: F821

print("FAILED" if [f for f in failures if "username cleanup" in f] else "ok")  # noqa: F821
