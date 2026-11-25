import time

import requests

from ..config import USER_AGENT

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.8"})
_session.cookies.set("CONSENT", "YES+cb", domain=".youtube.com")
_session.cookies.set("SOCS", "CAI", domain=".youtube.com")


def get(url: str, timeout: int = 20, retries: int = 2, **kw) -> requests.Response:
    last = None
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=timeout, **kw)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:  # network errors: retry with backoff
            last = e
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
    raise last
