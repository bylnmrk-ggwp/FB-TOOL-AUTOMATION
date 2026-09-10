"""Delete the 18 confirmed cleanup targets (no PowerShell/Git needed).

Run from anywhere (double-click works too):
    python delete_cleanup_targets.py

The script anchors itself to its own folder, so it works no matter what
the current working directory is. Uses only the Python standard library.
Prints each file it deletes, skips files that are already gone, and
lists what remains.
"""

import sys
from pathlib import Path

# Work relative to THIS script's folder, not the working directory, so it
# works whether double-clicked or launched from a prompt anywhere.
BASE = Path(__file__).resolve().parent

# The 18 files confirmed for deletion by the user (content already
# merged into the single docs file where relevant).
TARGETS = [
    # ── Debug artifacts (4) ────────────────────────────────
    "dump_group.json",
    "dump_reaction_error.json",
    "dump_reaction_no_button.json",
    "debug_profile_page.png",
    # ── Redundant anti-spam delay docs (8) ─────────────────
    "ANTI_SPAM_DELAYS_UPDATE.txt",
    "BEFORE_AFTER_COMPARISON.txt",
    "COMMENT_DELAYS_UPDATE.txt",
    "COMPLETE_DELAYS_SUMMARY.txt",
    "IMPLEMENTATION_SUMMARY.txt",
    "QUICK_START_DELAYS.txt",
    "START_HERE.txt",
    "DELAY_SETTINGS_README.md",
    # ── Feature doc merged into the docs file (1) ──────────
    "COMMENT_FEATURE_UPDATE.txt",
    # ── Install notices merged into the docs file (3) ───────
    "HOW_TO_FIX.txt",
    "INSTALLATION_COMPLETE.txt",
    "*ALL FIXED - READ THIS.txt",  # wildcard: matches "✓ ALL FIXED - READ THIS.txt"
    # ── Dead-code stubs in src/ui (2) ──────────────────────
    "src/ui/quick_share_tab.py",
    "src/ui/credentials_tab.py",
]

# Files that must never be touched.
PROTECTED = {
    "INSTALL + TROUBLESHOOTING.md",
    "README.md",  # pointer stub - kept so GitHub shows a landing page
    "facebook_profiles.db",
    "main.py",
    "cli.py",
    "requirements.txt",
    ".gitignore",
}


def main() -> int:
    project = BASE
    print("=" * 60)
    print("  FB TOOL AUTOMATION - Cleanup (Python)")
    print("=" * 60)
    print(f"  Folder: {project}")
    print()

    # Safety: refuse to run if the docs marker isn't next to this script.
    marker = project / "INSTALL + TROUBLESHOOTING.md"
    if not marker.exists():
        print("!! INSTALL + TROUBLESHOOTING.md not found next to this script.")
        print(f"!! Expected it at: {project}")
        return 1

    deleted = 0
    missing = 0

    for name in TARGETS:
        path = project / name
        # Fallback: allow wildcard patterns (used for the file whose name
        # contains a special checkmark character).
        if not path.exists() and any(ch in name for ch in "*?"):
            matches = list(project.glob(name))
            if matches:
                path = matches[0]
        if path.exists():
            try:
                path.unlink()
                print(f"  [DELETED] {name}")
                deleted += 1
            except PermissionError as exc:
                print(f"  [FAILED ] {name}  (permission denied: {exc})")
            except OSError as exc:
                print(f"  [FAILED ] {name}  ({exc})")
        else:
            print(f"  [already gone] {name}")
            missing += 1

    print()
    print("=" * 60)
    if deleted:
        print(f"  Done! {deleted} deleted, {missing} already absent.")
    else:
        print("  Nothing to delete - all targets already gone.")
    print("=" * 60)
    print()

    # Show what's still in the project folder.
    print("Files remaining in project folder:")
    for path in sorted(project.iterdir()):
        if path.is_file() and not path.name.startswith("."):
            print(f"  - {path.name}")
    print()

    input("Press Enter to exit...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
