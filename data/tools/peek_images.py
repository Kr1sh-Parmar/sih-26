"""Contact sheet of random images from a dataset. Run this on EVERY new pull.

audit_raw.py checks that boxes exist; it cannot tell you the images are the
right thing. fil-9zpqb/voter-01 shipped 146 images labelled `voter`, all of
them Albion Online screenshots, and the box audit looked perfectly healthy.
"""
import random, sys
from pathlib import Path
from PIL import Image

root, out = Path(sys.argv[1]), Path(sys.argv[2])
n = int(sys.argv[3]) if len(sys.argv) > 3 else 12
ims = [p for p in root.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
random.seed(11); random.shuffle(ims)
th = []
for p in ims[:n]:
    im = Image.open(p).convert("RGB"); im.thumbnail((320, 320)); th.append(im)
cols = 4
cv = Image.new("RGB", (cols*330, ((len(th)+cols-1)//cols)*250), "white")
for i, im in enumerate(th):
    cv.paste(im, ((i % cols)*330, (i//cols)*250))
cv.save(out); print(f"{len(ims)} images, sheet -> {out}")
