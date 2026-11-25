"""Validate Telegram HTML and post via Bot API. Posting requires an explicit --yes."""
import os
import re
from html.parser import HTMLParser

ALLOWED = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "code", "pre", "a", "blockquote", "tg-spoiler", "span"}
LIMIT = 4096


class _Checker(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.errors, self.stack, self.links = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag not in ALLOWED:
            self.errors.append(f"tag <{tag}> not allowed")
        if tag == "a":
            href = dict(attrs).get("href", "")
            if not href.startswith(("http://", "https://")):
                self.errors.append(f"bad link href {href!r}")
            self.links += 1
        self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unbalanced </{tag}>")
        else:
            self.stack.pop()


def split_messages(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"^\s*=====\s*$", text, flags=re.M) if p.strip()]


def visible_len(html: str) -> int:
    t = re.sub(r"<[^>]+>", "", html)
    return len(re.sub(r"&(amp|lt|gt|quot|#\d+);", "x", t))


def validate(text: str) -> list[str]:
    problems = []
    msgs = split_messages(text)
    if len(msgs) != 2:
        problems.append(f"expected 2 messages, got {len(msgs)}")
    for i, m in enumerate(msgs, 1):
        c = _Checker()
        c.feed(m)
        c.close()
        problems += [f"msg {i}: {e}" for e in c.errors]
        if c.stack:
            problems.append(f"msg {i}: unclosed tags {c.stack}")
        if c.links == 0:
            problems.append(f"msg {i}: no source links")
        if visible_len(m) > LIMIT:
            problems.append(f"msg {i}: {visible_len(m)} visible chars > {LIMIT}")
        if re.search(r"&(?!amp;|lt;|gt;|quot;|#\d+;)", m):
            problems.append(f"msg {i}: unescaped &")
    return problems


def send(messages: list[str], chat_id: str | None = None) -> list[int]:
    import requests

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "@aisignalweekly")
    ids = []
    for m in messages:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30, data={
            "chat_id": chat_id, "text": m, "parse_mode": "HTML", "disable_web_page_preview": "true"})
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram error: {data.get('description')}")  # token never printed
        ids.append(data["result"]["message_id"])
    return ids
