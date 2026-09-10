import sqlite3
from pathlib import Path

AUTOSHARE_DIR = Path.home() / ".autoshare"
DB_PATH = AUTOSHARE_DIR / "autoshare.db"

_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        AUTOSHARE_DIR.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA busy_timeout=3000")
    return _conn


def init_db():
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS join_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile     TEXT    NOT NULL,
            group_url   TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            message     TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(profile, group_url)
        );

        CREATE TABLE IF NOT EXISTS share_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile     TEXT    NOT NULL,
            post_url    TEXT    NOT NULL,
            target      TEXT    NOT NULL DEFAULT '',
            status      TEXT    NOT NULL,
            message     TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(profile, post_url, target)
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            action      TEXT    NOT NULL,
            profile     TEXT    DEFAULT '',
            details     TEXT    DEFAULT '',
            created_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS profile_groups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            profile     TEXT    NOT NULL,
            group_name  TEXT    NOT NULL,
            group_url   TEXT    NOT NULL,
            fetched_at  TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(profile, group_url)
        );

        CREATE TABLE IF NOT EXISTS friend_relationships (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_a       TEXT    NOT NULL,
            profile_b       TEXT    NOT NULL,
            status          TEXT    NOT NULL DEFAULT 'pending',
            sent_by         TEXT    DEFAULT '',
            accepted_at     TEXT,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(profile_a, profile_b)
        );

        CREATE TABLE IF NOT EXISTS accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            sheet_no        INTEGER,
            facebook_name   TEXT    NOT NULL DEFAULT '',
            username        TEXT    NOT NULL,
            email           TEXT    NOT NULL DEFAULT '',
            number          TEXT    NOT NULL DEFAULT '',
            linked_profile  TEXT    NOT NULL DEFAULT '',
            imported_at     TEXT    NOT NULL DEFAULT (datetime('now','localtime')),
            UNIQUE(username)
        );

        CREATE TABLE IF NOT EXISTS used_images (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path      TEXT    NOT NULL UNIQUE,
            image_filename  TEXT    NOT NULL DEFAULT '',
            assigned_to     TEXT    NOT NULL DEFAULT '',
            session_id      TEXT    DEFAULT '',
            created_at      TEXT    NOT NULL DEFAULT (datetime('now','localtime'))
        );

        CREATE INDEX IF NOT EXISTS idx_join_profile ON join_history(profile);
        CREATE INDEX IF NOT EXISTS idx_join_url     ON join_history(group_url);
        CREATE INDEX IF NOT EXISTS idx_share_profile ON share_history(profile);
        CREATE INDEX IF NOT EXISTS idx_activity_action ON activity_log(action);
        CREATE INDEX IF NOT EXISTS idx_pg_profile ON profile_groups(profile);
        CREATE INDEX IF NOT EXISTS idx_pg_url     ON profile_groups(group_url);
        CREATE INDEX IF NOT EXISTS idx_fr_a ON friend_relationships(profile_a);
        CREATE INDEX IF NOT EXISTS idx_fr_b ON friend_relationships(profile_b);
        CREATE INDEX IF NOT EXISTS idx_acct_linked ON accounts(linked_profile);
        CREATE INDEX IF NOT EXISTS idx_acct_name ON accounts(facebook_name);
        CREATE INDEX IF NOT EXISTS idx_ui_path ON used_images(image_path);
        CREATE INDEX IF NOT EXISTS idx_ui_profile ON used_images(assigned_to);
    """)
    conn.commit()


# ── Join History ──────────────────────────────────────────


def has_joined(profile: str, group_url: str) -> bool:
    """Check if a profile already joined (or has a pending request for) a group."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT status FROM join_history WHERE profile=? AND group_url=?",
        (profile, group_url),
    ).fetchone()
    if row is None:
        return False
    return row["status"] in ("joined", "pending", "requested")


def record_join(profile: str, group_url: str, status: str, message: str = ""):
    """Record a join attempt result.

    Status values: joined, pending, requested, already_member, failed, skipped, error
    Uses INSERT OR REPLACE so repeated attempts overwrite previous record.
    """
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO join_history (profile, group_url, status, message)
           VALUES (?, ?, ?, ?)""",
        (profile, group_url, status, message),
    )
    conn.commit()


# ── Share History ─────────────────────────────────────────


def record_share(profile: str, post_url: str, target: str, status: str, message: str = ""):
    """Record a share/post attempt. Overwrites previous record for same profile+post+target."""
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO share_history (profile, post_url, target, status, message)
           VALUES (?, ?, ?, ?, ?)""",
        (profile, post_url, target, status, message),
    )
    conn.commit()


def has_shared(profile: str, post_url: str, target: str) -> bool:
    """Check if a profile already successfully shared this post to this group."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT status FROM share_history WHERE profile=? AND post_url=? AND target=?",
        (profile, post_url, target),
    ).fetchone()
    if row is None:
        return False
    return row["status"] in ("shared", "ok", "success")


# ── Activity Log ──────────────────────────────────────────


def log_activity(action: str, profile: str = "", details: str = ""):
    """Log a general activity event."""
    conn = _get_conn()
    conn.execute(
        "INSERT INTO activity_log (action, profile, details) VALUES (?, ?, ?)",
        (action, profile, details),
    )
    conn.commit()


# ── Profile Groups (persisted membership) ─────────────────


def save_profile_groups(profile: str, groups: list[dict]):
    """Save fetched groups for a profile. Uses INSERT OR REPLACE for dedup.

    groups: list of dicts with keys: name, url
    """
    conn = _get_conn()
    _BAD_GROUP_PATHS = ("/discover", "/feed", "/joins", "/requests", "/pending", "/admin")
    for g in groups:
        name = (g.get("name") or "").strip()
        url = (g.get("url") or "").strip()
        if not name or not url:
            continue
        if any(url.rstrip("/").endswith(p) for p in _BAD_GROUP_PATHS):
            continue
        conn.execute(
            """INSERT OR REPLACE INTO profile_groups (profile, group_name, group_url)
               VALUES (?, ?, ?)""",
            (profile, name, url),
        )
    conn.commit()


def get_profile_groups(profile: str | None = None) -> list[dict]:
    """Get saved groups. If profile is None, returns all grouped by URL with profiles list."""
    conn = _get_conn()
    if profile:
        rows = conn.execute(
            "SELECT group_name, group_url, fetched_at FROM profile_groups WHERE profile=? ORDER BY group_name",
            (profile,),
        ).fetchall()
        return [dict(r) for r in rows]
    else:
        rows = conn.execute(
            "SELECT profile, group_name, group_url FROM profile_groups ORDER BY group_name, profile",
        ).fetchall()
        # Deduplicate: group by URL, collect profile names
        by_url: dict[str, dict] = {}
        for r in rows:
            url = r["group_url"]
            if url not in by_url:
                by_url[url] = {"name": r["group_name"], "url": url, "profiles": []}
            if r["profile"] not in by_url[url]["profiles"]:
                by_url[url]["profiles"].append(r["profile"])
        return sorted(by_url.values(), key=lambda g: g["name"].lower())


# ── Friend Relationships ────────────────────────────────


def record_friend_sent(profile_a: str, profile_b: str):
    """Record that profile_a sent a friend request to profile_b."""
    conn = _get_conn()
    # Normalize: always store the smaller name first to avoid duplicates
    a, b = sorted([profile_a, profile_b])
    conn.execute(
        """INSERT OR IGNORE INTO friend_relationships (profile_a, profile_b, status, sent_by)
           VALUES (?, ?, 'pending', ?)""",
        (a, b, profile_a),
    )
    conn.commit()


def record_friend_accepted(profile_a: str, profile_b: str):
    """Record that profiles are now friends (request accepted)."""
    conn = _get_conn()
    a, b = sorted([profile_a, profile_b])
    conn.execute(
        """INSERT OR REPLACE INTO friend_relationships (profile_a, profile_b, status, sent_by, accepted_at)
           VALUES (?, ?, 'friends', COALESCE((SELECT sent_by FROM friend_relationships WHERE profile_a=? AND profile_b=?), ''),
                   datetime('now','localtime'))""",
        (a, b, a, b),
    )
    conn.commit()


def are_friends(profile_a: str, profile_b: str) -> bool:
    """Check if two profiles are already friends."""
    conn = _get_conn()
    a, b = sorted([profile_a, profile_b])
    row = conn.execute(
        "SELECT status FROM friend_relationships WHERE profile_a=? AND profile_b=?",
        (a, b),
    ).fetchone()
    return row is not None and row["status"] == "friends"


def get_friend_count_for_profile(profile_name: str) -> int:
    """Count how many friends a profile has (from our managed profiles)."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM friend_relationships WHERE (profile_a=? OR profile_b=?) AND status='friends'",
        (profile_name, profile_name),
    ).fetchone()
    return row["c"]


def get_non_friends(profile_name: str, all_names: list[str]) -> list[str]:
    """Return list of profile names that are NOT yet friends with this profile."""
    conn = _get_conn()
    placeholders = ",".join("?" for _ in all_names)
    rows = conn.execute(
        f"""SELECT profile_a, profile_b, status FROM friend_relationships
            WHERE (profile_a=? OR profile_b=?) AND profile_a IN ({placeholders}) AND profile_b IN ({placeholders})""",
        [profile_name, profile_name] + all_names + all_names,
    ).fetchall()
    
    friend_names = set()
    for r in rows:
        if r["status"] == "friends":
            if r["profile_a"] != profile_name:
                friend_names.add(r["profile_a"])
            if r["profile_b"] != profile_name:
                friend_names.add(r["profile_b"])
    
    return [n for n in all_names if n != profile_name and n not in friend_names]


# ── Used Images ─────────────────────────────────────────


def mark_image_used(image_path: str, profile_name: str, session_id: str = ""):
    """Record that an image has been assigned to a profile."""
    import os
    conn = _get_conn()
    filename = os.path.basename(image_path)
    conn.execute(
        """INSERT OR IGNORE INTO used_images (image_path, image_filename, assigned_to, session_id)
           VALUES (?, ?, ?, ?)""",
        (image_path, filename, profile_name, session_id),
    )
    conn.commit()


def get_used_image_paths() -> set[str]:
    """Return set of all image paths that have been assigned to any profile."""
    conn = _get_conn()
    rows = conn.execute("SELECT image_path FROM used_images").fetchall()
    return {r["image_path"] for r in rows}


# ── Account roster ────────────────────────────────────────
# Imported from the operator's account spreadsheet. Passwords are
# deliberately NOT stored here: nothing in the app reads them (the
# credential-login path is unreachable from the GUI) and persisting them
# would create a second plaintext copy outside the spreadsheet.


def upsert_account(sheet_no, facebook_name: str, username: str,
                   email: str = "", number: str = "") -> str:
    """Insert or refresh one account, keyed by username.

    Returns "inserted" or "updated" so a caller can report real counts.
    An existing linked_profile is preserved across re-imports.
    """
    conn = _get_conn()
    if conn.execute("SELECT 1 FROM accounts WHERE username = ?",
                    (username,)).fetchone():
        conn.execute(
            """UPDATE accounts SET sheet_no = ?, facebook_name = ?, email = ?,
                                   number = ?,
                                   imported_at = datetime('now','localtime')
               WHERE username = ?""",
            (sheet_no, facebook_name, email, number, username))
        conn.commit()
        return "updated"
    conn.execute(
        """INSERT INTO accounts (sheet_no, facebook_name, username, email, number)
           VALUES (?, ?, ?, ?, ?)""",
        (sheet_no, facebook_name, username, email, number))
    conn.commit()
    return "inserted"


def list_accounts(linked_only: bool = False) -> list[dict]:
    """Every imported account, ordered by its spreadsheet row number."""
    conn = _get_conn()
    sql = ("SELECT sheet_no, facebook_name, username, email, number, "
           "linked_profile FROM accounts")
    if linked_only:
        sql += " WHERE linked_profile != ''"
    sql += " ORDER BY CASE WHEN sheet_no IS NULL THEN 1 ELSE 0 END, sheet_no"
    return [dict(r) for r in conn.execute(sql)]


def link_account(username: str, profile_name: str) -> bool:
    """Point an account at a saved Brave profile ('' clears the link)."""
    conn = _get_conn()
    cur = conn.execute(
        "UPDATE accounts SET linked_profile = ? WHERE username = ?",
        (profile_name, username))
    conn.commit()
    return cur.rowcount > 0


def count_accounts() -> tuple[int, int]:
    """(total imported, number linked to a Brave profile)."""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    linked = conn.execute(
        "SELECT COUNT(*) FROM accounts WHERE linked_profile != ''").fetchone()[0]
    return total, linked


# Auto-init on import
init_db()
