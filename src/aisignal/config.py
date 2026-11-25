import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
DB_PATH = Path(os.environ.get("AISIGNAL_DB", DATA_DIR / "aisignal.db"))
OUT_DIR = ROOT / "out"
USER_AGENT = "Mozilla/5.0 (compatible; AISignalDigest/0.1; RSS reader)"
EXCERPT_CHARS = 1500


def load_env(path: Path = ROOT / ".env") -> None:
    """Minimal .env loader: KEY=VALUE lines, does not override real env vars."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
