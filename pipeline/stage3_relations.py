"""
Stage 3 — Automatically identify similarity / equivalence / contradiction.

  * Vectorises every element with a hand-rolled TF-IDF (numpy) and computes the
    full cosine-similarity matrix.
  * Classifies each pair:
        equivalence   – same theme & same stance (cross-cultural agreement)
        similarity    – high TF-IDF cosine across different stances (discovered)
        contradiction – opposed stance on a shared theme, or an antonym cue,
                        or a documented cross-theme debate (CROSS_CONTRA)
  * Clusters the elements two ways: by THEME (the taxonomy) and by unsupervised
    agglomerative clustering on the cosine distance (scipy) — the two are compared.
  * Computes a force-directed 2-D layout so taxonomy.html opens already arranged.

Outputs: data/relations.json, data/graph.json
"""
import os
import re
import json
import itertools
import numpy as np

from knowledge import THEMES, OPPOSITIONS, CROSS_CONTRA, CAUSATION, ANTONYMS, THINKER

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

SIM_EDGE = 0.17      # min cosine to draw a discovered "similarity" edge
SIM_TOPK = 4         # keep at most this many similarity edges per node
EQUIV_FLOOR = 0.45   # weight floor for same-stance equivalence edges
N_CLUSTERS = 15      # target for unsupervised agglomerative clustering

STOP = set("the a an and or of to in is are be that this with for as it its by on from "
           "at which not but his her their they them he she we you your our all one who "
           "what when how than then so if no nor can may will shall into do does did has "
           "have had been being more most such only own same may must each every there "
           "out up about itself other".split())

# seven well-separated hues (red/saffron/sand/teal/azure/violet/magenta) — green is
# reserved for causation edges; China red, India saffron, Egypt teal stay as anchors
CIV_COLOR = {"Mesopotamia": "#d9c34a", "Egypt": "#35c0ae", "Israel": "#9b7bf0",
             "Persia": "#e35bb4", "India": "#f0912d", "China": "#e04f4a", "Greece": "#4f9df7"}


def tokenize(s):
    return [w for w in re.findall(r"[a-zA-Z]+", s.lower()) if len(w) > 2 and w not in STOP]


def build_tfidf(els):
    # bag = element text + keywords (weighted x2) + stance words
    docs = []
    for e in els:
        toks = tokenize(e["text"]) + tokenize(" ".join(e["keywords"])) * 2 \
            + tokenize(e["stance"].replace("-", " "))
        docs.append(toks)
    vocab = {}
    for d in docs:
        for w in set(d):
            vocab[w] = vocab.get(w, 0) + 1
    terms = sorted(vocab)
    idx = {t: i for i, t in enumerate(terms)}
    N = len(docs)
    idf = np.array([np.log((N + 1) / (vocab[t] + 1)) + 1 for t in terms])
    M = np.zeros((N, len(terms)))
    for i, d in enumerate(docs):
        for w in d:
            M[i, idx[w]] += 1
    M = M * idf
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1
    return M / norms


def agglomerative_average(D, k):
    """Average-linkage agglomerative clustering (Lance-Williams), pure numpy."""
    n = D.shape[0]
    Dc = D.astype(float).copy()
    np.fill_diagonal(Dc, np.inf)
    active = list(range(n))
    members = {i: [i] for i in range(n)}
    sizes = {i: 1 for i in range(n)}
    while len(active) > k:
        sub = Dc[np.ix_(active, active)]
        ai, aj = divmod(int(np.argmin(sub)), len(active))
        a, b = active[ai], active[aj]
        sa, sb = sizes[a], sizes[b]
        for c in active:
            if c in (a, b):
                continue
            Dc[a, c] = Dc[c, a] = (sa * Dc[a, c] + sb * Dc[b, c]) / (sa + sb)
        members[a] += members[b]
        sizes[a] = sa + sb
        active.remove(b)
        Dc[b, :] = np.inf
        Dc[:, b] = np.inf
    labels = np.zeros(n, dtype=int)
    for ci, a in enumerate(active, 1):
        for m in members[a]:
            labels[m] = ci
    return labels


def opposed(theme, a, b):
    for x, y in OPPOSITIONS.get(theme, []):
        if {a, b} == {x, y}:
            return True
    return False


def antonym_cue(ei, ej):
    bi = (ei["text"] + " " + " ".join(ei["keywords"])).lower()
    bj = (ej["text"] + " " + " ".join(ej["keywords"])).lower()
    for a, b in ANTONYMS:
        if (a in bi and b in bj) or (a in bj and b in bi):
            return True
    return False


def fr_layout(n, edges, themes_idx, theme_keys, iterations=400, seed=7):
    """Lightweight Fruchterman-Reingold with a pull toward each node's theme anchor."""
    rng = np.random.default_rng(seed)
    # theme anchors arranged on a circle
    T = len(theme_keys)
    tk_i = {k: i for i, k in enumerate(theme_keys)}
    ang = {k: 2 * np.pi * i / T for i, k in enumerate(theme_keys)}
    anchors = np.array([[np.cos(ang[k]), np.sin(ang[k])] for k in theme_keys]) * 5.0
    pos = np.array([anchors[tk_i[themes_idx[i]]] for i in range(n)], dtype=float)
    pos += rng.normal(0, 0.45, pos.shape)
    k = 0.9
    ew = {}                                           # unique undirected edges, max weight
    for s, t, w in edges:
        key = (s, t) if s < t else (t, s)
        ew[key] = max(ew.get(key, 0.0), w)
    if ew:
        Es = np.array([e[0] for e in ew], dtype=int)
        Et = np.array([e[1] for e in ew], dtype=int)
        Ew = np.array(list(ew.values()), dtype=float)
    else:
        Es = Et = np.array([], dtype=int); Ew = np.array([])
    anchor_pos = np.array([anchors[tk_i[themes_idx[i]]] for i in range(n)])
    ti = np.array([tk_i[themes_idx[i]] for i in range(n)])   # node -> theme index
    if n > 300:
        iterations = 250                             # keep large graphs tractable
    temp = 2.2
    for _ in range(iterations):
        diff = pos[:, None, :] - pos[None, :, :]       # (n,n,2) repulsion, fully vectorised
        dist = np.sqrt((diff * diff).sum(2)); dist[dist < 0.01] = 0.01
        rep = (k * k) / dist; np.fill_diagonal(rep, 0.0)
        disp = (diff * (rep / dist)[:, :, None]).sum(1)
        if len(Es):                                   # attraction along edges only (O(E), vectorised)
            d = pos[Es] - pos[Et]
            dl = np.linalg.norm(d, axis=1); dl[dl < 1e-6] = 1e-6
            f = d / dl[:, None] * (dl * dl / k * Ew)[:, None]
            np.add.at(disp, Es, -f)
            np.add.at(disp, Et, f)
        disp += (anchor_pos - pos) * 0.30             # theme gravity (vectorised)
        # pull toward the theme's CURRENT centroid too: unlike the fixed anchors this is
        # translation-free, so it tightens each theme around wherever it naturally settles
        sums = np.zeros((T, 2)); np.add.at(sums, ti, pos)
        cnt = np.bincount(ti, minlength=T).astype(float)[:, None]
        cent = sums / np.maximum(cnt, 1)
        disp += (cent[ti] - pos) * 1.20
        length = np.linalg.norm(disp, axis=1, keepdims=True)
        length[length < 1e-6] = 1e-6
        pos += disp / length * np.minimum(length, temp)
        temp = max(0.05, temp * 0.985)
    # normalize to ~[-540,540] box
    pos -= pos.mean(0)
    span = np.abs(pos).max() or 1
    pos = pos / span * 540
    return pos


def main():
    els = json.load(open(os.path.join(DATA, "elements.json"), encoding="utf-8"))
    n = len(els)
    id2i = {e["id"]: i for i, e in enumerate(els)}
    P = build_tfidf(els)
    S = np.einsum("ik,jk->ij", P, P)   # cosine sim (P is L2-normalised); avoids BLAS warns

    cross = set()
    for a, b in CROSS_CONTRA:
        if a in id2i and b in id2i:
            cross.add(frozenset((a, b)))

    causal = set()                       # keep causal pairs out of the other classifiers
    for a, b, _ in CAUSATION:
        assert a in id2i, f"CAUSATION: unknown element {a}"
        assert b in id2i, f"CAUSATION: unknown element {b}"
        causal.add(frozenset((a, b)))

    relations = []
    sim_candidates = []  # (i,j,sim) to be filtered top-k
    for i, j in itertools.combinations(range(n), 2):
        ei, ej = els[i], els[j]
        sim = float(S[i, j])
        same_theme = ei["theme"] == ej["theme"]
        same_stance = ei["stance"] == ej["stance"]
        pair = frozenset((ei["id"], ej["id"]))

        if pair in causal:
            continue
        if pair in cross:
            relations.append((i, j, "contradiction", round(max(sim, 0.5), 3),
                              "documented cross-theme debate"))
        elif same_theme and same_stance:
            relations.append((i, j, "equivalence", round(max(sim, EQUIV_FLOOR), 3),
                              f"shared stance “{ei['stance']}” on {ei['theme']}"))
        elif same_theme and opposed(ei["theme"], ei["stance"], ej["stance"]):
            w = 0.5 + 0.5 * sim + (0.15 if antonym_cue(ei, ej) else 0)
            relations.append((i, j, "contradiction", round(min(w, 1.0), 3),
                              f"opposed stances on {ei['theme']}"))
        elif same_theme and not same_stance and antonym_cue(ei, ej) and sim >= 0.12:
            relations.append((i, j, "contradiction", round(0.5 + 0.4 * sim, 3),
                              "antonym cue on shared theme (discovered)"))
        elif sim >= SIM_EDGE:
            sim_candidates.append((i, j, sim))

    # keep top-k similarity edges per node to limit clutter
    by_node = {}
    for i, j, sim in sim_candidates:
        by_node.setdefault(i, []).append((sim, j))
        by_node.setdefault(j, []).append((sim, i))
    keep = set()
    for node, lst in by_node.items():
        for sim, other in sorted(lst, reverse=True)[:SIM_TOPK]:
            keep.add((min(node, other), max(node, other), round(sim, 3)))
    for i, j, sim in keep:
        relations.append((i, j, "similarity", sim, "high TF-IDF cosine (discovered)"))

    # curated causal / grounding links — DIRECTED: s is the cause, t the effect
    for a, b, why in CAUSATION:
        relations.append((id2i[a], id2i[b], "causation",
                          round(max(float(S[id2i[a], id2i[b]]), 0.6), 3), why))

    # ---- unsupervised agglomerative clustering on cosine distance ----------
    D = 1.0 - S
    np.fill_diagonal(D, 0.0)
    D = np.clip((D + D.T) / 2, 0, 2)
    auto = agglomerative_average(D, N_CLUSTERS)
    # label each auto-cluster by its dominant theme
    cl_theme = {}
    for c in set(auto):
        members = [els[i]["theme"] for i in range(n) if auto[i] == c]
        cl_theme[c] = max(set(members), key=members.count)

    # ---- degrees + layout --------------------------------------------------
    deg = [0] * n
    edges_for_layout = []
    for i, j, typ, w, _ in relations:
        deg[i] += 1
        deg[j] += 1
        pull = {"equivalence": 1.0, "similarity": 0.7, "contradiction": 0.15,
                "causation": 0.9}[typ]
        edges_for_layout.append((i, j, pull * max(w, 0.2)))

    themes_idx = [e["theme"] for e in els]
    pos = fr_layout(n, edges_for_layout, themes_idx, list(THEMES.keys()))

    nodes = []
    for i, e in enumerate(els):
        nodes.append({
            "id": e["id"], "label": e["thinker"], "text": e["text"],
            "civ": e["civ"], "color": CIV_COLOR.get(e["civ"], "#999"),
            "theme": e["theme"], "theme_label": e["theme_label"], "stance": e["stance"],
            "type": e["type"], "degree": deg[i],
            "auto_cluster": int(auto[i]), "auto_cluster_theme": cl_theme[auto[i]],
            "x": round(float(pos[i, 0]), 1), "y": round(float(pos[i, 1]), 1),
        })

    edges = [{"s": els[i]["id"], "t": els[j]["id"], "type": typ,
              "score": w, "rationale": why} for i, j, typ, w, why in relations]

    counts = {}
    for e in edges:
        counts[e["type"]] = counts.get(e["type"], 0) + 1

    # agreement between unsupervised clustering and the theme taxonomy
    agree = sum(1 for i in range(n) if cl_theme[auto[i]] == els[i]["theme"]) / n

    json.dump(edges, open(os.path.join(DATA, "relations.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"nodes": nodes, "edges": edges,
               "stats": {"elements": n, "edges": len(edges), "by_type": counts,
                         "auto_clusters": int(N_CLUSTERS),
                         "cluster_theme_agreement": round(agree, 3)}},
              open(os.path.join(DATA, "graph.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"Pairs evaluated: {n*(n-1)//2:,}   Edges kept: {len(edges)}")
    for t, c in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {t:14} {c}")
    print(f"Unsupervised clusters: {N_CLUSTERS} | agreement with theme taxonomy: {agree:.0%}")
    print("Wrote data/relations.json, data/graph.json")


if __name__ == "__main__":
    main()
