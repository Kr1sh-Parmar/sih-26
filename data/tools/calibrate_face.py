"""Calibrate the document-to-live threshold. Build time only.

    python data/tools/calibrate_face.py --pairs var/calibration --apply

Ships unused. There are no calibration pairs yet, and until there are, the
threshold in `config/thresholds.yaml` carries `calibrated: false` and every face
signal says so in the sentence the officer reads.

**Why not an LFW threshold.** Published buffalo operating points are live-to-
live. A document photo is printed, halftone screened, overprinted with a
security pattern, sub-300 dpi once scanned, and up to ten years old. The genuine
distribution is shifted down against LFW and the impostor distribution is not,
so an LFW threshold rejects real travellers - wrong in the direction that causes
queues and, worse, teaches an officer to override the machine (D11).

Expected layout, one directory per person:

    var/calibration/
      person_01/
        doc.jpg          the photo page or card, as the scanner sees it
        live_01.jpg      camera frames of the same person
        live_02.jpg
      person_02/
        ...

Genuine pairs are every (doc, live) within a person; impostor pairs are every
(doc, live) across different people. Target is >=500 genuine pairs from >=30
people (MODULES.md) - fewer and the operating point is an anecdote.

The chosen threshold is the one meeting the false-accept target, because at a
border the asymmetry is real: a false reject costs a traveller a secondary
inspection, a false accept lets the wrong person through. `--far` moves it, and
the whole curve is printed so a checkpoint commander can choose differently.
"""
import argparse
import itertools
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2                                                          # noqa: E402

from core.decode import decode, downscale                           # noqa: E402
from modules.face import detect as detector                         # noqa: E402
from modules.face import embed as embedder                          # noqa: E402

THRESHOLDS = ROOT / "config" / "thresholds.yaml"


def embed_file(path: Path) -> np.ndarray | None:
    image = cv2.imread(str(path))
    if image is None:
        return None
    image = downscale(image)
    face = detector.largest(detector.detect(image))
    if face is None:
        print(f"  no face found in {path.name}")
        return None
    return embedder.of(image, face["landmarks"])


def load(pairs_dir: Path) -> dict:
    """{person: {'doc': vec, 'live': [vec, ...]}}"""
    people = {}
    for person in sorted(p for p in pairs_dir.iterdir() if p.is_dir()):
        doc = next((f for f in sorted(person.glob("doc*")) if f.is_file()), None)
        if doc is None:
            print(f"{person.name}: no doc* image, skipped")
            continue
        doc_vec = embed_file(doc)
        if doc_vec is None:
            continue
        live = [v for v in (embed_file(f) for f in sorted(person.glob("live*")))
                if v is not None]
        if not live:
            print(f"{person.name}: no usable live frame, skipped")
            continue
        people[person.name] = {"doc": doc_vec, "live": live}
        print(f"{person.name}: 1 document photo, {len(live)} live frames")
    return people


def score_pairs(people: dict) -> tuple[np.ndarray, np.ndarray]:
    genuine, impostor = [], []
    for name, data in people.items():
        genuine += [embedder.cosine(data["doc"], v) for v in data["live"]]
    for a, b in itertools.permutations(people, 2):
        impostor += [embedder.cosine(people[a]["doc"], v)
                     for v in people[b]["live"]]
    return np.array(genuine), np.array(impostor)


def curve(genuine: np.ndarray, impostor: np.ndarray) -> list[dict]:
    points = []
    for cut in np.arange(0.10, 0.75, 0.01):
        points.append({
            "threshold": round(float(cut), 2),
            # FAR: impostors accepted. FRR: genuine travellers turned away.
            "far": float((impostor >= cut).mean()),
            "frr": float((genuine < cut).mean()),
        })
    return points


def apply_to(text: str, cut: float, people: int, pairs: int) -> str:
    """Rewrite the `face.doc_live` block of config/thresholds.yaml.

    The TODO comment is replaced along with the value it marks. A plain value
    substitution left the file reading `threshold: 0.41  # TODO calibrate` next
    to `calibrated: true` - the one place a reader looks to find out whether
    this number was measured, saying both.
    """
    text, hits = re.subn(
        r"(?m)^(  doc_live:\n)    threshold: [\d.]+.*$",
        lambda m: f"{m.group(1)}    threshold: {cut:.2f}"
                  f"            # calibrated on {pairs} doc-vs-live pairs "
                  f"from {people} people",
        text, count=1)
    if not hits:
        raise ValueError("no face.doc_live threshold line in thresholds.yaml")
    text, hits = re.subn(r"(?m)^    calibrated: false", "    calibrated: true",
                         text, count=1)
    if not hits:
        raise ValueError("no `calibrated: false` under face.doc_live")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="var/calibration")
    parser.add_argument("--far", type=float, default=0.001,
                        help="target false accept rate; the threshold is the "
                             "lowest cut that meets it")
    parser.add_argument("--apply", action="store_true",
                        help="write the threshold into config/thresholds.yaml "
                             "and set calibrated: true")
    args = parser.parse_args()

    pairs_dir = ROOT / args.pairs
    if not pairs_dir.exists():
        print(f"no calibration set at {pairs_dir}.\n\n{__doc__.split('Expected layout')[1]}")
        return 1

    people = load(pairs_dir)
    if len(people) < 2:
        print("at least two people are needed to produce an impostor distribution")
        return 1

    genuine, impostor = score_pairs(people)
    print(f"\n{len(people)} people, {len(genuine)} genuine pairs, "
          f"{len(impostor)} impostor pairs")
    if len(genuine) < 500 or len(people) < 30:
        print("  NOT ENOUGH. MODULES.md asks for >=500 genuine pairs from >=30")
        print("  people. Anything below that is an anecdote, and a threshold")
        print("  from it should not be marked calibrated.")

    print(f"\n  genuine  median {np.median(genuine):.3f}  "
          f"5th percentile {np.quantile(genuine, 0.05):.3f}")
    print(f"  impostor median {np.median(impostor):.3f}  "
          f"95th percentile {np.quantile(impostor, 0.95):.3f}")

    points = curve(genuine, impostor)
    print(f"\n  {'threshold':>10s} {'FAR':>8s} {'FRR':>8s}")
    for point in points:
        # round() before the modulo: 0.55 * 100 is 55.00000000000001 in binary
        # floating point, which silently dropped that row from the curve.
        if round(point["threshold"] * 100) % 5 == 0:
            print(f"  {point['threshold']:10.2f} {point['far']:8.2%} "
                  f"{point['frr']:8.2%}")

    meeting = [p for p in points if p["far"] <= args.far]
    if not meeting:
        print(f"\nno threshold reaches FAR <= {args.far:.1%} on this set")
        return 1
    chosen = meeting[0]
    print(f"\nthreshold {chosen['threshold']:.2f} -> FAR {chosen['far']:.2%}, "
          f"FRR {chosen['frr']:.2%}")

    out = ROOT / "var" / "face_calibration.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "people": len(people), "genuine_pairs": len(genuine),
        "impostor_pairs": len(impostor), "target_far": args.far,
        "chosen": chosen, "curve": points,
    }, indent=2), encoding="utf-8")
    print(f"curve written to {out.relative_to(ROOT)}")

    if args.apply:
        if len(genuine) < 500 or len(people) < 30:
            print("\nrefusing --apply: the set is below the size that makes "
                  "`calibrated: true` an honest claim.")
            return 1
        THRESHOLDS.write_text(
            apply_to(THRESHOLDS.read_text(encoding="utf-8"),
                     chosen["threshold"], len(people), len(genuine)),
            encoding="utf-8")
        print("config/thresholds.yaml updated; face.doc_live is now calibrated")
    else:
        print("\nrerun with --apply to write it into config/thresholds.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
