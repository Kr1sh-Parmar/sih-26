"""Demographic disparity in face matching. BUILD TIME ONLY.

    python scripts/eval_bias.py --set data/raw/face/fairface

**Currently unrunnable, because the data is not here.** That is recorded in
`data/FACE.md` as *unmeasured*, which is a very different claim from *small*.
MODULES.md calls this "a compliance item, not a nice-to-have", and NIST FRVT
found demographic false-match differentials of more than an order of magnitude
across algorithms - so an unmeasured system is not a system with no disparity.

## What each dataset can and cannot tell you

**FairFace** labels age, gender and race but has **one image per person**. With
no identity labels there are no genuine pairs, so it can measure a **false match
rate** - how often two *different* people from the same group are confused - and
it cannot measure false rejection at all. FMR is still the half that matters
most here: a false match is an impostor admitted.

**RFW** (Racial Faces in the Wild) carries identities and gives both halves.
It requires signing a licence, so it cannot be fetched unattended.

This script does whichever the data supports and says which it did. It will not
print a disparity ratio from a group with too few faces to mean anything.

## Expected layout

    data/raw/face/fairface/
      labels.csv          columns: file,age,gender,race[,identity]
      images/...          paths in `file` are relative to the set directory
"""
import argparse
import csv
import itertools
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import cv2                                                          # noqa: E402

from core.decode import downscale                                   # noqa: E402
from modules.face import detect as detector                         # noqa: E402
from modules.face import embed as embedder                          # noqa: E402
from modules.face import threshold                                  # noqa: E402

#: Below this a group's rate is an anecdote. NIST reports by group precisely
#: because pooling hides the disparity; reporting a group of nine does the same
#: thing in the other direction.
MIN_PER_GROUP = 60


def load(directory: Path, limit: int) -> dict:
    """{group: [(identity, embedding)]} for whatever the labels file carries."""
    labels = directory / "labels.csv"
    if not labels.exists():
        sys.exit(f"no {labels}.\n{__doc__.split('## Expected layout')[1]}")

    groups: dict = defaultdict(list)
    with labels.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))[:limit]

    for n, row in enumerate(rows, 1):
        path = directory / row["file"]
        image = cv2.imread(str(path))
        if image is None:
            continue
        image = downscale(image)
        face = detector.largest(detector.detect(image))
        if face is None:
            continue
        # Group on the axis NIST reports on. Gender is carried alongside so a
        # follow-up can slice both ways without re-embedding.
        group = row.get("race") or row.get("gender") or "all"
        groups[group].append((row.get("identity") or f"row{n}",
                              embedder.of(image, face["landmarks"])))
        if n % 200 == 0:
            print(f"  {n}/{len(rows)}")
    return groups


def false_match_rate(entries: list, cut: float, cap: int = 20000) -> tuple:
    """Share of *different-person* pairs inside one group that match anyway."""
    pairs = [(a, b) for a, b in itertools.combinations(entries, 2)
             if a[0] != b[0]]
    if len(pairs) > cap:
        step = len(pairs) // cap
        pairs = pairs[::step][:cap]
    scores = np.array([float(np.dot(a[1], b[1])) for a, b in pairs])
    return float((scores >= cut).mean()), len(pairs), scores


def false_non_match_rate(entries: list, cut: float) -> tuple:
    """Share of same-person pairs that fail to match. Needs identity labels."""
    by_identity: dict = defaultdict(list)
    for identity, vector in entries:
        by_identity[identity].append(vector)
    pairs = [(a, b) for vectors in by_identity.values() if len(vectors) > 1
             for a, b in itertools.combinations(vectors, 2)]
    if not pairs:
        return None, 0, np.array([])
    scores = np.array([float(np.dot(a, b)) for a, b in pairs])
    return float((scores < cut).mean()), len(pairs), scores


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="data/raw/face/fairface")
    parser.add_argument("--limit", type=int, default=4000)
    args = parser.parse_args()

    directory = ROOT / args.set
    if not directory.exists():
        print(f"no dataset at {directory}.\n\n"
              "FairFace: github.com/joojs/fairface (images via Google Drive; "
              "the padding=0.25 set is enough).\n"
              "RFW: whdeng.cn/RFW - requires signing a licence, so it cannot be "
              "fetched unattended.\n\n"
              "Until one of them is on disk the demographic disparity of this "
              "system is UNMEASURED. data/FACE.md says so.")
        return 1

    cut, calibrated = threshold()
    print(f"threshold {cut}"
          f"{'' if calibrated else '  (NOT calibrated - D11)'}")

    groups = load(directory, args.limit)
    usable = {name: rows for name, rows in groups.items()
              if len(rows) >= MIN_PER_GROUP}
    if len(usable) < 2:
        print(f"only {len(usable)} group(s) reached {MIN_PER_GROUP} faces; "
              f"a disparity needs at least two")
        return 1

    print(f"\n{'group':22s} {'faces':>6s} {'pairs':>8s} {'FMR':>8s} {'FNMR':>8s}")
    print("-" * 58)
    fmrs = {}
    for name, rows in sorted(usable.items()):
        fmr, pairs, _ = false_match_rate(rows, cut)
        fnmr, genuine, _ = false_non_match_rate(rows, cut)
        fmrs[name] = fmr
        shown = f"{fnmr:8.2%}" if fnmr is not None else "       -"
        print(f"{name:22s} {len(rows):6d} {pairs:8d} {fmr:8.3%} {shown}")

    worst, best = max(fmrs.values()), min(fmrs.values())
    print(f"\nfalse match rate: worst group {worst:.3%}, best {best:.3%}")
    if best > 0:
        print(f"disparity ratio:  {worst / best:.1f}x")
    else:
        print("disparity ratio:  undefined - the best group had no false match "
              "at this threshold, which usually means the sample is too small")

    if all(false_non_match_rate(r, cut)[0] is None for r in usable.values()):
        print("\nFNMR is blank because this set has one image per person. False "
              "rejection needs identity labels - RFW has them, FairFace does not.")
    print("\nThis measures the embedding on web photographs. The system screens "
          "document-to-live pairs, which is a different domain (D11), so treat "
          "this as the disparity of the model rather than of the deployment.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
