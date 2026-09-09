"""Render one printable card per calibration volunteer. BUILD TIME ONLY.

    python data/tools/build_calibration_cards.py
    python data/tools/build_calibration_cards.py --doc-type pan --sheet

Reads the layout `scripts/capture_pairs.py` writes and closes the gap between it
and `data/tools/calibrate_face.py`:

    var/calibration/
      person_01/
        portrait.jpg   <- capture_pairs.py wrote this
        card.png       <- this script writes this      PRINT IT
        doc.jpg        <- YOU put the SCAN of the print here
        live_00.jpg    <- capture_pairs.py wrote these

**The print-and-scan round trip is the point, and it is not skippable.** A
document photo is printed, halftone screened, overprinted and scanned at sub-300
dpi, and that degradation is the entire reason this threshold cannot be taken
from a published live-to-live benchmark (D11). Rendering `card.png` and feeding
it straight to the calibrator as `doc.jpg` would measure a screen, not a card,
and would set the threshold too high - which rejects real travellers.

A volunteer's own Aadhaar is never used. The card is a generated one carrying
their portrait, which is what `Identity.extras["portrait_path"]` exists for.

`--sheet` also writes `sheet_NN.png` - the cards tiled onto A4 at 300 dpi, so a
session prints a couple of pages instead of one page per person. At six people
it saves little; at fifty it is the difference between an afternoon and a day.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import cv2                                                          # noqa: E402
import numpy as np                                                  # noqa: E402

#: A4 at 300 dpi, portrait. The margin keeps cards off the unprintable edge
#: that most consumer printers have.
A4 = (2480, 3508)
MARGIN = 90
GAP = 60


def _scaled(spec: dict, k: int) -> dict:
    """The template at k times the size - canvas, boxes and fonts together.

    Field boxes are fractions of the canvas so they scale for free, but font
    sizes are absolute points. Scaling the canvas alone would render a big card
    covered in tiny text, so every `size:` integer is scaled with it.
    """
    import copy
    out = copy.deepcopy(spec)
    out["size"] = [v * k for v in out["size"]]

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "size" and isinstance(value, int):
                    node[key] = value * k
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for section in ("fields", "static", "marks"):
        walk(out.get(section))
    return out


def render_card(doc_type: str, portrait: Path, seed: int, scale: int = 1):
    """One generated document carrying this volunteer's face.

    `scale` exists because of a measurement, not a preference. At the template's
    native 1000 px the portrait lands about 45-55 px wide on the card, and
    `config/thresholds.yaml` sets `face.quality.doc_min_px: 48` - so a genuine
    volunteer's own card sits on the floor, and one of the first six rendered
    could not be found by the detector at all. Calibrating on that would compare
    embeddings of upscaled guesswork and produce a threshold about nothing.

    Scaling the template renders the *portrait* at more pixels too, because
    `_portrait()` resizes the source into the box rather than the other way
    round. The source frames are 1280x720 with faces around 200 px, so there is
    real detail to keep.
    """
    from data.generator import build
    from data.generator import render as _render
    from data.generator.identity import build as build_identity

    who = build_identity(seed)
    # `portrait_path` overrides the SFHQ pool pick. Absent this the generator
    # would paste a stranger's face onto the card and every genuine pair would
    # silently become an impostor pair - which drags the impostor distribution
    # up and moves the chosen threshold *down*, toward accepting strangers.
    who.extras["portrait_path"] = str(portrait)

    if scale == 1:
        return build(doc_type, seed=seed, who=who)

    # `render()` loads the template itself, so this is the seam. Build-time
    # tool, never imported by the screening path.
    original = _render.load_template
    _render.load_template = lambda dt: _scaled(original(dt), scale)
    try:
        return build(doc_type, seed=seed, who=who)
    finally:
        _render.load_template = original


def tile(cards: list[np.ndarray]) -> list[np.ndarray]:
    """Lay the cards onto A4 sheets, in rows, top-left first.

    The sheet resolution follows the cards rather than the other way round. At
    `--scale 3` a card is 3000 px wide and simply does not fit on a 300 dpi A4
    (2480 px), which pasted out of bounds; the sheet steps up to 600 dpi so the
    same physical page holds it. Printing is physical - what matters is the
    card's size in millimetres on paper, not the sheet's pixel count.
    """
    if not cards:
        return []
    width = max(c.shape[1] for c in cards)
    height = max(c.shape[0] for c in cards)

    sheet_w, sheet_h = A4
    while width + 2 * MARGIN > sheet_w or height + 2 * MARGIN > sheet_h:
        sheet_w, sheet_h = sheet_w * 2, sheet_h * 2
        if sheet_w > 20000:      # a card this big is a one-per-page job
            return [c.copy() for c in cards]
    per_row = max(1, (sheet_w - 2 * MARGIN + GAP) // (width + GAP))
    per_col = max(1, (sheet_h - 2 * MARGIN + GAP) // (height + GAP))
    per_sheet = per_row * per_col

    sheets = []
    for start in range(0, len(cards), per_sheet):
        sheet = np.full((sheet_h, sheet_w, 3), 255, np.uint8)
        for i, card in enumerate(cards[start:start + per_sheet]):
            r, c = divmod(i, per_row)
            x = MARGIN + c * (width + GAP)
            y = MARGIN + r * (height + GAP)
            sheet[y:y + card.shape[0], x:x + card.shape[1]] = card
        sheets.append(sheet)
    return sheets


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", default="var/calibration")
    parser.add_argument("--doc-type", default="pan",
                        help="PAN is the smallest card and the cheapest to "
                             "print; any of the six works")
    parser.add_argument("--scale", type=int, default=3,
                        help="render the card at this multiple of the "
                             "template size, so the portrait carries enough "
                             "pixels to survive print and scan (measured: 1x "
                             "puts the face on the doc_min_px floor)")
    parser.add_argument("--sheet", action="store_true",
                        help="also tile the cards onto A4 sheets for printing")
    args = parser.parse_args()

    root = ROOT / args.pairs
    people = sorted(p for p in root.glob("person_*") if p.is_dir())
    if not people:
        print(f"no person_* directories under {root}\n"
              f"  run: python scripts/capture_pairs.py 01 --consent")
        return 1

    cards, made = [], 0
    for seed, person in enumerate(people, start=1):
        portrait = person / "portrait.jpg"
        if not portrait.exists():
            print(f"  {person.name}: no portrait.jpg, skipped")
            continue
        doc = render_card(args.doc_type, portrait, seed, scale=args.scale)
        out = person / "card.png"
        cv2.imwrite(str(out), doc.image)
        cards.append(doc.image)
        made += 1
        print(f"  {person.name}: {out.relative_to(ROOT)}  "
              f"{doc.image.shape[1]}x{doc.image.shape[0]}")

    if args.sheet and cards:
        for i, sheet in enumerate(tile(cards)):
            out = root / f"sheet_{i:02d}.png"
            cv2.imwrite(str(out), sheet)
            print(f"  sheet: {out.relative_to(ROOT)}")

    print(f"\n{made} card(s) rendered.\n"
          f"Next: print them, scan each at 300 dpi or better, and save the scan\n"
          f"as var/calibration/person_NN/doc.jpg - the *scan*, not card.png.\n"
          f"Then: python data/tools/calibrate_face.py --pairs {args.pairs}")
    return 0


def demo() -> None:
    """Self-check on the tiling arithmetic - no generator needed."""
    cards = [np.full((300, 500, 3), 200, np.uint8) for _ in range(7)]
    sheets = tile(cards)
    assert sheets, "no sheet produced"
    assert all(s.shape == (A4[1], A4[0], 3) for s in sheets), \
        [s.shape for s in sheets]
    per_row = (A4[0] - 2 * MARGIN + GAP) // (500 + GAP)
    per_col = (A4[1] - 2 * MARGIN + GAP) // (300 + GAP)
    assert len(sheets) == -(-7 // (per_row * per_col)), len(sheets)
    assert tile([]) == []
    # A card must not be written outside the margin.
    assert MARGIN + per_row * 500 + (per_row - 1) * GAP <= A4[0]
    print(f"tiling ok - {per_row}x{per_col} cards per A4 sheet")


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        demo()
    else:
        raise SystemExit(main())
