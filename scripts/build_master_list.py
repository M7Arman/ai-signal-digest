"""Parse a saved copy of https://ai-tldr.dev/influencers/ into config/influencers.json.

Usage: python scripts/build_master_list.py data/source/ai-tldr-influencers-YYYY-MM-DD.html
"""
import json, re, sys
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SECTION_SHORT = {
    "Lab Leaders & Founders": "Labs", "Researchers & Scientists": "Research",
    "Educators & Explainers": "Learn", "AI Engineering & Open Source": "Build",
    "Tools, Demos & Creators": "Tools", "Podcasts, Newsletters & Analysts": "Voices",
}
# Fixes learned in the first pass (2026-11-24): lowercase source handle -> working handle
YOUTUBE_FIXES = {
    "welchlabsvideo": "@WelchLabs", "t3dotgg": "@theo", "hamelhusain": "@hamelhusain7140",
    "peterdiamandis": "@peterdiamandis", "curiousrefuge": "@curiousrefuge",
    "sirajraval": "@SirajRaval", "nateherk": "@nateherk",
}
YOUTUBE_UNRESOLVED = {"ai-foundations"}

def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")

def main(html_path):
    soup = BeautifulSoup(Path(html_path).read_text(encoding="utf-8"), "html.parser")
    out = []
    for sec in soup.select("section.inf-section"):
        title = sec.select_one(".inf-section-title").get_text(strip=True)
        for a in sec.select("a.inf-card"):
            plat = next(c[len("inf-plat-"):] for c in a["class"] if c.startswith("inf-plat-"))
            plat = {"twitter": "x"}.get(plat, plat)
            name = a.select_one(".inf-name").get_text(strip=True)
            h = a.select_one(".inf-handle")
            reach = a.select_one(".inf-reach")
            url = a["href"]
            rec = {
                "id": slug(name), "name": name,
                "section": SECTION_SHORT.get(title, title), "section_title": title,
                "platform": plat, "url": url,
                "handle": h.get_text(strip=True) if h else None,
                "reach": reach.get_text(strip=True) if reach else None,
                "tags": [t.get_text(strip=True) for t in a.select(".inf-tag")],
                "bio": (a.select_one(".inf-bio") or a).get_text(strip=True) if a.select_one(".inf-bio") else None,
                "other_link_types": [i.get("title") for i in a.select(".inf-link-icon")],
            }
            if plat == "x":
                rec["x_username"] = url.rstrip("/").rsplit("/", 1)[-1]
            if plat == "youtube":
                yt = url.rstrip("/").rsplit("@", 1)[-1].lower()
                if yt in YOUTUBE_FIXES and "@" + yt != YOUTUBE_FIXES[yt].lower():
                    rec["url_original"], rec["url"] = url, "https://www.youtube.com/" + YOUTUBE_FIXES[yt]
                rec["youtube_handle"] = rec["url"].rstrip("/").rsplit("/", 1)[-1]
                if yt in YOUTUBE_UNRESOLVED:
                    rec["note"] = "handle not resolved in first pass"
            out.append(rec)
    dest = ROOT / "config" / "influencers.json"
    dest.write_text(json.dumps({"source": "https://ai-tldr.dev/influencers/",
                                "scraped_from": Path(html_path).name,
                                "count": len(out), "influencers": out}, indent=2, ensure_ascii=False), encoding="utf-8")
    from collections import Counter
    print(len(out), Counter(r["section"] for r in out), Counter(r["platform"] for r in out))

if __name__ == "__main__":
    main(sys.argv[1])
