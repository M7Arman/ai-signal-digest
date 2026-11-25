# AI Signal Digest (Telegram @aisignalweekly)

Pipeline: collect posts from the 159 AI influencers on https://ai-tldr.dev/influencers/ -> SQLite history -> weekly two-message Telegram digest -> later trend/investment analysis.

Owner: Arman (Asia/Yerevan, UTC+4). Wants very concise replies (2-3 line status per stage).

## Rules
- Free sources first (RSS/Atom, YouTube RSS, yt-dlp, youtube-transcript-api). Firecrawl is paid: give a credit estimate and get Arman's OK before any significant run.
- Never post to Telegram without Arman's explicit OK on a dry-run file (`out/`).
- Secrets only in `.env` (gitignored): TELEGRAM_BOT_TOKEN, FIRECRAWL_API_KEY, ANTHROPIC_API_KEY. Never in code, logs or commits.
- Never overwrite history: posts are upserted (unique platform+post_id); raw snapshots per run in `data/raw/YYYY-MM-DD/`.
- Dates stored as ISO-8601 UTC; convert relative dates at collection time.
- A failing source must not break a run; record per-source status.

## Digest format
Copy the structure of `config/digest_template.html` (the original approved sample `telegram_digest_sample.html` is lost; template rebuilt from the brief) (Telegram HTML, two messages split by `=====`, each < 4096 chars). Message 1 "AI WEEKLY" + date range, 4 numbered top stories, blockquotes, source links, ⚠️ italic note on single-source claims. Message 2 "WORTH A CLOSER LOOK", 4-6 items, footer "Source: posts and videos from N AI accounts, <date range>. Not financial advice." Only facts from the data; attribute opinions; link sources; no invented numbers. Allowed tags: b i u s code pre a blockquote tg-spoiler.

## Known source issues
See `config/feeds.json` (overrides, extra accounts, skipped LinkedIn/GitHub). X via Firecrawl x-com `users/posts` (sample, not full timeline; ilyasut, ch402, fchollet failed). Karpathy's YouTube is dormant; his X matters more. `@ai-foundations` unresolved.

See README.md for commands.
