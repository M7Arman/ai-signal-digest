# AI Signal Digest

Collects posts from the ai-tldr.dev AI influencer list, keeps full history in SQLite, and (next stage) builds a two-message Telegram digest for @aisignalweekly.

## Setup (Windows PowerShell)
```
cd ai-signal-digest
python -m venv .venv; .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # fill in keys; .env is gitignored
$env:PYTHONPATH="src"
```

## Commands
```
python -m aisignal collect                       # free: RSS/Atom + YouTube RSS
python -m aisignal collect --transcripts-days 8  # + transcripts for last-8-day videos
python -m aisignal import-firstpass <folder>     # first-pass JSON files
python -m aisignal stats
python -m aisignal digest --days 7               # dry run -> out/digest_<date>.html (Claude API, ~$0.3-0.5/run)
python -m aisignal digest --days 7 --pack-only   # prompt pack only, no API call
python -m aisignal check-digest out/digest_<date>.html
python -m aisignal post out/digest_<date>.html --yes   # ONLY after Arman approves that exact file
python -m pytest -q tests                        # offline tests
```

## Layout
- `config/influencers.json` master list (159). Rebuild: `python scripts/build_master_list.py data/source/<saved page>.html`
- `config/feeds.json` feed overrides, extra accounts, skipped sources
- `data/aisignal.db` SQLite history; `data/raw/YYYY-MM-DD/` raw run snapshots; `data/transcripts/` full transcripts
- `config/digest_template.html` digest structure (reconstructed from the brief; replace with the approved sample if found)
- X collector (paid Firecrawl) is off until a cost estimate is approved.
