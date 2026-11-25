import hashlib
import re
from datetime import datetime, timedelta, timezone

from dateutil import parser as dtparser


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def to_iso_utc(value, ref: datetime | None = None) -> str | None:
    """Parse absolute or relative ('3 days ago') dates into ISO-8601 UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif hasattr(value, "tm_year"):  # time.struct_time from feedparser (already UTC)
        dt = datetime(*value[:6], tzinfo=timezone.utc)
    else:
        s = str(value).strip()
        rel = parse_relative(s, ref)
        if rel:
            dt = rel
        else:
            try:
                dt = dtparser.parse(s)
            except (ValueError, OverflowError):
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800,
          "month": 2592000, "year": 31536000}


def parse_relative(s: str, ref: datetime | None = None) -> datetime | None:
    ref = ref or datetime.now(timezone.utc)
    s = s.lower().strip()
    if s in ("today", "just now"):
        return ref
    if s == "yesterday":
        return ref - timedelta(days=1)
    m = re.match(r"(?:streamed\s+)?(\d+|an?|one)\s+(second|minute|hour|day|week|month|year)s?\s+ago", s)
    if not m:
        return None
    n = 1 if m.group(1) in ("a", "an", "one") else int(m.group(1))
    return ref - timedelta(seconds=n * _UNITS[m.group(2)])


def strip_html(html: str | None) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup
    return re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" ")).strip()


def short_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]
