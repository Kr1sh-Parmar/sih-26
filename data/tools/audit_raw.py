"""Instances per class for every dataset under data/raw/. Run before mapping.

A Universe project's advertised class list is not evidence that the images are
annotated: at-in/bangladeshi-passport-fields advertises 33 classes over 200
images and ships 27 boxes on ONE image. This is the check that catches that.
"""
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "data" / "raw"
for y in sorted(ROOT.rglob("data.yaml")):
    d = y.parent
    names = [x.strip().strip("'\"") for x in
             re.search(r"names:\s*\[(.*?)\]", y.read_text(), re.S).group(1).split(",")]
    c, imgs, empty = Counter(), 0, 0
    for lp in d.rglob("labels/*.txt"):
        imgs += 1
        rows = [l for l in lp.read_text().split("\n") if len(l.split()) >= 5]
        empty += not rows
        c.update(int(r.split()[0]) for r in rows)
    tot = sum(c.values())
    print(f"\n{str(d.relative_to(ROOT))}  {imgs} labelled files, {empty} empty, {tot} boxes")
    if not tot:
        print("   !! NO ANNOTATIONS")
        continue
    for i, n in sorted(c.items(), key=lambda kv: -kv[1]):
        print(f"   {names[i] if i < len(names) else '?'+str(i):28} {n:6}")
