"""
repair_downloads.py — re-fetch the sources that stage 1 captured as TOC-only.

  * sacred-texts index pages: crawl the numbered same-directory chapter files
    (sbe1000.htm, eog01.htm, …) which live in <area>/<map> tags, not <a href>.
  * ctext.org works: fetch the `slug/ens` (+ `slug/zh`) full-text aggregate pages
    — one request gets the whole work — with long back-off to ride out throttling.

Overwrites data/raw/<id>.txt for each repaired source. Run after stage 1; then
rebuild with `python3 pipeline/pipeline.py --no-download`.
"""
import os
import re
import time
import requests

from util import url_to_id, html_to_text

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

CTEXT_WORKS = ["mozi", "mengzi", "xunzi", "zhuangzi", "han-feizi",
               "shang-jun-shu", "shang-shu", "gongsunlongzi"]
ST_INDEXES = [
    "https://sacred-texts.com/bud/sbe10/index.htm",   # Dhammapada
    "https://sacred-texts.com/hin/sbe01/index.htm",   # Upanishads I
    "https://sacred-texts.com/hin/sbe15/index.htm",   # Upanishads II
    "https://sacred-texts.com/egy/ebod/index.htm",    # Book of the Dead
    "https://sacred-texts.com/hin/rigveda/index.htm", # Rig Veda
]


def get(url, tries=4, base_wait=40):
    """GET with back-off on throttling (403/429/503)."""
    for i in range(tries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25)
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 429, 503) and i < tries - 1:
                time.sleep(base_wait * (i + 1))
                continue
            return ""
        except Exception:
            if i < tries - 1:
                time.sleep(10 * (i + 1))
    return ""


def save(landing_url, text):
    uid = url_to_id(landing_url)
    with open(os.path.join(RAW, uid + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    return len(text)


def repair_sacred_texts():
    for idx in ST_INDEXES:
        html = get(idx, tries=2)
        if not html:
            print(f"ST  {idx}  -> index fetch failed", flush=True)
            continue
        base = idx.rsplit("/", 1)[0] + "/"
        # numbered same-directory files (content pages carry a digit; nav pages don't)
        files = sorted(set(re.findall(r'([a-z][a-z0-9_]+\.htm)', html)))
        files = [f for f in files if f != "index.htm" and any(c.isdigit() for c in f)][:60]
        text = html_to_text(html)
        n = 0
        for f in files:
            h = get(base + f, tries=2, base_wait=10)
            if h:
                t = html_to_text(h)
                if len(t) > 40:
                    text += "\n\n" + t
                    n += 1
            time.sleep(0.4)
        ln = save(idx, text)
        print(f"ST  {idx}  -> {n} chapters, {ln:,} chars", flush=True)


def repair_ctext():
    print("cooldown 60s before re-contacting ctext.org …", flush=True)
    time.sleep(60)
    for slug in CTEXT_WORKS:
        text = ""
        for view in ("ens", "zh"):
            h = get(f"https://ctext.org/{slug}/{view}", tries=4, base_wait=40)
            if h:
                text += "\n\n" + html_to_text(h)
            time.sleep(3)
        if text.strip():
            ln = save(f"https://ctext.org/{slug}", text)
            print(f"CT  {slug}  -> {ln:,} chars", flush=True)
        else:
            print(f"CT  {slug}  -> STILL BLOCKED", flush=True)


if __name__ == "__main__":
    repair_sacred_texts()
    repair_ctext()
    print("repair complete.", flush=True)
