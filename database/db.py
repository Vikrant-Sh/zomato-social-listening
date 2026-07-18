"""
database/db.py — Module 2: the project's memory.

Every other module talks to the database ONLY through the functions
in this file. Nobody else writes SQL. That way, if we ever change the
database, we change one file.

Tables:
  posts          — one row per social post, from raw text to final score
  source_status  — one row per source (reddit / x / rss): last run health
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# The .db file lives next to this script, inside the database/ folder.
DB_PATH = Path(__file__).parent / "socialwatch.db"


# ---------------------------------------------------------------- connection

def get_connection():
    """Open a connection to the database file (creates it if missing)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # lets us read rows like dictionaries
    return conn


# ---------------------------------------------------------------- setup

def init_db():
    """Create the tables if they don't exist yet. Safe to run many times."""
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS posts (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        source         TEXT NOT NULL,              -- 'reddit' / 'x' / 'rss'
        source_post_id TEXT NOT NULL,              -- the post's own id on that platform
        author         TEXT,
        title          TEXT,
        body           TEXT,
        url            TEXT,
        posted_at      TEXT,                       -- when it appeared on the platform
        fetched_at     TEXT NOT NULL,              -- when WE collected it
        upvotes        INTEGER DEFAULT 0,
        comments       INTEGER DEFAULT 0,

        -- pipeline results (filled in later by Modules 4-6)
        prefilter_pass INTEGER,                    -- 1 = worth sending to Claude
        category       TEXT,                       -- e.g. 'food_safety'
        severity       INTEGER,                    -- 1-5, from Claude
        summary        TEXT,                       -- one-line summary, from Claude
        score          REAL,                       -- final 0-100 escalation score
        escalated      INTEGER DEFAULT 0,          -- 1 = actions were fired
        actions_log    TEXT,                       -- what we did about it

        UNIQUE(source, source_post_id)             -- the dedupe guard
    );

    CREATE TABLE IF NOT EXISTS source_status (
        source        TEXT PRIMARY KEY,            -- 'reddit' / 'x' / 'rss'
        last_run_at   TEXT,
        last_status   TEXT,                        -- 'ok' or an error message
        posts_fetched INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- writing

def save_post(post: dict) -> bool:
    """
    Save one collected post. Returns True if it was NEW,
    False if we already had it (duplicate — silently skipped).
    """
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO posts
               (source, source_post_id, author, title, body, url,
                posted_at, fetched_at, upvotes, comments)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                post["source"],
                post["source_post_id"],
                post.get("author"),
                post.get("title"),
                post.get("body"),
                post.get("url"),
                post.get("posted_at"),
                datetime.now(timezone.utc).isoformat(),
                post.get("upvotes", 0),
                post.get("comments", 0),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False  # duplicate — UNIQUE(source, source_post_id) blocked it
    finally:
        conn.close()


def update_prefilter(post_id: int, passed: bool):
    """Module 4 records whether a post is worth sending to Claude."""
    conn = get_connection()
    conn.execute(
        "UPDATE posts SET prefilter_pass = ? WHERE id = ?",
        (1 if passed else 0, post_id),
    )
    conn.commit()
    conn.close()


def update_classification(post_id: int, category: str, severity: int, summary: str):
    """Module 5 records Claude's verdict."""
    conn = get_connection()
    conn.execute(
        "UPDATE posts SET category = ?, severity = ?, summary = ? WHERE id = ?",
        (category, severity, summary, post_id),
    )
    conn.commit()
    conn.close()


def update_score(post_id: int, score: float):
    """Module 6 records the final escalation score."""
    conn = get_connection()
    conn.execute("UPDATE posts SET score = ? WHERE id = ?", (score, post_id))
    conn.commit()
    conn.close()


def mark_escalated(post_id: int, actions_log: str):
    """Module 7 records that real actions were fired for this post."""
    conn = get_connection()
    conn.execute(
        "UPDATE posts SET escalated = 1, actions_log = ? WHERE id = ?",
        (actions_log, post_id),
    )
    conn.commit()
    conn.close()


def update_source_status(source: str, status: str, posts_fetched: int):
    """Each collector reports how its run went (shown on the dashboard)."""
    conn = get_connection()
    conn.execute(
        """INSERT INTO source_status (source, last_run_at, last_status, posts_fetched)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(source) DO UPDATE SET
               last_run_at = excluded.last_run_at,
               last_status = excluded.last_status,
               posts_fetched = excluded.posts_fetched""",
        (source, datetime.now(timezone.utc).isoformat(), status, posts_fetched),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------- reading

def get_unprocessed_posts():
    """Posts the pre-filter (Module 4) hasn't looked at yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM posts WHERE prefilter_pass IS NULL ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unclassified_posts():
    """Posts that passed the pre-filter but Claude hasn't judged yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM posts WHERE prefilter_pass = 1 AND category IS NULL ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unscored_posts():
    """Classified posts that don't have a final score yet."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM posts WHERE category IS NOT NULL AND score IS NULL ORDER BY id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_posts(limit: int = 100):
    """Newest posts for the dashboard table."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM posts ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_source_statuses():
    """Health of each collector, for the dashboard's status strip."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM source_status").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- self-test

if __name__ == "__main__":
    print(f"Database file: {DB_PATH}")
    init_db()
    print("✅ Tables created (or already existed).")

    fake_post = {
        "source": "reddit",
        "source_post_id": "test123",
        "author": "test_user",
        "title": "Test post — my order never arrived",
        "body": "Waited 2 hours, food never came.",
        "url": "https://reddit.com/test123",
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "upvotes": 42,
        "comments": 7,
    }

    is_new = save_post(fake_post)
    print(f"✅ First save  → new post?  {is_new}   (should be True)")

    is_new_again = save_post(fake_post)
    print(f"✅ Second save → new post?  {is_new_again}  (should be False — dedupe works)")

    unprocessed = get_unprocessed_posts()
    print(f"✅ Unprocessed posts in DB: {len(unprocessed)}")

    update_source_status("reddit", "ok", 1)
    print(f"✅ Source status: {get_source_statuses()}")

    print("\nAll good — Module 2 works. 🎉")
