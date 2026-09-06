"""PII-free synthetic face pool for the document generator.

SFHQ (Synthetic Faces High Quality, David Beniaguev) is StyleGAN2 / Stable
Diffusion output - no real person, CC0 public domain. It replaces the 2,000
MIDV faces we lost when the European datasets went out of scope.

The full set is 81 GB; the repo ships small-sample zips, which is all the
generator needs. Resumes with a Range request - the download drops often.
"""
import sys, time, zipfile, requests
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "data" / "raw" / "face" / "sfhq"
BASE = "https://huggingface.co/datasets/bitmind/SyntheticFacesHQ/resolve/main/"
FILES = ("small-sample.zip", "small-sample-4.zip")


def fetch(name):
    tmp = OUT / name
    for attempt in range(8):
        have = tmp.stat().st_size if tmp.exists() else 0
        hdr = {"Range": f"bytes={have}-"} if have else {}
        try:
            with requests.get(BASE + name, headers=hdr, stream=True, timeout=120) as r:
                if r.status_code == 416:
                    break                      # already complete
                r.raise_for_status()
                total = have + int(r.headers.get("content-length", 0))
                with open(tmp, "ab" if have else "wb") as fh:
                    for c in r.iter_content(1 << 20):
                        fh.write(c)
            if tmp.stat().st_size >= total:
                break
        except Exception as e:
            print(f"  retry {attempt+1}: {type(e).__name__} at {have/1e6:.0f} MB", flush=True)
            time.sleep(5)
    zipfile.ZipFile(tmp).extractall(OUT)       # throws if the zip is truncated
    print(f"  {name}: {tmp.stat().st_size/1e6:.0f} MB", flush=True)
    tmp.unlink()


OUT.mkdir(parents=True, exist_ok=True)
for f in (sys.argv[1:] or FILES):
    fetch(f)
n = sum(1 for p in OUT.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
print("synthetic faces on disk:", n)
