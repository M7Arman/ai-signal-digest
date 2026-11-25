"""SQLite history + raw JSON snapshots. History is append/upsert only, never deleted."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import DB_PATH, RAW_DIR
from .util import now_utc

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id            INTEGER PRIMARY KEY,
    platform      TEXT NOT NULL,
    post_id       TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    person        TEXT NOT NULL,
    url           TEXT,
    title         TEXT,
    text          TEXT,
    published_at  TEXT,          -- ISO-8601 UTC
    metrics       TEXT,          -- JSON
    collected_at  TEXT NOT NULL, -- first time we saw it
    updated_at    TEXT NOT NULL, -- last time we saw it
    origin        TEXT,          -- collector / import name
    transcript_path TEXT,
    UNIQUE(platform, post_id)
);
CREATE INDEX IF NOT EXISTS ix_posts_published ON posts(published_at);
CREATE INDEX IF NOT EXISTS ix_posts_person ON posts(person);

CREATE TABLE IF NOT EXISTS runs (
    run_id       TEXT PRIMARY KEY,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    kind         TEXT,
    summary      TEXT            -- JSON: counts per platform, failures, credits used
);

CREATE TABLE IF NOT EXISTS source_status (
    run_id     TEXT NOT NULL,
    source_id  TEXT NOT NULL,
    status     TEXT NOT NULL,     -- ok | empty | failed | skipped
    n_items    INTEGER DEFAULT 0,
    n_new      INTEGER DEFAULT 0,
    error      TEXT,
    PRIMARY KEY (run_id, source_id)
);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


def upsert_posts(con: sqlite3.Connection, records: list[dict], origin: str) -> int:
    """Insert new posts; for existing ones refresh metrics and fill empty fields. Returns # new."""
    new = 0
    for r in records:
        cur = con.execute("SELECT id, text, title, published_at, transcript_path FROM posts WHERE platform=? AND post_id=?",
                          (r["platform"], r["post_id"]))
        row = cur.fetchone()
        metrics = json.dumps(r.get("metrics") or {}, ensure_ascii=False)
        if row is None:
            con.execute(
                """INSERT INTO posts(platform, post_id, source_id, person, url, title, text, published_at,
                   metrics, collected_at, updated_at, origin, transcript_path)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r["platform"], r["post_id"], r["source_id"], r["person"], r.get("url"), r.get("title"),
                 r.get("text"), r.get("published_at"), metrics, r.get("collected_at") or now_utc(), now_utc(),
                 origin, r.get("transcript_path")))
            new += 1
        else:
            con.execute(
                """UPDATE posts SET metrics=?, updated_at=?,
                   text=COALESCE(NULLIF(text,''), ?), title=COALESCE(NULLIF(title,''), ?),
                   published_at=COALESCE(published_at, ?), transcript_path=COALESCE(transcript_path, ?)
                   WHERE id=?""",
                (metrics, now_utc(), r.get("text"), r.get("title"), r.get("published_at"),
                 r.get("transcript_path"), row["id"]))
    con.commit()
    return new


def start_run(con, kind: str) -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + kind
    con.execute("INSERT INTO runs(run_id, started_at, kind) VALUES (?,?,?)", (run_id, now_utc(), kind))
    con.commit()
    return run_id


def finish_run(con, run_id: str, summary: dict) -> None:
    con.execute("UPDATE runs SET finished_at=?, summary=? WHERE run_id=?",
                (now_utc(), json.dumps(summary, ensure_ascii=False), run_id))
    con.commit()


def record_source_status(con, run_id, source_id, status, n_items=0, n_new=0, error=None):
    con.execute("INSERT OR REPLACE INTO source_status VALUES (?,?,?,?,?,?)",
                (run_id, source_id, status, n_items, n_new, (error or "")[:500] or None))


def write_raw_snapshot(run_id: str, name: str, payload) -> Path:
    """Raw per-run snapshot in data/raw/YYYY-MM-DD/. Never overwrites: run_id is unique."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    d = RAW_DIR / day
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{run_id}__{name}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return p
