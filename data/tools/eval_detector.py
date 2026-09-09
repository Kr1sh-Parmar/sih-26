"""Recall of the shipped detector on a YOLO-format split. BUILD TIME ONLY.

    python data/tools/eval_detector.py --split data/processed/fields/test
    python data/tools/eval_detector.py --split data/processed/generated/test

Why this exists and `train_fields.py` does not answer it: the sidecar carries
ultralytics' numbers for the `.pt` on the split it was trained against. Two
things about that are the wrong question at inspection time.

The first is *what* is measured - the shipped artefact is the int8 ONNX read
through `modules.extraction.detect`, letterboxing, NMS and all, and a
quantisation or a decode bug lives exactly in the gap between the two.

The second is *where*. The detector trained on Roboflow document photographs;
the demo, the rehearsal and every screenshot run on `data/generator/` renders,
and there are zero generated cards in the training split. That is a domain gap,
and an unmeasured domain gap in a submission is a claim waiting to be taken
apart. Point this at both splits and quote both numbers.

Recall, not mAP. A field the detector never proposes is a field OCR never reads
and a coverage point the document never earns - that is the failure an officer
sees. Precision costs one wasted crop that fails to normalise and is discarded.
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core import registry                                          # noqa: E402
from modules.extraction import detect                              # noqa: E402

IOU_MATCH = 0.5


def iou(a, b) -> float:
    """Intersection over union of two xyxy boxes."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def truth(label: Path, names: list[str], w: int, h: int) -> list[tuple[str, tuple]]:
    """YOLO `cls cx cy w h`, normalised, to [(class_name, xyxy_pixels)]."""
    out = []
    for line in label.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        cid, cx, cy, bw, bh = int(parts[0]), *(float(v) for v in parts[1:5])
        out.append((names[cid], (
            (cx - bw / 2) * w, (cy - bh / 2) * h,
            (cx + bw / 2) * w, (cy + bh / 2) * h,
        )))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", required=True,
                        help="directory holding images/ and labels/")
    parser.add_argument("--conf", type=float, default=detect.CONF_THRESHOLD)
    parser.add_argument("--limit", type=int, default=0, help="0 = all")
    args = parser.parse_args()

    names = registry.metadata(registry.FIELD_DETECTOR).get("classes")
    if not names:
        print("no detector sidecar in models/ - nothing to evaluate")
        return 1

    split = Path(args.split)
    images = sorted((split / "images").glob("*"))
    if args.limit:
        images = images[:args.limit]
    if not images:
        print(f"no images under {split / 'images'}")
        return 1

    found = defaultdict(int)
    total = defaultdict(int)
    per_doc = defaultdict(lambda: [0, 0])

    for path in images:
        label = split / "labels" / f"{path.stem}.txt"
        if not label.exists():
            continue
        image = cv2.imread(str(path))
        if image is None:
            continue
        h, w = image.shape[:2]
        predictions = detect.detect(image, conf=args.conf)
        doc = path.stem.split("__")[0]

        for cls, box in truth(label, names, w, h):
            total[cls] += 1
            per_doc[doc][1] += 1
            hit = any(p["class"] == cls and iou(p["box"], box) >= IOU_MATCH
                      for p in predictions)
            if hit:
                found[cls] += 1
                per_doc[doc][0] += 1

    every = sum(total.values())
    if not every:
        print("no labelled instances found")
        return 1

    print(f"\n{split}  conf>={args.conf}  IoU>={IOU_MATCH}  {len(images)} images")
    print(f"\n  {'class':20s} {'recall':>8s}  {'found':>6s} / {'truth':>6s}")
    for cls in names:
        if not total[cls]:
            print(f"  {cls:20s} {'--':>8s}  {'':>6s}   {0:>6d}   (no instances)")
            continue
        print(f"  {cls:20s} {found[cls] / total[cls]:8.3f}  "
              f"{found[cls]:6d} / {total[cls]:6d}")

    print(f"\n  {'by document':20s} {'recall':>8s}")
    for doc in sorted(per_doc):
        hit, seen = per_doc[doc]
        print(f"  {doc:20s} {hit / seen if seen else 0:8.3f}  {hit:6d} / {seen:6d}")

    print(f"\n  {'OVERALL':20s} {sum(found.values()) / every:8.3f}  "
          f"{sum(found.values()):6d} / {every:6d}\n")
    return 0


def demo() -> None:
    """Self-check on the only non-obvious arithmetic here."""
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
    assert abs(iou((0, 0, 10, 10), (5, 0, 15, 10)) - 1 / 3) < 1e-9
    # Touching edges share no area.
    assert iou((0, 0, 10, 10), (10, 0, 20, 10)) == 0.0

    import tempfile
    names = ["a", "b"]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "l.txt"
        p.write_text("1 0.5 0.5 0.5 0.5\n", encoding="utf-8")
        (cls, box), = truth(p, names, 100, 100)
        assert cls == "b", cls
        assert box == (25.0, 25.0, 75.0, 75.0), box
    print("eval_detector self-check ok")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        demo()
    else:
        raise SystemExit(main())
