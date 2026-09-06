"""Crop N sample boxes per ontology class from the merged dataset and montage
them. If person_photo shows faces and mrz shows MRZ strips, the remap is right.
"""
import re, sys, random
from pathlib import Path
from PIL import Image, ImageDraw

root, out, n = Path(sys.argv[1]), Path(sys.argv[2]), int(sys.argv[3])
names = [x.strip().strip("'\"") for x in
         re.search(r"names:\s*\[(.*?)\]", (root/"data.yaml").read_text(), re.S).group(1).split(",")]

lbls = sorted((root/"train"/"labels").glob("*.txt"))
random.seed(1); random.shuffle(lbls)
by = {}
for lp in lbls:
    ip = next((p for p in (root/"train"/"images").glob(lp.stem + ".*")), None)
    if not ip: continue
    for line in lp.read_text().split("\n"):
        p = line.split()
        if len(p) < 5: continue
        c = int(p[0])
        if len(by.get(c, [])) >= n: continue
        by.setdefault(c, []).append((ip, *map(float, p[1:5])))

rows = []
for c in sorted(by):
    crops = []
    for ip, xc, yc, bw, bh in by[c]:
        im = Image.open(ip).convert("RGB"); W, H = im.size
        x1, y1 = max(0,int((xc-bw/2)*W)), max(0,int((yc-bh/2)*H))
        x2, y2 = min(W,int((xc+bw/2)*W)), min(H,int((yc+bh/2)*H))
        if x2-x1 < 4 or y2-y1 < 4: continue
        cr = im.crop((x1,y1,x2,y2))
        crops.append(cr.resize((max(8,int(cr.width*80/cr.height)), 80)))
    if crops: rows.append((c, crops))

lw, pad = 150, 6
W = lw + max(sum(cr.width+pad for cr in cs) for _, cs in rows) + 20
H = sum(80+pad for _ in rows) + 20
cv = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(cv)
y = 10
for c, cs in rows:
    d.text((8, y+34), f"{c:2d} {names[c]}", fill="black")
    x = lw
    for cr in cs: cv.paste(cr, (x, y)); x += cr.width + pad
    y += 80 + pad
cv.save(out); print("classes rendered:", {names[c]: len(cs) for c, cs in rows})
