"""
fetch_lowvalue.py — grab the real text for the few sources stage 1 got as stubs.

  * classics.mit.edu  -> the plain-text `.mb.txt` edition (the .html is a frameset stub)
  * avalon Hammurabi  -> the frameset's content page `hamcode.asp`
  * archive.org       -> the full OCR `<id>_djvu.txt`

Overwrites data/raw/<id>.txt keyed by the ORIGINAL source URL used in index.html,
so a rebuild (`python3 pipeline/pipeline.py --no-download`) picks them up.
"""
import os
import time
import requests

from util import url_to_id, html_to_text

RAW = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

# (fetch_url, mode, original_source_url)   mode: "text" = raw plain text, "html" = strip tags
JOBS = [
    ("https://classics.mit.edu/Aristotle/politics.mb.txt", "text",
     "https://classics.mit.edu/Aristotle/politics.html"),
    ("https://classics.mit.edu/Aristotle/metaphysics.mb.txt", "text",
     "https://classics.mit.edu/Aristotle/metaphysics.html"),
    ("https://classics.mit.edu/Plato/republic.mb.txt", "text",
     "https://classics.mit.edu/Plato/republic.html"),
    ("https://avalon.law.yale.edu/ancient/hamcode.asp", "html",
     "https://avalon.law.yale.edu/ancient/hamframe.asp"),
    ("https://archive.org/download/ashtadhyayitrans06paniuoft/ashtadhyayitrans06paniuoft_djvu.txt", "text",
     "https://archive.org/details/ashtadhyayitrans06paniuoft"),
    ("https://archive.org/download/firstphilosopher00fairiala/firstphilosopher00fairiala_djvu.txt", "text",
     "https://archive.org/details/firstphilosopher00fairiala"),
]


def main():
    for fetch_url, mode, src in JOBS:
        try:
            r = requests.get(fetch_url, headers=HEADERS, timeout=60, allow_redirects=True)
            if r.status_code != 200 or not r.text.strip():
                print(f"FAIL {r.status_code:>4}  {fetch_url}", flush=True)
                continue
            text = r.text if mode == "text" else html_to_text(r.text)
            with open(os.path.join(RAW, url_to_id(src) + ".txt"), "w", encoding="utf-8") as f:
                f.write(text)
            print(f"OK   {len(text):>8,}c  {os.path.basename(fetch_url)}  ->  {src}", flush=True)
        except Exception as e:
            print(f"ERR  {str(e)[:60]}  {fetch_url}", flush=True)
        time.sleep(0.6)
    print("low-value fetch complete.", flush=True)


if __name__ == "__main__":
    main()
