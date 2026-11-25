"""RSS/Atom collector for blogs, Substack and podcasts, with feed autodiscovery."""
from urllib.parse import urljoin, urlparse

import feedparser
from bs4 import BeautifulSoup

from ..sources import Source
from ..util import now_utc, strip_html, to_iso_utc
from .http import get

CANDIDATE_PATHS = ["feed", "rss", "feed.xml", "index.xml", "atom.xml", "rss.xml", "feed/podcast", "rss/"]
MAX_TEXT = 4000


def discover_feed(url: str) -> str | None:
    """Find a feed URL for a site: <link rel=alternate> first, then common paths."""
    try:
        r = get(url, timeout=15, retries=1)
        if _looks_like_feed(r.text):
            return url
        soup = BeautifulSoup(r.text, "html.parser")
        for link in soup.find_all("link", rel=lambda v: v and "alternate" in v):
            t = (link.get("type") or "").lower()
            if "rss" in t or "atom" in t:
                return urljoin(r.url, link["href"])
    except Exception:
        pass
    base = url if url.endswith("/") else url + "/"
    roots = [base]
    root = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
    if root != base:
        roots.append(root)
    for b in roots:
        for path in CANDIDATE_PATHS:
            try:
                r = get(urljoin(b, path), timeout=10, retries=0)
                if _looks_like_feed(r.text):
                    return r.url
            except Exception:
                continue
    return None


def _looks_like_feed(text: str) -> bool:
    head = text[:1000].lower()
    return "<rss" in head or "<feed" in head or "<rdf:rdf" in head


def parse_feed(xml: str | bytes, src: Source, limit: int | None = None) -> list[dict]:
    fp = feedparser.parse(xml)
    collected = now_utc()
    out = []
    entries = fp.entries
    # newest first even if the feed is unordered
    entries = sorted(entries, key=lambda e: e.get("published_parsed") or e.get("updated_parsed") or (0,), reverse=True)
    for e in entries[:limit] if limit else entries:
        url = e.get("link")
        post_id = e.get("id") or e.get("guid") or url
        if not post_id:
            continue
        body = ""
        if e.get("content"):
            body = e.content[0].get("value", "")
        body = strip_html(body or e.get("summary") or "")
        metrics = {}
        if e.get("itunes_duration"):
            metrics["duration"] = e.itunes_duration
        enclosure = next((l.get("href") for l in e.get("links", []) if l.get("rel") == "enclosure"), None)
        if enclosure:
            metrics["audio_url"] = enclosure
        out.append({
            "source_id": src.source_id, "person": src.person, "platform": src.platform,
            "post_id": post_id, "url": url, "title": strip_html(e.get("title")),
            "text": body[:MAX_TEXT],
            "published_at": to_iso_utc(e.get("published_parsed") or e.get("updated_parsed")
                                       or e.get("published") or e.get("updated")),
            "metrics": metrics, "collected_at": collected,
        })
    return out


def collect(src: Source, limit: int | None = 20) -> tuple[list[dict], dict]:
    """Returns (records, info). info carries the resolved feed_url so callers can cache it."""
    feed_url, r = src.feed_url, None
    if feed_url:
        try:
            r = get(feed_url)
        except Exception:
            r = None  # configured/cached feed broke: fall back to discovery
    if r is None:
        feed_url = discover_feed(src.url)
        if not feed_url:
            raise RuntimeError(f"no RSS/Atom feed found for {src.url}")
        r = get(feed_url)
    recs = parse_feed(r.content, src, limit)
    return recs, {"feed_url": feed_url, "raw_bytes": len(r.content)}
