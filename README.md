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
python -m pytest -q tests                        # offline tests
```

## Layout
- `config/influencers.json` master list (159). Rebuild: `python scripts/build_master_list.py data/source/<saved page>.html`
- `config/feeds.json` feed overrides, extra accounts, skipped sources
- `data/aisignal.db` SQLite history; `data/raw/YYYY-MM-DD/` raw run snapshots; `data/transcripts/` full transcripts
- X collector (paid Firecrawl) is off until a cost estimate is approved.
