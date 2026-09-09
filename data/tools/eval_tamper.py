"""Measure what the tampering checks actually do. Build-time only.

    python data/tools/eval_tamper.py --limit 120

Two numbers per check, and the second is the one that counts:

    false positive rate   on untouched genuine cards
    detection rate        per forgery family, at that same threshold

**The thresholds are set from the clean set alone.** Each cut is the score at
which the false-positive rate on genuine cards hits the budget below; no forgery
ever participates in choosing it. That is a stronger discipline than CLAUDE.md's
"tune on one family, report on another", and it exists for the same reason: a
threshold tuned against the forgeries it is then scored on measures the
generator rather than the forgery. Every family here is held out by construction.

What this cannot measure, stated rather than hidden:

  * Real forgeries. `data/tools/mutate.py` writes the mutations; a professional
    physical forgery is not obtainable and nothing here stands in for one.
  * `tamper.digital.double_jpeg`. It looks for a non-standard quantisation
    table, the fingerprint of an editor having written the file. OpenCV writes
    standard libjpeg tables, so the generator cannot produce the artefact the
    check looks for. It is reported as NOT EVALUATED, not as 100%.
  * `tamper.digital.exif_software`. Same reason - the generator writes no EXIF.
  * The physical checks that need `ctx.field_boxes`. No detector weights yet.

Genuine cards come from `data/processed/fields/test/images`, the held-out split
of the field-detector dataset. They are real captures of real card layouts, not
renders, which is what makes the false-positive number worth anything.
"""
import argparse
import glob
import random
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2                                                          # noqa: E402

from core.decode import downscale                                   # noqa: E402
from core.profiles import load_config                               # noqa: E402
from data.tools import mutate                                       # noqa: E402
from modules.tamper import digital, physical                        # noqa: E402

IMAGES = ROOT / "data" / "processed" / "fields" / "test" / "images"

#: The share of genuine cards we are willing to see flagged. Tamper signals are
#: weighted evidence, not hard fails, so a few percent is affordable - but it is
#: an explicit budget rather than whatever a round number produced.
FP_BUDGET = 0.05

#: Which mutation each check is even capable of seeing. Scoring a check against
#: a family it has no mechanism to detect produces a low number that means
#: nothing, and a reader would take it for a weakness rather than a category
#: error.
EXPECTED = {
    "halftone": ("splice", "photo_swap", "retype"),
    "ela": ("splice", "photo_swap"),
    "copy_move": ("copy_move",),
    "noise_residual": ("splice", "photo_swap", "retype"),
}


def score_image(image: np.ndarray, cfg: dict) -> dict:
    ela_z, _ = digital.ela(image)
    matches, region = digital.copy_move(image, cfg)
    noise, _ = digital.noise_residual(image, cfg)
    disagree, _, tiles = physical.halftone(image, cfg)
    return {
        "halftone": disagree if tiles else 0.0,
        "ela": ela_z,
        # Copy-move is a decision, not a score - the geometric guards either
        # accept the cluster or reject it - so it carries its own threshold and
        # is reported as a rate rather than swept.
        "copy_move": float(matches if region is not None else 0),
        "noise_residual": noise,
    }


def scraped_cards(limit: int, seed: int):
    """Real captures of real card layouts, from the held-out detector split."""
    files = sorted(glob.glob(str(IMAGES / "*.jpg")))
    if not files:
        return []
    random.seed(seed)
    for path in random.sample(files, min(limit, len(files))):
        raw = cv2.imread(path)
        if raw is not None:
            yield downscale(raw)


def generated_cards(limit: int, seed: int):
    """Our own documents, from `data/generator/`.

    The reason this source exists: the scraped numbers are measured on imagery
    of unrecorded provenance, which is exactly the question DEMO.md predicts a
    panel will ask. These are ours, labelled, and reproducible from a seed.

    They are also *cleaner* than any real capture - no scanner noise, no
    lighting, no print. A false-positive rate measured here is a floor, and the
    scraped number remains the one to quote.
    """
    from data.generator import DOC_TYPES, build
    for n in range(limit):
        doc_type = DOC_TYPES[n % len(DOC_TYPES)]
        yield build(doc_type, seed=seed + n).image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--source", choices=("scraped", "generated"),
                        default="scraped",
                        help="which genuine set to measure against")
    args = parser.parse_args()

    source = (scraped_cards if args.source == "scraped" else generated_cards)
    images = list(source(args.limit, args.seed))
    if not images:
        print(f"no genuine cards for source {args.source!r}.\n"
              f"  scraped:   python data/tools/build_field_dataset.py\n"
              f"  generated: pip install -r requirements-build.txt "
              f"&& python scripts/fetch_fonts.py")
        return 1

    cfg = load_config("thresholds")["tamper"]
    clean: list[dict] = []
    tampered: dict[str, list[dict]] = {f: [] for f in mutate.FAMILIES}
    halftone_resolved = 0

    print(f"scoring {len(images)} genuine {args.source} cards "
          f"x {len(mutate.FAMILIES) + 1} variants")
    for n, image in enumerate(images, 1):
        clean.append(score_image(image, cfg))
        _fraction, _region, tiles = physical.halftone(image, cfg)
        halftone_resolved += 1 if tiles else 0
        for family in mutate.FAMILIES:
            mutated, _mask = mutate.apply(family, image, seed=args.seed + n)
            tampered[family].append(score_image(mutated, cfg))
        if n % 20 == 0:
            print(f"  {n}/{len(images)}")

    cuts = {}
    print(f"\nthresholds, chosen so that {FP_BUDGET:.0%} of genuine cards are flagged")
    print("-" * 74)
    for check in ("ela", "noise_residual", "halftone"):
        values = np.array([row[check] for row in clean], dtype=float)
        cut = float(np.quantile(values, 1 - FP_BUDGET))
        cuts[check] = cut
        fp = float((values > cut).mean())
        print(f"  {check:16s} cut {cut:8.3f}   genuine flagged {fp:5.1%}   "
              f"(median {np.median(values):.3f})")

    cm_values = np.array([row["copy_move"] for row in clean], dtype=float)
    cm_fp = float((cm_values > 0).mean())
    print(f"  {'copy_move':16s} cut {cfg['copy_move_min_matches']:8d}   "
          f"genuine flagged {cm_fp:5.1%}   (geometric guards, not a swept cut)")

    print(f"\ndetection rate per family, every family held out of the tuning")
    print("-" * 74)
    header = f"  {'check':16s} " + " ".join(f"{f:>11s}" for f in mutate.FAMILIES)
    print(header)
    for check in ("ela", "noise_residual", "halftone", "copy_move"):
        cells = []
        for family in mutate.FAMILIES:
            values = np.array([row[check] for row in tampered[family]], dtype=float)
            cut = cuts.get(check, 0.0)
            rate = float((values > cut).mean())
            marker = "" if family in EXPECTED[check] else "."
            cells.append(f"{rate:10.1%}{marker or ' '}")
        print(f"  {check:16s} " + " ".join(cells))
    print("\n  a trailing '.' marks a family the check has no mechanism to see;"
          "\n  that number is a category error, not a weakness.")

    print(f"\nnot evaluated")
    print("-" * 74)
    print("  double_jpeg        the generator writes standard libjpeg tables, so it")
    print("                     cannot produce the editor-written table this looks for")
    print("  exif_software      the generator writes no EXIF")
    print("  layout_geometry    needs field boxes; no detector weights deployed")
    print("  ocrb_conformance   needs field boxes; no detector weights deployed")
    print(f"  halftone           the print screen resolved on {halftone_resolved}/"
          f"{len(clean)} genuine captures")
    print("  guilloche_break    measured three ways and disabled; see data/TAMPERING.md")
    print("  ghost_missing      a comparison, not a score - measured separately")
    if halftone_resolved == 0:
        print("                     -> reports `inconclusive` on every one of them,")
        print("                        which is the honest answer at this capture")
        print("                        resolution, not a pass")

    print(f"\nput these in config/thresholds.yaml:")
    print(f"  ela_z: {cuts['ela']:.1f}")
    print(f"  noise_outlier_frac: {cuts['noise_residual']:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
