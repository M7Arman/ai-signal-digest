"""Build the list of collectable sources from config/influencers.json + config/feeds.json."""
import json
from dataclasses import dataclass, field

from .config import CONFIG_DIR


@dataclass
class Source:
    source_id: str              # e.g. "simon-willison:blog"
    person: str
    person_ids: list[str]
    platform: str               # x | youtube | substack | blog | podcast | linkedin | github
    url: str
    collector: str              # rss | youtube | x | skip
    feed_url: str | None = None
    handle: str | None = None
    extra: dict = field(default_factory=dict)


def _load(name):
    p = CONFIG_DIR / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_sources() -> list[Source]:
    infl = _load("influencers.json")["influencers"]
    feeds = _load("feeds.json")
    overrides, extras, skip = feeds.get("overrides", {}), feeds.get("extra_sources", []), set(feeds.get("skip", []))
    out: list[Source] = []
    for r in infl:
        plat, url = r["platform"], r["url"]
        ov = overrides.get(r["id"], {})
        if "youtube.com/" in url:
            collector = "youtube"
        elif plat == "x":
            collector = "x"
        elif plat in ("substack", "blog", "podcast") or ov.get("feed_url"):
            collector = "rss"
        else:
            collector = "skip"   # linkedin, github without a feed
        if r["id"] in skip:
            collector = "skip"
        eff = ov.get("platform", "youtube" if collector == "youtube" else plat)
        out.append(Source(
            source_id=f"{r['id']}:{eff}", person=r["name"], person_ids=[r["id"]],
            platform=eff, url=url,
            collector=ov.get("collector", collector), feed_url=ov.get("feed_url"),
            handle=r.get("x_username") or r.get("youtube_handle") or r.get("handle"), extra=ov))
    for e in extras:  # additional accounts for the same person (e.g. Karpathy on X)
        out.append(Source(source_id=e["source_id"], person=e["person"], person_ids=e.get("person_ids", []),
                          platform=e["platform"], url=e["url"], collector=e["collector"],
                          feed_url=e.get("feed_url"), handle=e.get("handle"), extra=e))
    return out
