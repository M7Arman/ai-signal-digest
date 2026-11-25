"""X (Twitter) via Firecrawl Alexandria provider `x-com`, capability `users/posts` (PAID credits).

Disabled unless explicitly enabled (--x) and FIRECRAWL_API_KEY is set. The CLI prints a cost
estimate and asks for confirmation before running.

NOTE: the exact REST endpoint/payload for Alexandria execution must be confirmed against the
Firecrawl docs before first use; until then `collect` raises NotImplementedError and the run
records the X sources as 'skipped'.
"""
from ..sources import Source

EST_CREDITS_PER_ACCOUNT = None  # fill in after checking Firecrawl pricing for x-com users/posts


def collect(src: Source, from_date: str, to_date: str, limit: int = 10):
    raise NotImplementedError("X collector not wired yet (needs Firecrawl Alexandria REST details + budget OK)")
