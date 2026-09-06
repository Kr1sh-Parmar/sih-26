"""draw.py <root> <out.png> [n] - draw all boxes on n random train images, side by side."""
import re, sys, random
from pathlib import Path
from PIL import Image, ImageDraw
root, out = Path(sys.argv[1]), Path(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
names = [x.strip().strip("'\"") for x in
         re.search(r"names:\s*\[(.*?)\]", (root/"data.yaml").read_text(), re.S).group(1).split(",")]
lbls = [p for p in sorted((root/"train"/"labels").glob("*.txt")) if p.read_text().strip()]
random.seed(int(sys.argv[4]) if len(sys.argv) > 4 else 7); random.shuffle(lbls)
ims = []
for lp in lbls[:n]:
    ip = next((p for p in (root/"train"/"images").glob(lp.stem+".*")), None)
    if not ip: continue
    im = Image.open(ip).convert("RGB"); W, H = im.size
    s = 700/max(W, H); im = im.resize((int(W*s), int(H*s))); W, H = im.size
    d = ImageDraw.Draw(im)
    for line in lp.read_text().split("\n"):
        p = line.split()
        if len(p) < 5: continue
        c = int(p[0]); xc, yc, bw, bh = map(float, p[1:5])
        box = ((xc-bw/2)*W, (yc-bh/2)*H, (xc+bw/2)*W, (yc+bh/2)*H)
        d.rectangle(box, outline=(255, 0, 0), width=2)
        d.text((box[0]+2, box[1]+2), names[c], fill=(0, 0, 255))
    ims.append(im)
cv = Image.new("RGB", (sum(i.width+8 for i in ims), max(i.height for i in ims)), "white")
x = 0
for i in ims: cv.paste(i, (x, 0)); x += i.width+8
cv.save(out); print("ok")
