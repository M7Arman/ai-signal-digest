"""Command line entry point.

  python -m aisignal collect [--only rss,youtube] [--transcripts-days 8] [--limit-sources N]
  python -m aisignal import-firstpass <folder with first-pass JSON files>
  python -m aisignal stats
"""
import argparse
import json
import sys
import traceback
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from . import storage
from .config import CONFIG_DIR, load_env
from .sources import load_sources


def cmd_collect(args):
    from .collectors import rss, youtube
    con = storage.connect()
    run_id = storage.start_run(con, "collect")
    only = set(args.only.split(",")) if args.only else {"rss", "youtube"}
    sources = [s for s in load_sources() if s.collector in only]
    if args.limit_sources:
        sources = sources[: args.limit_sources]
    tx_since = None
    if args.transcripts_days:
        tx_since = (datetime.now(timezone.utc) - timedelta(days=args.transcripts_days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    # group sources sharing one feed (e.g. two Latent Space hosts) so it is fetched once
    groups = defaultdict(list)
    for s in sources:
        groups[(s.collector, s.feed_url or s.url)].append(s)

    feeds_cache_path = CONFIG_DIR / "feeds_resolved.json"
    feeds_cache = json.loads(feeds_cache_path.read_text(encoding="utf-8")) if feeds_cache_path.exists() else {}
    counts, failures, raw = Counter(), [], []
    for (collector, _), group in groups.items():
        src = group[0]
        if collector == "rss" and not src.feed_url and src.url in feeds_cache:
            src.feed_url = feeds_cache[src.url]
        try:
            if collector == "rss":
                recs, info = rss.collect(src)
                feeds_cache[src.url] = info["feed_url"]
            else:
                recs, info = youtube.collect(src, transcripts_since=tx_since)
            if len(group) > 1:  # shared feed: attribute to all hosts
                for r in recs:
                    r["person"] = ", ".join(g.person for g in group)
            raw.append({"source_id": src.source_id, "info": info, "records": recs})
            n_new = storage.upsert_posts(con, recs, origin=collector)
            status = "ok" if recs else "empty"
            for g in group:
                storage.record_source_status(con, run_id, g.source_id, status, len(recs), n_new)
            counts[f"{src.platform}_items"] += len(recs)
            counts[f"{src.platform}_new"] += n_new
            print(f"  {status:6} {src.source_id:45} {len(recs):3} items, {n_new:3} new", flush=True)
        except Exception as e:  # one failing source never breaks the run
            err = f"{type(e).__name__}: {e}"
            failures.append({"source_id": src.source_id, "error": err})
            for g in group:
                storage.record_source_status(con, run_id, g.source_id, "failed", error=err)
            print(f"  FAILED {src.source_id:45} {err[:120]}", flush=True)
            if args.verbose:
                traceback.print_exc()
        con.commit()
    feeds_cache_path.write_text(json.dumps(feeds_cache, indent=1, sort_keys=True), encoding="utf-8")
    storage.write_raw_snapshot(run_id, "collect", raw)
    summary = {"sources": len(groups), "counts": dict(counts), "failures": failures, "credits_used": 0}
    storage.finish_run(con, run_id, summary)
    print(f"\nRun {run_id}: {len(groups) - len(failures)}/{len(groups)} sources ok, "
          f"{sum(v for k, v in counts.items() if k.endswith('_new'))} new posts, {len(failures)} failed.")


def cmd_import(args):
    from .importer import import_firstpass
    import_firstpass(args.folder)


def cmd_digest(args):
    from .config import OUT_DIR
    from .digest import select, telegram, writer
    con = storage.connect()
    start, end = select.window(args.days, args.end)
    items = select.candidates(con, start, end)
    n_accounts = len({i["person"] for i in items})
    stamp = end[:10]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prompt = writer.build_prompt(items, start, end, n_accounts)
    (OUT_DIR / f"prompt_{stamp}.txt").write_text(writer.SYSTEM + "\n\n" + prompt, encoding="utf-8")
    print(f"{len(items)} posts from {n_accounts} accounts, {start[:10]}..{end[:10]}; prompt ~{len(prompt)//4} tokens")
    if args.pack_only:
        print(f"wrote out/prompt_{stamp}.txt (no LLM call)")
        return
    text, usage = writer.write_digest(prompt)
    path = OUT_DIR / f"digest_{stamp}.html"
    path.write_text(text, encoding="utf-8")
    problems = telegram.validate(text)
    print(f"wrote {path.relative_to(OUT_DIR.parent)}; usage {usage}")
    print("validation:", "OK" if not problems else problems)


def cmd_check(args):
    from pathlib import Path
    from .digest import telegram
    text = Path(args.file).read_text(encoding="utf-8")
    problems = telegram.validate(text)
    for i, m in enumerate(telegram.split_messages(text), 1):
        print(f"message {i}: {telegram.visible_len(m)} visible chars")
    print("OK" if not problems else "\n".join(problems))
    return 1 if problems else 0


def cmd_post(args):
    from pathlib import Path
    from .digest import telegram
    text = Path(args.file).read_text(encoding="utf-8")
    problems = telegram.validate(text)
    if problems:
        sys.exit("refusing to post, validation failed:\n" + "\n".join(problems))
    if not args.yes:
        sys.exit("dry run only. Re-run with --yes after Arman approves this exact file.")
    ids = telegram.send(telegram.split_messages(text), args.chat)
    print(f"posted message ids {ids}")


def cmd_stats(_args):
    con = storage.connect()
    print("posts by platform:")
    for r in con.execute("SELECT platform, COUNT(*) n, MAX(published_at) latest FROM posts GROUP BY platform ORDER BY n DESC"):
        print(f"  {r['platform']:10} {r['n']:5}  latest {r['latest']}")
    r = con.execute("SELECT COUNT(DISTINCT person) p, COUNT(*) n FROM posts").fetchone()
    print(f"total {r['n']} posts from {r['p']} people")
    last = con.execute("SELECT run_id, summary FROM runs ORDER BY started_at DESC LIMIT 3").fetchall()
    for x in last:
        print(" run", x["run_id"], (x["summary"] or "")[:200])


def main(argv=None):
    load_env()
    ap = argparse.ArgumentParser(prog="aisignal")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--only", help="comma list of collectors: rss,youtube (x is paid, not default)")
    c.add_argument("--transcripts-days", type=int, default=0, help="fetch transcripts for videos newer than N days")
    c.add_argument("--limit-sources", type=int)
    c.add_argument("-v", "--verbose", action="store_true")
    c.set_defaults(fn=cmd_collect)
    i = sub.add_parser("import-firstpass")
    i.add_argument("folder")
    i.set_defaults(fn=cmd_import)
    d = sub.add_parser("digest", help="build the digest dry run into out/ (calls Claude unless --pack-only)")
    d.add_argument("--days", type=int, default=7)
    d.add_argument("--end", help="end date YYYY-MM-DD (exclusive), default now")
    d.add_argument("--pack-only", action="store_true", help="write the prompt pack only, no API call")
    d.set_defaults(fn=cmd_digest)
    k = sub.add_parser("check-digest")
    k.add_argument("file")
    k.set_defaults(fn=cmd_check)
    po = sub.add_parser("post", help="post an approved digest file to Telegram (needs --yes)")
    po.add_argument("file")
    po.add_argument("--yes", action="store_true")
    po.add_argument("--chat", help="override chat id (e.g. a private test channel)")
    po.set_defaults(fn=cmd_post)
    s = sub.add_parser("stats")
    s.set_defaults(fn=cmd_stats)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
