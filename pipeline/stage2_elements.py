"""
Stage 2 — Break all text into sentence-level elements, in a uniform format.

  * Segments every downloaded source into clean prose sentences  -> data/sentences.json
  * Emits the curated atomic concept/rule elements                -> data/elements.json
    (each enriched with civ / school / native name / link to the original text, and
     with real supporting sentences pulled from the downloaded corpus as "evidence").
"""
import os
import json

import re
from util import url_to_id, sentence_split, good_sentence, clean_corpus_text, html_to_text
from knowledge import THEMES, THINKER, ELEMENTS, QUOTES, TERMS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
RAW = os.path.join(DATA, "raw")

MAX_SENTENCES_PER_SOURCE = 400
STOP = set("the a an and or of to in is are be that this with for as it its by on "
           "from at which not but his her their they them he she we you your our all "
           "one two who what when how than then so if no nor can may will shall into "
           "do does did done has have had been being more most such only own same".split())


def load_text(url):
    path = os.path.join(RAW, url_to_id(url) + ".txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    return ""


def kw_tokens(el):
    toks = set(w for w in el["keywords"].lower().split() if len(w) > 3 and w not in STOP)
    # add salient words from the element text itself
    for w in el["text"].lower().replace(",", " ").replace(".", " ").split():
        w = w.strip("();:'\"")
        if len(w) > 4 and w not in STOP:
            toks.add(w)
    return toks


_LANDING = {}
def landing_text(uid):
    """Whitespace-normalised visible text of the source's OWN landing page (its <id>.html),
    excluding the child pages that stage 1 concatenated into <id>.txt. This is what the
    linked source_url actually shows, so a text-fragment verified here will highlight there."""
    if uid in _LANDING:
        return _LANDING[uid]
    p = os.path.join(RAW, uid + ".html")
    t = ""
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                t = re.sub(r"\s+", " ", html_to_text(f.read())).strip()
        except Exception:
            t = ""
    _LANDING[uid] = t
    return t


def _window(sent, hay):
    """Longest short verbatim window (<=12 words) of `sent` present in `hay`, else ''."""
    w = re.sub(r"\s+", " ", sent).strip().split()
    for L in (12, 8, 6):
        if len(w) < L:
            s = " ".join(w)
            if s and s in hay:
                return s
            continue
        for i in range(len(w) - L + 1):
            c = " ".join(w[i:i + L])
            if c in hay:
                return c
    s = " ".join(w)
    return s if s and s in hay else ""


def verified_frag(candidates, hay):
    """First candidate (or short window of it) that is verbatim on the landing page, else ''."""
    if not hay:
        return ""
    for c in candidates:
        if not c:
            continue
        cn = re.sub(r"\s+", " ", c).strip()
        if cn and cn in hay:
            return cn if len(cn.split()) <= 12 else _window(c, hay)
        w = _window(c, hay)
        if w:
            return w
    return ""


def main():
    # ---- 1. sentence-level segmentation of the whole corpus (cached) -------
    # Segmenting the full corpus is the slowest step, but it only depends on
    # data/raw/*, which is unchanged when we merely edit knowledge.py. So reuse
    # data/sentences.json unless a raw file is newer than it.
    SENT_PATH = os.path.join(DATA, "sentences.json")
    raw_mtime = max((os.path.getmtime(os.path.join(RAW, f))
                     for f in os.listdir(RAW) if f.endswith(".txt")), default=0)
    if os.path.exists(SENT_PATH) and os.path.getmtime(SENT_PATH) >= raw_mtime:
        with open(SENT_PATH, encoding="utf-8") as f:
            sentences = json.load(f)
        total = sum(len(v) for v in sentences.values())
        print(f"Segmented corpus: {total:,} sentences from {len(sentences)} sources (cached)")
    else:
        sentences = {}
        for fn in sorted(os.listdir(RAW)):
            if not fn.endswith(".txt"):
                continue
            with open(os.path.join(RAW, fn), encoding="utf-8") as f:
                text = clean_corpus_text(f.read())
            good = [s for s in sentence_split(text) if good_sentence(s)][:MAX_SENTENCES_PER_SOURCE]
            if good:
                sentences[fn[:-4]] = good
        with open(SENT_PATH, "w", encoding="utf-8") as f:
            json.dump(sentences, f, ensure_ascii=False, indent=1)
        total = sum(len(v) for v in sentences.values())
        print(f"Segmented corpus: {total:,} clean prose sentences from {len(sentences)} sources")
    sent_index = {uid: [(s.lower(), s) for s in good] for uid, good in sentences.items()}

    # ---- 2. build the uniform element store --------------------------------
    out = []
    evidence_hits = 0
    frag_hits = 0
    for el in ELEMENTS:
        native, civ, school, source = THINKER[el["thinker"]]
        toks = kw_tokens(el)

        # find supporting sentences in this thinker's downloaded original text
        evidence = []
        uid = url_to_id(source)
        for low, orig in sent_index.get(uid, []):
            hits = sum(1 for t in toks if t in low)
            if hits >= 2:
                evidence.append((hits, orig))
        evidence.sort(key=lambda x: (-x[0], len(x[1])))
        evidence = [{"text": o, "source_url": source} for _, o in evidence[:2]]
        if evidence:
            evidence_hits += 1

        # verify highlight targets against the source's OWN landing page (not crawled children)
        land = landing_text(uid)
        for ev in evidence:
            ev["frag"] = verified_frag([ev["text"]], land)
        qcands = list(QUOTES[el["id"]]) if el["id"] in QUOTES else []
        _term = TERMS.get(el["id"])
        if _term:
            qcands.append(_term[0])
        qcands += [ev["text"] for ev in evidence] + [el["text"]]
        quote_frag = verified_frag(qcands, land)
        if quote_frag:
            frag_hits += 1

        out.append({
            "id": el["id"],
            "text": el["text"],
            "type": el["type"],
            "theme": el["theme"],
            "theme_label": THEMES[el["theme"]][0],
            "stance": el["stance"],
            "thinker": el["thinker"],
            "thinker_native": native,
            "civ": civ,
            "school": school,
            "source_url": source,
            "keywords": sorted(toks),
            "quote": ({"o": QUOTES[el["id"]][0], "e": QUOTES[el["id"]][1]}
                      if el["id"] in QUOTES else None),
            "evidence": evidence,
            "frag": quote_frag,   # verified verbatim snippet present on the linked page ("" if none)
        })

    # integrity checks
    ids = [e["id"] for e in out]
    assert len(ids) == len(set(ids)), "duplicate element ids!"
    for e in out:
        assert e["theme"] in THEMES, e["theme"]

    with open(os.path.join(DATA, "elements.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    civs = {}
    for e in out:
        civs[e["civ"]] = civs.get(e["civ"], 0) + 1
    print(f"Elements: {len(out)}  across {len(civs)} civilizations")
    print("  " + "  ".join(f"{c}:{n}" for c, n in sorted(civs.items(), key=lambda x: -x[1])))
    print(f"Elements with textual evidence pulled from originals: {evidence_hits}/{len(out)}")
    print(f"Elements whose quote is verifiably highlightable on the linked page: {frag_hits}/{len(out)}")
    print("Wrote data/sentences.json, data/elements.json")


if __name__ == "__main__":
    main()
