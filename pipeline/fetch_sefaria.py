"""
fetch_sefaria.py — pull the Hebrew Bible books via the Sefaria JSON API.

The sefaria.org pages are JavaScript apps (the server sends ~1 KB), so stage 1 only
captured stubs. This fetches the real text (Hebrew + English, verse by verse) through
https://www.sefaria.org/api/texts/<ref>.<chapter> and overwrites data/raw/<id>.txt.
"""
import os
import re
import time
import requests

from util import url_to_id

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
HEADERS = {"User-Agent": "philosophy-taxonomy-pipeline (research)"}

BOOKS = {
    "Proverbs":     "https://www.sefaria.org/Proverbs",
    "Ecclesiastes": "https://www.sefaria.org/Ecclesiastes",
    "Job":          "https://www.sefaria.org/Job",
    "Genesis":      "https://www.sefaria.org/Genesis",
    "Isaiah":       "https://www.sefaria.org/Isaiah",
    "Amos":         "https://www.sefaria.org/Amos",
}


def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def api(ref):
    r = requests.get(f"https://www.sefaria.org/api/texts/{ref}",
                     params={"context": 0, "commentary": 0}, headers=HEADERS, timeout=25)
    return r.json()


def flatten(seg):
    """Yield verse strings from a chapter payload (list of str, or nested list)."""
    if isinstance(seg, str):
        if seg.strip():
            yield clean(seg)
    elif isinstance(seg, list):
        for x in seg:
            yield from flatten(x)


def fetch(ref):
    d = api(ref)
    nch = d.get("length") if isinstance(d.get("length"), int) else 1
    en, he = [], []
    for ch in range(1, nch + 1):
        dd = api(f"{ref}.{ch}")
        en.extend(flatten(dd.get("text")))
        he.extend(flatten(dd.get("he")))
        time.sleep(0.25)
    text = "\n".join(en) + "\n\n" + "\n".join(he)
    return text, nch, len(en)


def main():
    for ref, url in BOOKS.items():
        try:
            text, nch, nv = fetch(ref)
            with open(os.path.join(RAW, url_to_id(url) + ".txt"), "w", encoding="utf-8") as f:
                f.write(text)
            print(f"{ref:14} -> {nch:2} chapters, {nv:4} English verses, {len(text):,} chars", flush=True)
        except Exception as e:
            print(f"{ref:14} -> FAILED: {e}", flush=True)
    print("sefaria fetch complete.", flush=True)


if __name__ == "__main__":
    main()
