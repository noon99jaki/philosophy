"""
retry_ctext.py [wait_seconds] — finish the ctext.org works that were rate-limited.

Waits for the throttle to reset, then fetches each work's `slug/ens` (full English)
and `slug/zh` (full Chinese) aggregate page — only two requests per work — and
overwrites data/raw/<id>.txt. Run in the background; rebuild afterwards with
`python3 pipeline/pipeline.py --no-download`.
"""
import os
import sys
import time
import requests

from util import url_to_id, html_to_text

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
WORKS = ["mozi", "mengzi", "xunzi", "zhuangzi", "han-feizi",
         "shang-jun-shu", "shang-shu", "gongsunlongzi"]


def get(url, tries=3, base_wait=30):
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


def main():
    wait = int(sys.argv[1]) if len(sys.argv) > 1 else 1200
    print(f"waiting {wait}s for ctext.org throttle to reset …", flush=True)
    time.sleep(wait)
    ok = 0
    for slug in WORKS:
        text = ""
        for view in ("ens", "zh"):
            h = get(f"https://ctext.org/{slug}/{view}")
            if h:
                text += "\n\n" + html_to_text(h)
            time.sleep(4)
        if len(text.strip()) > 500:
            with open(os.path.join(RAW, url_to_id(f"https://ctext.org/{slug}") + ".txt"),
                      "w", encoding="utf-8") as f:
                f.write(text)
            print(f"{slug:16} -> {len(text):,} chars", flush=True)
            ok += 1
        else:
            print(f"{slug:16} -> STILL BLOCKED", flush=True)
        time.sleep(3)
    print(f"ctext retry done: {ok}/{len(WORKS)} works recovered.", flush=True)


if __name__ == "__main__":
    main()
