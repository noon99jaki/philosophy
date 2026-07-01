"""
Stage 4 — Assemble the visualization payload and render taxonomy.html.

Merges elements + relations + layout into one self-contained data block, computes
cross-cultural "bridges" (equivalences spanning civilizations) and "debates"
(contradictions), then injects everything into taxonomy_template.html.
"""
import os
import json

from knowledge import THEMES, TERMS, AUTHOR_ROMAN, BIRTH, ROMAN

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


def detect_lang(text):
    """Pick a speech-synthesis BCP-47 code from the dominant script of `text`."""
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            return "zh-CN"
        if 0x0370 <= o <= 0x03FF or 0x1F00 <= o <= 0x1FFF:
            return "el-GR"
        if 0x0590 <= o <= 0x05FF:
            return "he-IL"
        if 0x0900 <= o <= 0x097F:
            return "hi-IN"
        if 0x0600 <= o <= 0x06FF:
            return "fa-IR"
    return ""   # Latin / transliteration -> default voice

REL = {
    "equivalence":  {"color": "#e3b341", "label": "equivalence / agreement"},
    "similarity":   {"color": "#6fb1c9", "label": "similarity (discovered)"},
    "contradiction":{"color": "#e0524a", "label": "contradiction / debate"},
}


def main():
    els = {e["id"]: e for e in json.load(open(os.path.join(DATA, "elements.json"), encoding="utf-8"))}
    graph = json.load(open(os.path.join(DATA, "graph.json"), encoding="utf-8"))
    gnodes = {n["id"]: n for n in graph["nodes"]}
    edges = graph["edges"]

    # merge full detail into nodes
    nodes = []
    for nid, n in gnodes.items():
        e = els[nid]
        # two consistent pronunciations per concept, always both present:
        #   name  = the author / work (native name, cuneiform romanized)
        #   idea  = the concept itself (quote > native term)
        name_text = AUTHOR_ROMAN.get(e["thinker"], e["thinker_native"])
        idea_text = e["quote"]["o"] if e["quote"] else (TERMS.get(nid) or e["thinker_native"])
        nodes.append({
            "id": nid, "label": e["thinker"], "native": e["thinker_native"],
            "year": BIRTH.get(e["thinker"], ""),
            "civ": e["civ"], "color": n["color"], "school": e["school"],
            "theme": e["theme"], "theme_label": e["theme_label"], "stance": e["stance"],
            "type": e["type"], "degree": n["degree"], "x": n["x"], "y": n["y"],
            "text": e["text"], "quote": e["quote"], "source_url": e["source_url"],
            "evidence": [ev["text"] for ev in e["evidence"]],
            "speak": {"name": {"text": name_text, "lang": detect_lang(name_text),
                               "roman": ROMAN.get(name_text, "")},
                      "idea": {"text": idea_text, "lang": detect_lang(idea_text),
                               "roman": ROMAN.get(idea_text, "")}},
            "auto_cluster": n["auto_cluster"],
        })

    # themes -> stances -> ids (hierarchy for the taxonomy view)
    themes_out = []
    for key, (label, blurb, color) in THEMES.items():
        members = [e for e in els.values() if e["theme"] == key]
        stances = {}
        for e in members:
            stances.setdefault(e["stance"], []).append(e["id"])
        themes_out.append({
            "key": key, "label": label, "blurb": blurb, "color": color,
            "count": len(members),
            "stances": [{"stance": s, "ids": ids} for s, ids in
                        sorted(stances.items(), key=lambda kv: -len(kv[1]))],
        })

    civ_order = ["Mesopotamia", "Egypt", "Israel", "Persia", "India", "China", "Greece"]
    civ_colors = {n["civ"]: n["color"] for n in nodes}

    # ---- cross-cultural bridges (equivalence across civilizations) ----------
    bridges = []
    for ed in edges:
        if ed["type"] != "equivalence":
            continue
        a, b = els[ed["s"]], els[ed["t"]]
        if a["civ"] != b["civ"]:
            bridges.append({
                "a": a["id"], "b": b["id"], "ca": a["civ"], "cb": b["civ"],
                "ta": a["thinker"], "tb": b["thinker"], "theme": a["theme_label"],
                "xa": a["text"], "xb": b["text"], "score": ed["score"],
            })
    # diversify by theme, keep strongest
    bridges.sort(key=lambda x: -x["score"])
    seen, top_bridges = {}, []
    for br in bridges:
        if seen.get(br["theme"], 0) < 2:
            top_bridges.append(br)
            seen[br["theme"]] = seen.get(br["theme"], 0) + 1
    top_bridges = top_bridges[:14]

    debates = []
    for ed in edges:
        if ed["type"] != "contradiction":
            continue
        a, b = els[ed["s"]], els[ed["t"]]
        debates.append({
            "a": a["id"], "b": b["id"], "ca": a["civ"], "cb": b["civ"],
            "ta": a["thinker"], "tb": b["thinker"], "theme": a["theme_label"],
            "xa": a["text"], "xb": b["text"], "score": ed["score"],
            "cross": a["civ"] != b["civ"],
        })
    debates.sort(key=lambda x: (-int(x["cross"]), -x["score"]))
    seen2, top_debates = {}, []
    for d in debates:
        if seen2.get(d["theme"], 0) < 2:
            top_debates.append(d)
            seen2[d["theme"]] = seen2.get(d["theme"], 0) + 1
    top_debates = top_debates[:14]

    payload = {
        "stats": graph["stats"],
        "themes": themes_out,
        "civs": civ_order,
        "civColors": civ_colors,
        "relTypes": REL,
        "nodes": nodes,
        "edges": edges,
        "highlights": {"bridges": top_bridges, "debates": top_debates},
    }

    with open(os.path.join(DATA, "taxonomy.json"), "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)

    tpl = open(os.path.join(HERE, "taxonomy_template.html"), encoding="utf-8").read()
    html = tpl.replace('"__TAXONOMY_DATA__"', json.dumps(payload, ensure_ascii=False))
    out = os.path.join(ROOT, "taxonomy.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Nodes: {len(nodes)} | Edges: {len(edges)} | Bridges: {len(top_bridges)} "
          f"| Debates: {len(top_debates)}")
    print(f"Wrote data/taxonomy.json and {os.path.relpath(out, ROOT)} "
          f"({len(html):,} bytes)")


if __name__ == "__main__":
    main()
