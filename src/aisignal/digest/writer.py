"""Ask Claude to write the two-message digest from the candidate pack."""
import json
import os

from ..config import CONFIG_DIR

MODEL = os.environ.get("AISIGNAL_MODEL", "claude-opus-5-5")

SYSTEM = """You write "AI Signal Digest" (Telegram channel @aisignalweekly): a weekly digest of what ~160 AI researchers, lab leaders, builders, educators and analysts posted.

Hard rules:
- Use ONLY facts present in the provided posts. Never add outside knowledge, numbers, dates or names that are not in the data.
- Attribute every opinion or claim to the person who made it. Link the source post with <a href="URL">Name</a> using the exact URL from the data.
- If a story rests on one person's post only, add an italic line: <i>⚠️ Single source: …</i>
- Prefer stories several people talk about (count distinct people). Mix groups (Labs, Research, Learn, Build, Tools, Voices).
- Skip pure self-promotion, sponsor reads, course ads and off-topic posts.
- Output Telegram HTML only. Allowed tags: <b> <i> <u> <s> <code> <pre> <a href> <blockquote> <tg-spoiler>. No <br>, <p>, <ul>, <li>, headings or Markdown. Escape & < > in text as &amp; &lt; &gt;.
- Exactly two messages separated by a line containing only =====. Each message under 3800 characters including tags.
- Follow the template structure exactly: message 1 = "AI WEEKLY" header with the date range, 4 numbered top stories (bold heading, 2-3 sentences, a <blockquote> with a reaction or context, source links); message 2 = "WORTH A CLOSER LOOK" with 4-6 short items (topics, disputes, tools, open models, the contrarian view) and the footer.
- English, plain and direct. No hype words ("game-changer", "revolutionary"). No investment advice.
Return only the two messages, nothing else."""


def build_prompt(items: list[dict], start: str, end: str, n_accounts: int) -> str:
    template = (CONFIG_DIR / "digest_template.html").read_text(encoding="utf-8")
    return (
        f"Date range: {start[:10]} to {end[:10]}. Accounts with posts in range: {n_accounts}.\n\n"
        f"TEMPLATE (structure to copy; replace the {{…}} placeholders):\n{template}\n\n"
        f"POSTS ({len(items)}, JSON lines):\n" + "\n".join(json.dumps(i, ensure_ascii=False) for i in items)
    )


def write_digest(prompt: str) -> tuple[str, dict]:
    import anthropic

    client = anthropic.Anthropic()
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=32000,
        system=SYSTEM,
        thinking={"type": "adaptive"},
        output_config={"effort": "high"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {msg.stop_details}")
    text = "".join(b.text for b in msg.content if b.type == "text").strip()
    u = msg.usage
    usage = {"model": msg.model, "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "stop_reason": msg.stop_reason}
    return text, usage
