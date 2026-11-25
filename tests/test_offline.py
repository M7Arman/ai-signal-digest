"""Offline tests: parsing, dedupe, import. No network."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Old &amp; gold</title><link>https://ex.com/a</link><guid>a</guid><pubDate>Mon, 17 Nov 2026 10:00:00 +0400</pubDate><description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description></item>
<item><title>New</title><link>https://ex.com/b</link><guid>b</guid><pubDate>Sun, 23 Nov 2026 08:00:00 GMT</pubDate><description>x</description></item>
</channel></rss>"""

YT = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">
<entry><id>yt:video:abcdefghijk</id><yt:videoId>abcdefghijk</yt:videoId><title>Vid</title>
<link rel="alternate" href="https://www.youtube.com/watch?v=abcdefghijk"/><published>2026-11-22T15:00:00+00:00</published>
<media:group><media:title>Vid</media:title><media:description>Desc here</media:description>
<media:community><media:starRating count="321" average="5.00" min="1" max="5"/><media:statistics views="12345"/></media:community></media:group></entry>
</feed>"""


def _src(platform="blog"):
    from aisignal.sources import Source
    return Source("p:" + platform, "Person", ["p"], platform, "https://ex.com", "rss")


def test_rss_parse():
    from aisignal.collectors.rss import parse_feed
    recs = parse_feed(RSS, _src())
    assert [r["post_id"] for r in recs] == ["b", "a"]          # newest first
    assert recs[1]["published_at"] == "2026-11-17T06:00:00Z"   # converted to UTC
    assert recs[1]["text"] == "Hello world" and recs[1]["title"] == "Old & gold"


def test_youtube_parse():
    from aisignal.collectors.youtube import parse_feed
    r = parse_feed(YT, _src("youtube"))[0]
    assert r["post_id"] == "abcdefghijk" and r["metrics"] == {"views": 12345, "likes": 321}
    assert r["text"] == "Desc here" and r["published_at"] == "2026-11-22T15:00:00Z"


def test_relative_dates():
    from datetime import datetime, timezone
    from aisignal.util import to_iso_utc
    ref = datetime(2026, 11, 24, 12, tzinfo=timezone.utc)
    assert to_iso_utc("3 days ago", ref) == "2026-11-21T12:00:00Z"
    assert to_iso_utc("an hour ago", ref) == "2026-11-24T11:00:00Z"
    assert to_iso_utc("2026-11-20") == "2026-11-20T00:00:00Z"


def test_storage_dedupe(tmp_path):
    from aisignal import storage
    from aisignal.collectors.rss import parse_feed
    con = storage.connect(tmp_path / "t.db")
    recs = parse_feed(RSS, _src())
    assert storage.upsert_posts(con, recs, "rss") == 2
    assert storage.upsert_posts(con, recs, "rss") == 0
    assert con.execute("SELECT COUNT(*) FROM posts").fetchone()[0] == 2


def test_sources_load():
    from aisignal.sources import load_sources
    s = load_sources()
    by = {x.source_id: x for x in s}
    assert len([x for x in s if x.source_id != "andrej-karpathy:x"]) == 159
    assert by["simon-willison:blog"].collector == "rss"
    assert by["ruben-hassid:substack"].collector == "rss"
    assert by["andrew-ng:linkedin"].collector == "skip"
    assert by["sarah-guo:youtube"].collector == "youtube"


def test_import_firstpass(tmp_path, monkeypatch):
    from aisignal import config, importer, storage
    monkeypatch.setattr(importer, "TRANSCRIPT_DIR", tmp_path / "tx")
    monkeypatch.setattr(storage, "RAW_DIR", tmp_path / "raw")
    db = tmp_path / "i.db"
    monkeypatch.setattr(storage, "DB_PATH", db)
    monkeypatch.setattr(storage.connect, "__defaults__", (db,))
    (tmp_path / "ai_tldr_influencers_latest_posts.json").write_text(json.dumps({"influencers": [
        {"name": "Simon Willison", "handle": "simonw", "platform": "blog", "status": "ok",
         "posts": [{"text": "t1", "date": "2026-11-20", "url": "https://simonwillison.net/x"}]},
        {"name": "Sam Altman", "handle": "sama", "platform": "X", "status": "ok",
         "posts": [{"text": "hi", "date": "2 days ago", "url": "https://x.com/sama/status/123"}]}]}))
    (tmp_path / "ai_tldr_youtube_videos.json").write_text(json.dumps({"channels": [
        {"name": "Fireship", "handle": "@Fireship", "videos": [
            {"video_id": "abcdefghijk", "title": "v", "date": "2026-11-21", "views": 5}]}]}))
    (tmp_path / "ai_tldr_youtube_transcripts.json").write_text(json.dumps({"abcdefghijk": "hello transcript"}))
    importer.import_firstpass(str(tmp_path))
    con = storage.connect(db)
    rows = {r["post_id"]: dict(r) for r in con.execute("SELECT * FROM posts")}
    assert rows["123"]["published_at"] == "2026-11-22T12:00:00Z"
    assert rows["123"]["person"] == "Sam Altman" and rows["123"]["platform"] == "x"
    assert "hello transcript" in rows["abcdefghijk"]["metrics"]


def test_discover_feed_skips_dead_advertised_link(monkeypatch):
    """A page advertising a 404 feed must not win; fall through to a working common path."""
    import requests
    from aisignal.collectors import rss

    class R:
        def __init__(self, url, text):
            self.url, self.text = url, text

    pages = {
        "https://ex.com/blog/": '<html><head><link rel="alternate" type="application/rss+xml" href="index.xml"></head></html>',
        "https://ex.com/blog/feed.xml": RSS.decode(),
    }

    def fake_get(url, **kw):
        if url in pages:
            return R(url, pages[url])
        raise requests.HTTPError(f"404 for {url}")

    monkeypatch.setattr(rss, "get", fake_get)
    assert rss.discover_feed("https://ex.com/blog/") == "https://ex.com/blog/feed.xml"


def test_digest_validate():
    from aisignal.digest.telegram import validate, split_messages
    good = ('📡 <b>AI WEEKLY</b> · Nov 18-25\n1️⃣ <b>X</b> said A &amp; B <a href="https://x.com/a/status/1">A</a>'
            '\n<blockquote>hi</blockquote>\n=====\n🔍 <b>WORTH A CLOSER LOOK</b> <a href="https://ex.com">B</a>')
    assert validate(good) == [] and len(split_messages(good)) == 2
    bad = good.replace("&amp;", "&").replace("<blockquote>hi</blockquote>", "<p>hi</p>")
    probs = validate(bad)
    assert any("<p>" in p for p in probs) and any("unescaped" in p for p in probs)


def test_digest_pack(tmp_path):
    from aisignal import storage
    from aisignal.collectors.rss import parse_feed
    from aisignal.digest import select, writer
    con = storage.connect(tmp_path / "d.db")
    storage.upsert_posts(con, parse_feed(RSS, _src()), "rss")
    start, end = select.window(7, "2026-11-25")
    items = select.candidates(con, start, end)
    assert [i["url"] for i in items] == ["https://ex.com/b"]
    p = writer.build_prompt(items, start, end, 1)
    assert "TEMPLATE" in p and "https://ex.com/b" in p
