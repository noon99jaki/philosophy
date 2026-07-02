"""Shared utilities for the philosophy taxonomy pipeline (stdlib only)."""
import re
import html
import hashlib
import unicodedata
from html.parser import HTMLParser

# ---------------------------------------------------------------------------
# HTML -> plain text
# ---------------------------------------------------------------------------
_SKIP = {"script", "style", "head", "noscript", "nav", "footer", "form"}
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
          "section", "article", "blockquote", "td"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self.skip_depth += 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self.skip_depth:
            self.skip_depth -= 1
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.out.append(data)


def html_to_text(raw: str) -> str:
    """Strip tags/scripts and collapse whitespace into readable plain text."""
    try:
        p = _TextExtractor()
        p.feed(raw)
        txt = "".join(p.out)
    except Exception:
        txt = re.sub(r"<[^>]+>", " ", raw)
    txt = html.unescape(txt)
    txt = re.sub(r"[ \t ]+", " ", txt)
    txt = re.sub(r"\n[ \t]*\n[ \t]*(\n[ \t]*)+", "\n\n", txt)
    txt = re.sub(r" *\n *", "\n", txt)
    return txt.strip()


# ---------------------------------------------------------------------------
# Slugs / ids
# ---------------------------------------------------------------------------
def slugify(value: str, maxlen: int = 80) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^\w\s./-]", "", value).strip().lower()
    value = re.sub(r"[\s/.]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value[:maxlen] or "item"


def url_to_id(url: str) -> str:
    m = re.match(r"https?://([^/]+)(/.*)?$", url)
    host = (m.group(1) if m else url).replace("www.", "")
    path = (m.group(2) or "") if m else ""
    s = slugify(host + path)
    if len(s) >= 80:      # slug hit the cap: long URLs differing only near the end
        s = s[:71] + "-" + hashlib.md5(url.encode()).hexdigest()[:8]   # would collide
    return s


# ---------------------------------------------------------------------------
# Sentence segmentation
# ---------------------------------------------------------------------------
_ABBR = {"mr", "mrs", "ms", "dr", "st", "vs", "etc", "e.g", "i.e", "cf",
         "ch", "no", "vol", "p", "pp", "c", "ca", "fl", "b.c", "a.d", "bce", "ce"}


def sentence_split(text: str):
    """Lightweight sentence segmentation for English prose."""
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    # protect common abbreviations
    parts = re.split(r"(?<=[.!?;])\s+(?=[\"'(\[A-Z0-9])", text)
    out = []
    for s in parts:
        s = s.strip()
        if not s:
            continue
        last = s.split()[-1].rstrip(".!?;:").lower() if s.split() else ""
        if out and last in _ABBR:
            out[-1] = out[-1] + " " + s
        else:
            out.append(s)
    return out


def clean_corpus_text(text: str) -> str:
    """Remove wiki/footnote/navigation artifacts before sentence segmentation."""
    text = text.replace("​", "").replace(" ", " ")
    text = re.sub(r"\[\s*edit\s*\]", " ", text, flags=re.I)   # Wikisource [edit] links
    text = re.sub(r"\[\d{1,3}\]", " ", text)                   # [5] footnote markers
    text = re.sub(r"\{\d{1,4}\}", " ", text)                   # {44} page markers
    text = re.sub(r"\bFragment\s+\d+\b", " ", text)            # fragment headers
    text = re.sub(r"(?m)^\s*\(\d+\)\s*", "", text)             # (55) verse numbers
    text = re.sub(r"[ \t]+", " ", text)
    return text


def good_sentence(s: str) -> bool:
    """Heuristic: keep sentences that look like real prose, not navigation/markup."""
    words = s.split()
    if not (5 <= len(words) <= 60):
        return False
    letters = sum(c.isalpha() for c in s)
    if letters < 0.6 * len(s):
        return False
    if re.search(r"(cookie|javascript|copyright|all rights|click here|home\s*\|"
                 r"|next:|previous:|sacred-texts|wikisource|table of contents|\[edit\]"
                 r"|fragment\s+\d|\bdjvu\b|font-|px;|index\b)", s, re.I):
        return False
    # too many digits (verse/line numbering)
    if sum(c.isdigit() for c in s) > 0.15 * len(s):
        return False
    return True
