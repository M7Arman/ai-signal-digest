"""Import the first-pass JSON files (claude.ai run, 2026-11-24) into SQLite.

Files (in one folder):
  ai_tldr_influencers_latest_posts.json   influencers[] {name, handle, platform, status, posts[] {text,date,url}}
  ai_tldr_youtube_videos.json             YouTube channels with videos
  ai_tldr_youtube_transcripts.json        {video_id: transcript}
The YouTube schema is read tolerantly (several key spellings) because it was produced ad hoc.
"""
import json
import re
from pathlib import Path

from . import storage
from .config import CONFIG_DIR, EXCERPT_CHARS, TRANSCRIPT_DIR
from .util import now_utc, to_iso_utc

IMPORT_REF_DATE = "2026-11-24T12:00:00Z"  # first-pass collection date, for relative dates


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _people_index():
    infl = json.loads((CONFIG_DIR / "influencers.json").read_text(encoding="utf-8"))["influencers"]
    idx = {}
    for r in infl:
        for key in (r["name"], r.get("handle"), r.get("x_username"), r.get("youtube_handle"), r["url"]):
            if key:
                idx[_norm(key)] = r
    return idx


def _platform(p: str) -> str:
    p = (p or "").lower()
    return {"twitter": "x", "twitter/x": "x", "𝕏": "x"}.get(p, p) or "unknown"


def _post_id(platform: str, url: str | None, text: str | None) -> str:
    if url:
        m = re.search(r"/status/(\d+)", url)
        if m:
            return m.group(1)
        m = re.search(r"(?:v=|youtu\.be/|/shorts/)([\w-]{11})", url)
        if m:
            return m.group(1)
        return url
    from .util import short_hash
    return "hash:" + short_hash(text or "")


def _ref():
    from dateutil import parser
    return parser.isoparse(IMPORT_REF_DATE)


def _first(d: dict, *keys):
    for k in keys:
        if d.get(k) not in (None, ""):
            return d[k]
    return None


def import_firstpass(folder: str) -> None:
    folder = Path(folder)
    con = storage.connect()
    run_id = storage.start_run(con, "import-firstpass")
    people = _people_index()
    summary = {}

    # 1) X / blogs / Substack / podcasts
    p = folder / "ai_tldr_influencers_latest_posts.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        recs, unmatched = [], set()
        for inf in data.get("influencers", []):
            plat = _platform(inf.get("platform"))
            person = people.get(_norm(inf.get("name"))) or people.get(_norm(inf.get("handle")))
            if not person:
                unmatched.add(inf.get("name"))
            pid = person["id"] if person else _norm(inf.get("name"))
            for post in inf.get("posts") or []:
                url = post.get("url")
                recs.append({
                    "source_id": f"{pid}:{plat}", "person": person["name"] if person else inf.get("name"),
                    "platform": plat, "post_id": _post_id(plat, url, post.get("text")), "url": url,
                    "title": post.get("title"), "text": post.get("text"),
                    "published_at": to_iso_utc(post.get("date"), _ref()),
                    "metrics": {k: v for k, v in post.items() if k not in ("text", "date", "url", "title")},
                    "collected_at": IMPORT_REF_DATE,
                })
        n_new = storage.upsert_posts(con, recs, origin="firstpass")
        summary["posts_file"] = {"records": len(recs), "new": n_new, "unmatched_people": sorted(unmatched),
                                 "missing_dates": sum(1 for r in recs if not r["published_at"])}
        storage.write_raw_snapshot(run_id, "firstpass_posts", data)

    # 2) YouTube transcripts (full text to disk)
    transcripts = {}
    p = folder / "ai_tldr_youtube_transcripts.json"
    if p.exists():
        transcripts = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(transcripts, dict) and "transcripts" in transcripts and isinstance(transcripts["transcripts"], (dict, list)):
            transcripts = transcripts["transcripts"]
        if isinstance(transcripts, list):
            transcripts = {t.get("video_id"): t for t in transcripts if isinstance(t, dict)}
        TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
        for vid, t in transcripts.items():
            text = t if isinstance(t, str) else _first(t, "transcript", "text", "full_text") or json.dumps(t)
            (TRANSCRIPT_DIR / f"{vid}.json").write_text(json.dumps(
                {"video_id": vid, "source": "firstpass", "fetched_at": IMPORT_REF_DATE, "text": text},
                ensure_ascii=False), encoding="utf-8")

    # 3) YouTube videos
    p = folder / "ai_tldr_youtube_videos.json"
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        channels = data.get("channels") if isinstance(data, dict) else data
        if channels is None:
            channels = next((v for v in data.values() if isinstance(v, list)), [])
        recs = []
        for ch in channels:
            name = _first(ch, "name", "channel", "channel_name", "title")
            handle = _first(ch, "handle", "channel_handle", "url")
            person = people.get(_norm(name)) or people.get(_norm(handle)) or people.get(_norm(str(handle).lstrip("@")))
            pid = person["id"] if person else _norm(name)
            for v in ch.get("videos") or []:
                url = _first(v, "url", "link")
                vid = _first(v, "video_id", "id") or _post_id("youtube", url, None)
                tx = transcripts.get(vid)
                excerpt = _first(v, "transcript_excerpt", "transcript")
                if not excerpt and tx:
                    excerpt = (tx if isinstance(tx, str) else _first(tx, "transcript", "text") or "")[:EXCERPT_CHARS]
                metrics = {k: v[k] for k in ("views", "likes", "view_count", "like_count", "duration") if v.get(k) is not None}
                if excerpt:
                    metrics["transcript_excerpt"] = str(excerpt)[:EXCERPT_CHARS]
                recs.append({
                    "source_id": f"{pid}:youtube", "person": person["name"] if person else name,
                    "platform": "youtube", "post_id": vid,
                    "url": url or f"https://www.youtube.com/watch?v={vid}",
                    "title": v.get("title"), "text": _first(v, "description", "text"),
                    "published_at": to_iso_utc(_first(v, "date", "published_at", "upload_date", "published"), _ref()),
                    "metrics": metrics, "collected_at": IMPORT_REF_DATE,
                    "transcript_path": f"data/transcripts/{vid}.json" if vid in transcripts else None,
                })
        n_new = storage.upsert_posts(con, recs, origin="firstpass")
        summary["youtube_file"] = {"records": len(recs), "new": n_new,
                                   "with_transcript": sum(1 for r in recs if r["transcript_path"]),
                                   "missing_dates": sum(1 for r in recs if not r["published_at"])}
        storage.write_raw_snapshot(run_id, "firstpass_youtube", data)

    storage.finish_run(con, run_id, summary)
    print(json.dumps(summary, indent=1, ensure_ascii=False))
