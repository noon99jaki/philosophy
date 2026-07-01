#!/usr/bin/env python3
"""
pipeline.py — run the whole philosophy-taxonomy pipeline end to end.

    python3 pipeline/pipeline.py                 # all 4 stages (re-downloads sources)
    python3 pipeline/pipeline.py --no-download   # reuse data/raw, run stages 2-4
    python3 pipeline/pipeline.py --only 3         # run a single stage

Stages
    1  download   sources listed in index.html  ->  data/raw, data/sources.json
    2  elementize sentences + atomic elements    ->  data/sentences.json, data/elements.json
    3  relate     similarity/equivalence/contra  ->  data/relations.json, data/graph.json
    4  visualize  assemble + render              ->  data/taxonomy.json, taxonomy.html
"""
import os
import sys
import time
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
STAGES = [
    ("1 · download",   "stage1_download.py"),
    ("2 · elementize", "stage2_elements.py"),
    ("3 · relate",     "stage3_relations.py"),
    ("4 · visualize",  "stage4_taxonomy.py"),
]


def run(script):
    subprocess.run([sys.executable, os.path.join(HERE, script)], check=True)


def main():
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        only = args[args.index("--only") + 1]
    skip_dl = "--no-download" in args

    t0 = time.time()
    for i, (name, script) in enumerate(STAGES, 1):
        if only and str(i) != only:
            continue
        if i == 1 and skip_dl:
            print(f"\n=== STAGE {name} — SKIPPED (--no-download) ===")
            continue
        print(f"\n{'='*64}\n=== STAGE {name}\n{'='*64}")
        run(script)
    print(f"\n✓ pipeline complete in {time.time()-t0:.1f}s  ->  open taxonomy.html")


if __name__ == "__main__":
    main()
