"""YouTube collector (free): channel RSS feed + optional transcripts.

- Channel id is resolved once from the @handle page and cached in config/youtube_channels.json.
- RSS gives the latest 15 videos with title, description, date, views and like count.
- Transcripts via youtube-transcript-api (full text saved to data/transcripts/<video_id>.json,
  excerpt stored in the DB). yt-dlp is used as a fallback for channel id resolution.
"""
import json
import re
import time

import feedparser

from ..config import CONFIG_DIR, EXCERPT_CHARS, TRANSCRIPT_DIR
from ..sources import Source
from ..util import now_utc, to_iso_utc
from .http import get

CACHE = CONFIG_DIR / "youtube_channels.json"
FEED = "https://www.youtube.com/feeds/videos.xml?channel_id={}"
_CID_PATTERNS = [
    r'"externalId":"(UC[\w-]{22})"',
    r'<link rel="canonical" href="https://www\.youtube\.com/channel/(UC[\w-]{22})"',
    r'"channelId":"(UC[\w-]{22})"',
    r'<meta itemprop="identifier" content="(UC[\w-]{22})"',
]


def _cache() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _save_cache(c: dict) -> None:
    CACHE.write_text(json.dumps(c, indent=1, sort_keys=True), encoding="utf-8")


def resolve_channel_id(url: str) -> str:
    m = re.search(r"/channel/(UC[\w-]{22})", url)
    if m:
        return m.group(1)
    cache = _cache()
    key = url.rstrip("/").rsplit("/", 1)[-1].lower()
    if key in cache:
        return cache[key]
    cid = None
    try:
        html = get(url.rstrip("/") + "/about", timeout=20).text
        for pat in _CID_PATTERNS:
            m = re.search(pat, html)
            if m:
                cid = m.group(1)
                break
    except Exception:
        pass
    if not cid:
        cid = _resolve_with_ytdlp(url)
    if not cid:
        raise RuntimeError(f"could not resolve channel id for {url}")
    cache[key] = cid
    _save_cache(cache)
    return cid


def _resolve_with_ytdlp(url: str) -> str | None:
    try:
        import yt_dlp
    except ImportError:
        return None
    opts = {"quiet": True, "skip_download": True, "extract_flat": True, "playlistend": 1, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("channel_id") or info.get("id")
    except Exception:
        return None


def parse_feed(xml, src: Source, limit: int | None = None) -> list[dict]:
    fp = feedparser.parse(xml)
    collected = now_utc()
    out = []
    for e in fp.entries[:limit] if limit else fp.entries:
        vid = e.get("yt_videoid") or e.get("id", "").rsplit(":", 1)[-1]
        stats = e.get("media_statistics") or {}
        rating = e.get("media_starrating") or {}
        desc = (e.get("media_description") or e.get("summary") or "").strip()
        metrics = {}
        if stats.get("views"):
            metrics["views"] = int(stats["views"])
        if rating.get("count"):
            metrics["likes"] = int(rating["count"])
        out.append({
            "source_id": src.source_id, "person": src.person, "platform": "youtube",
            "post_id": vid, "url": e.get("link") or f"https://www.youtube.com/watch?v={vid}",
            "title": e.get("title"), "text": desc[:4000],
            "published_at": to_iso_utc(e.get("published_parsed") or e.get("published")),
            "metrics": metrics, "collected_at": collected,
        })
    return out


def fetch_transcript(video_id: str) -> dict | None:
    """Return {'lang':..., 'segments':[{text,start,duration}]} or None. Saves to disk."""
    path = TRANSCRIPT_DIR / f"{video_id}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    langs = ["en", "en-US", "en-GB"]
    try:
        try:  # youtube-transcript-api >= 1.0
            ft = YouTubeTranscriptApi().fetch(video_id, languages=langs)
            segs, lang = ft.to_raw_data(), getattr(ft, "language_code", "en")
        except (AttributeError, TypeError):  # 0.6.x
            segs, lang = YouTubeTranscriptApi.get_transcript(video_id, languages=langs), "en"
    except Exception:
        return None
    data = {"video_id": video_id, "lang": lang, "fetched_at": now_utc(), "segments": segs}
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def transcript_text(data: dict) -> str:
    return " ".join(s["text"].replace("\n", " ") for s in data.get("segments", []))


def collect(src: Source, limit: int | None = 15, transcripts_since: str | None = None,
            max_transcripts: int = 3) -> tuple[list[dict], dict]:
    """transcripts_since: ISO date; fetch transcripts only for videos published after it."""
    cid = src.extra.get("channel_id") or resolve_channel_id(src.url)
    r = get(FEED.format(cid))
    recs = parse_feed(r.content, src, limit)
    n_tx = 0
    if transcripts_since:
        for rec in recs:
            if n_tx >= max_transcripts or not rec["published_at"] or rec["published_at"] < transcripts_since:
                continue
            tx = fetch_transcript(rec["post_id"])
            if tx:
                full = transcript_text(tx)
                rec["metrics"]["transcript_excerpt"] = full[:EXCERPT_CHARS]
                rec["transcript_path"] = f"data/transcripts/{rec['post_id']}.json"
                n_tx += 1
                time.sleep(1.5)  # be gentle; YouTube blocks bursts of transcript requests
    return recs, {"channel_id": cid, "transcripts": n_tx}
