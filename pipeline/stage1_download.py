"""
Stage 1 — Download all listed sources in an organized uniform format.

Reads the original-text links out of ../index.html (the <a class="src"> anchors),
builds a uniform manifest (data/sources.json), then downloads each unique URL to
data/raw/<id>.html (+ cleaned <id>.txt) and records status in data/downloads.json.
"""
import os
import re
import json
import time
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from util import html_to_text, url_to_id

MAX_CHILDREN = 45      # cap sub-pages crawled per table-of-contents source
CHILD_DELAY = 0.35     # politeness between sub-page requests (seconds)
TOC_TEXT_MAX = 20000   # only crawl sub-pages when the landing looks like a short TOC

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")
INDEX = os.path.join(ROOT, "index.html")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


class SourceParser(HTMLParser):
    """Walk index.html, tracking the current civilization / thinker / work so each
    <a class="src"> link can be emitted with full context."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.civ = self.thinker = self.work = ""
        self._cap = None          # which field we are currently accumulating
        self._buf = []
        self._a = None            # current anchor being captured
        self.records = []

    def _classes(self, attrs):
        d = dict(attrs)
        return d, set((d.get("class") or "").split())

    def handle_starttag(self, tag, attrs):
        d, cls = self._classes(attrs)
        if tag == "span" and "cname" in cls:
            self._cap, self._buf = "civ", []
        elif tag == "span" and "pname" in cls:
            self._cap, self._buf = "thinker", []
        elif tag == "span" and "wtitle" in cls:
            self._cap, self._buf = "work", []
        elif tag == "a" and "src" in cls:
            self._a = {"href": d.get("href", ""),
                       "kind": "alt" if "alt" in cls else "primary"}
            self._buf2 = []

    def handle_endtag(self, tag):
        if tag == "span" and self._cap:
            val = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            setattr(self, self._cap, val)
            self._cap = None
        elif tag == "a" and self._a is not None:
            label = re.sub(r"\s+", " ", "".join(getattr(self, "_buf2", []))).strip()
            href = self._a["href"]
            if href.startswith("http"):
                self.records.append({
                    "civ": self.civ, "thinker": self.thinker, "work": self.work,
                    "url": href, "label": label, "kind": self._a["kind"],
                })
            self._a = None

    def handle_data(self, data):
        if self._cap:
            self._buf.append(data)
        if self._a is not None:
            self._buf2.append(data)


def parse_index():
    with open(INDEX, encoding="utf-8") as f:
        html = f.read()
    p = SourceParser()
    p.feed(html)
    for i, r in enumerate(p.records):
        r["id"] = f"S{i:03d}"
        r["url_id"] = url_to_id(r["url"])
    return p.records


def expand_children(url, html):
    """For table-of-contents pages, return the URLs of the actual content sub-pages.
    Handles ctext.org work pages (relative `work-slug/chapter` links) and
    sacred-texts.com `index.htm` pages (sibling `*.htm` files in the same folder)."""
    m = re.match(r"https?://([^/]+)(/.*)?$", url)
    host = (m.group(1) if m else "").replace("www.", "")
    path = (m.group(2) or "/") if m else "/"
    hrefs = [h.replace("&amp;", "&") for h in re.findall(r'href="([^"]+)"', html)]
    kids = []
    if host == "ctext.org":
        parts = path.strip("/").split("/")
        if len(parts) == 1 and parts[0]:                 # a single work landing page
            slug = parts[0]
            for h in hrefs:
                if h.startswith(slug + "/") and "?" not in h and "#" not in h:
                    kids.append("https://ctext.org/" + h)
    elif host == "sacred-texts.com" and path.endswith("index.htm"):
        base = url.rsplit("/", 1)[0] + "/"
        for h in hrefs:
            if (h.endswith(".htm") and not h.startswith("http")
                    and "/" not in h and h != "index.htm"):
                kids.append(urljoin(base, h))
    seen, out = set(), []
    for k in kids:
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def download(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=18, allow_redirects=True)
        ct = r.headers.get("Content-Type", "")
        ok = r.status_code == 200 and ("html" in ct or "text" in ct or ct == "")
        return {
            "status": "ok" if ok else f"http_{r.status_code}",
            "http_code": r.status_code, "content_type": ct,
            "final_url": r.url, "bytes": len(r.content),
            "html": r.text if ok else "",
        }
    except Exception as e:
        return {"status": "error", "http_code": 0, "content_type": "",
                "final_url": url, "bytes": 0, "html": "", "error": str(e)[:200]}


def main():
    os.makedirs(RAW, exist_ok=True)
    records = parse_index()
    with open(os.path.join(DATA, "sources.json"), "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    unique = {}
    for r in records:
        unique.setdefault(r["url_id"], r["url"])
    print(f"Listed source links: {len(records)}  |  unique URLs: {len(unique)}")

    downloads = {}
    for n, (uid, url) in enumerate(sorted(unique.items()), 1):
        res = download(url)
        txt_path = html_path = ""
        chars = 0
        n_children = 0
        if res["html"]:
            html_path = os.path.join(RAW, uid + ".html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(res["html"])
            text = html_to_text(res["html"])
            # if the landing page is a short table of contents, crawl its content sub-pages
            children = expand_children(url, res["html"]) if len(text) < TOC_TEXT_MAX else []
            for c in children[:MAX_CHILDREN]:
                cres = download(c)
                if cres["html"]:
                    ctxt = html_to_text(cres["html"])
                    if len(ctxt) > 40:
                        text += "\n\n" + ctxt
                        n_children += 1
                time.sleep(CHILD_DELAY)
            chars = len(text)
            txt_path = os.path.join(RAW, uid + ".txt")
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
        downloads[uid] = {
            "url": url, "status": res["status"], "http_code": res["http_code"],
            "content_type": res["content_type"], "bytes": res["bytes"],
            "text_chars": chars, "sub_pages": n_children,
            "html_file": os.path.relpath(html_path, ROOT) if html_path else "",
            "text_file": os.path.relpath(txt_path, ROOT) if txt_path else "",
        }
        if "error" in res:
            downloads[uid]["error"] = res["error"]
        flag = "OK " if res["status"] == "ok" else "•• "
        sub = f" +{n_children} sub-pages" if n_children else ""
        print(f"  [{n:2}/{len(unique)}] {flag}{res['status']:10} {chars:>8}c{sub}  {url}")
        time.sleep(0.6)

    with open(os.path.join(DATA, "downloads.json"), "w", encoding="utf-8") as f:
        json.dump(downloads, f, ensure_ascii=False, indent=2)

    ok = sum(1 for d in downloads.values() if d["status"] == "ok")
    tot = sum(d["text_chars"] for d in downloads.values())
    print(f"\nDownloaded OK: {ok}/{len(unique)}  |  total text captured: {tot:,} chars")
    print("Wrote data/sources.json, data/downloads.json, data/raw/*")


if __name__ == "__main__":
    main()
