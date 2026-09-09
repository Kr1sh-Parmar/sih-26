"""Fetch the face models into models/. BUILD TIME ONLY.

    python scripts/fetch_face_models.py

This is the one place in the repository allowed to reach the network for a
model, and it never runs at inspection time - the same boundary
`data/tools/train_fields.py` sits on. The screening process loads what this
leaves behind and nothing else; pulling the plug after this has run changes
nothing (CLAUDE.md rule 3).

**Why the models and not the `insightface` package.** `FaceAnalysis` downloads
its own weights on first use, into a home directory, at whatever moment the
first traveller arrives. That is precisely the runtime network call rule 3
forbids, and it would be invisible in a demo until the cable came out. It also
pulls scikit-image and cython in for a detector we can run on the ONNX Runtime
session already in the process. So: take the two ONNX files out of the pack and
run them ourselves. The cost is about a hundred lines of SCRFD decode and a
five-point alignment, both in `modules/face/`.

**Why `buffalo_sc` and not `buffalo_l`.** The Tier 1 face budget is 320 ms for
*two* faces plus passive liveness (TECHNICAL-SPEC.md section 2, L6).
TECHNICAL-SPEC section 4 puts `buffalo_l` at 160 ms per face, which spends the
whole budget before liveness runs. `buffalo_sc` is the same pipeline at a
fraction of the cost: 15 MB against 289 MB. It is a real accuracy trade and it
is written down in data/FACE.md rather than hidden. Pass `--pack buffalo_l` to
measure the other side of it.
"""
import argparse
import hashlib
import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

BASE = "https://github.com/deepinsight/insightface/releases/download/v0.7/"

#: Logical name in core/registry.py -> the file inside the pack. Only these two
#: are extracted; the packs also carry landmark and gender/age models we neither
#: need nor want warm in the process.
WANTED = {
    "buffalo_sc": {"face_detector": "det_500m.onnx",
                   "face_embedding": "w600k_mbf.onnx"},
    "buffalo_s": {"face_detector": "det_500m.onnx",
                  "face_embedding": "w600k_mbf.onnx"},
    "buffalo_l": {"face_detector": "det_10g.onnx",
                  "face_embedding": "w600k_r50.onnx"},
}

#: What each model expects, recorded in the sidecar so the module reads it
#: rather than hardcoding - the same rule the field detector follows.
SHAPES = {
    "face_detector": {"imgsz": 320, "task": "face detection, SCRFD"},
    "face_embedding": {"imgsz": 112, "task": "face embedding, ArcFace, 512-d"},
}


def download(pack: str) -> bytes:
    url = f"{BASE}{pack}.zip"
    print(f"fetching {url}")
    with urllib.request.urlopen(url, timeout=300) as response:
        data = response.read()
    print(f"  {len(data) / 1e6:.1f} MB")
    return data


def extract(pack: str, blob: bytes) -> dict:
    MODELS.mkdir(parents=True, exist_ok=True)
    written = {}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        members = {Path(n).name: n for n in archive.namelist()}
        for logical, filename in WANTED[pack].items():
            if filename not in members:
                sys.exit(f"{filename} is not in {pack}.zip; it holds "
                         f"{sorted(members)}")
            payload = archive.read(members[filename])
            target = MODELS / f"{logical}.onnx"
            target.write_bytes(payload)

            meta = {
                "name": logical,
                "source": f"insightface {pack}/{filename}",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size_mb": round(len(payload) / 1e6, 2),
                "precision": "fp32",
                **SHAPES[logical],
            }
            (MODELS / f"{logical}.json").write_text(json.dumps(meta, indent=2),
                                                    encoding="utf-8")
            written[logical] = meta
            print(f"  {target.relative_to(ROOT)}  {meta['size_mb']} MB  "
                  f"{meta['sha256'][:12]}")
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", default="buffalo_sc", choices=sorted(WANTED))
    parser.add_argument("--force", action="store_true",
                        help="re-download even if the files are already here")
    args = parser.parse_args()

    have = all((MODELS / f"{n}.onnx").exists() for n in WANTED[args.pack])
    if have and not args.force:
        print(f"models/ already holds the face models; --force to replace them")
        return 0

    extract(args.pack, download(args.pack))
    print("\nnothing else fetches at runtime. Verify with:\n"
          "  python -c \"from core import registry; print(registry.warm())\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
