"""Pick the candidate posts for a digest window and pack them compactly for the LLM."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

from ..config import CONFIG_DIR

PER_ITEM_TEXT = 700
MAX_ITEMS = 300


def window(days: int, end: str | None = None) -> tuple[str, str]:
    end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if end else datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    f = "%Y-%m-%dT%H:%M:%SZ"
    return start_dt.strftime(f), end_dt.strftime(f)


def _sections() -> dict:
    infl = json.loads((CONFIG_DIR / "influencers.json").read_text(encoding="utf-8"))["influencers"]
    return {r["name"]: r["section"] for r in infl}


def candidates(con: sqlite3.Connection, start: str, end: str) -> list[dict]:
    rows = con.execute(
        "SELECT * FROM posts WHERE published_at >= ? AND published_at < ? ORDER BY published_at DESC",
        (start, end)).fetchall()
    sections = _sections()
    items = []
    for r in rows:
        m = json.loads(r["metrics"] or "{}")
        tx = m.pop("transcript_excerpt", "") or ""
        text = (r["text"] or "").strip()
        body = text[:PER_ITEM_TEXT]
        if tx:
            body += ("\n[transcript excerpt] " + tx[:PER_ITEM_TEXT])
        items.append({
            "id": r["id"], "person": r["person"],
            "group": sections.get(r["person"].split(",")[0].strip(), "?"),
            "platform": r["platform"], "date": (r["published_at"] or "")[:10],
            "title": r["title"], "text": body, "url": r["url"],
            "metrics": {k: v for k, v in m.items() if k in ("views", "likes", "duration")},
        })
    # cap per person so one prolific feed can't dominate, then overall cap
    per_person, out = {}, []
    for it in items:
        n = per_person.get(it["person"], 0)
        if n < 6:
            out.append(it)
            per_person[it["person"]] = n + 1
    return out[:MAX_ITEMS]
