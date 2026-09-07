"""Track A - physical artifact forensics. context/TECHNICAL-SPEC.md section 7.

The primary track, because it is the one that survives the thing digital
forensics cannot see: a professionally printed forgery, scanned fresh. The file
is genuinely a single-compression scan of a real object; what is wrong is the
object.

Three checks live here, and they are the three that need no reference template:

  halftone            does the whole page carry one print screen?
  print consistency   is every glyph on a line the same machine's output?
  layout geometry     is each field where genuine cards of this type put it?

Guilloche continuity and ghost portrait are **not** here. Guilloche needs a
vectorised template per document type (D18 buys that for passport and Aadhaar
only, and the templates do not exist yet); `ghost_photo` has zero instances in
the training set, so the detector will never emit the box the check would read.
Both are reported by `modules/tamper/__init__.py` as structural gaps that name
their own reason, rather than as a silent `inconclusive` an officer would read
as "checked, nothing found".

The layout reference is not a hand-drawn template. It is the median field
position measured over the labelled genuine cards in the training set, written
by `data/tools/build_layout.py`. That is a defensible sentence in front of a
panel and it cost no vector work.
"""
import json
import time
from pathlib import Path

import cv2
import numpy as np

from core.decode import to_gray
from core.profiles import field_label
from fusion.signal import Signal

ROOT = Path(__file__).resolve().parents[2]
LAYOUT_DIR = ROOT / "config" / "layout"

#: Mirrors data/tools/build_layout.py. A field position measured on a handful of
#: cards from one source is not a fact about the document type, and checking
#: against it would accuse genuine cards of being in the wrong place.
MIN_REFERENCE_CARDS = 50

#: Halftone analysis resolution. A 2400 px FFT does not fit the 160 ms Tier 1
#: budget and buys nothing - the print screen is a low-frequency structure.
FFT_EDGE = 1024
TILE = 128

#: A tile of blank laminate has no screen to measure and would otherwise vote.
MIN_TILE_ENERGY = 4.0


# ------------------------------------------------------------------- halftone

def _tile_frequency(tile: np.ndarray) -> float | None:
    """Radial frequency of the strongest non-DC peak, or None if the tile is flat."""
    tile = tile - tile.mean()
    if float(tile.std()) < MIN_TILE_ENERGY:
        return None

    # Hann window, or the tile edges ring and every tile reports the same
    # spurious peak at the border frequency.
    n = tile.shape[0]
    window = np.outer(np.hanning(n), np.hanning(n)).astype(np.float32)
    spectrum = np.abs(np.fft.rfft2(tile * window))
    spectrum[0, 0] = 0.0

    flat = int(np.argmax(spectrum))
    fy, fx = np.unravel_index(flat, spectrum.shape)
    # Wrap the vertical axis: rfft2 keeps rows -n/2..n/2 folded at the top.
    if fy > n // 2:
        fy = n - fy
    return float(np.hypot(fx, fy))


def halftone(image: np.ndarray, cfg: dict) -> tuple[float, tuple | None, int]:
    """Print screen consistency. Returns (disagreeing fraction, region, tiles).

    Genuine printing lays one screen across the whole page. A region that was
    printed separately and pasted, or inserted digitally and reprinted, carries
    a different screen frequency or none at all - and it is the *disagreement*
    that is the signal, not any absolute frequency, because we hold no reference
    for what each document's press used.
    """
    gray = to_gray(image).astype(np.float32)
    h, w = gray.shape[:2]
    scale = FFT_EDGE / max(h, w)
    if scale < 1.0:
        gray = cv2.resize(gray, (round(w * scale), round(h * scale)),
                          interpolation=cv2.INTER_AREA)
    gh, gw = gray.shape[:2]
    rows, cols = gh // TILE, gw // TILE
    if rows < 2 or cols < 2:
        return 0.0, None, 0

    grid = np.full((rows, cols), np.nan, dtype=np.float32)
    for r in range(rows):
        for c in range(cols):
            value = _tile_frequency(gray[r * TILE:(r + 1) * TILE,
                                         c * TILE:(c + 1) * TILE])
            if value is not None:
                grid[r, c] = value

    measured = grid[~np.isnan(grid)]
    if measured.size < 4:
        return 0.0, None, int(measured.size)

    # Is a screen actually resolved? A capture that does not resolve the print
    # screen gives every tile a different, essentially arbitrary peak, so the
    # measured frequencies have no mode. Reporting "one consistent screen"
    # from that would be a pass invented out of noise. The caller turns a
    # `tiles` count of zero into `inconclusive`, which is the truth: a phone
    # photo of a card at 2400 px does not resolve a 150 lpi offset screen.
    modal = float(np.median(measured))
    spread = float(np.median(np.abs(measured - modal)))
    if modal <= 0 or spread > 0.5 * modal:
        return 0.0, None, 0
    tolerance = max(2.0, 0.25 * modal)
    disagree = ~np.isnan(grid) & (np.abs(grid - modal) > tolerance)
    fraction = float(disagree.sum()) / float(measured.size)
    if not disagree.any():
        return 0.0, None, int(measured.size)

    ys, xs = np.nonzero(disagree)
    sy, sx = h / rows, w / cols
    region = (float(xs.min() * sx), float(ys.min() * sy),
              float(min(w, (xs.max() + 1) * sx)), float(min(h, (ys.max() + 1) * sy)))
    return fraction, region, int(measured.size)


# ----------------------------------------------------------- print consistency

def glyph_height_cv(patch: np.ndarray) -> tuple[float, int]:
    """Coefficient of variation of glyph height in one crop, and the glyph count.

    Machine printing of a single line is uniform to a fraction of a percent. A
    line that has been retyped, spliced from another document, or overprinted
    carries a second set of metrics, and the mixture shows up as spread. Uses
    height rather than stroke width because height survives a 300 dpi scan and
    stroke width mostly does not.
    """
    if patch is None or patch.size == 0:
        return 0.0, 0
    gray = to_gray(patch)
    if min(gray.shape[:2]) < 8:
        return 0.0, 0

    _thresh, binary = cv2.threshold(gray, 0, 255,
                                    cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, 8)
    if count < 2:
        return 0.0, 0

    heights = stats[1:, cv2.CC_STAT_HEIGHT].astype(np.float32)
    areas = stats[1:, cv2.CC_STAT_AREA].astype(np.float32)
    line = float(gray.shape[0])
    # Drop speckle and drop anything as tall as the crop itself - a border or a
    # scan artefact is not a glyph and would dominate the spread.
    keep = (areas >= 6) & (heights >= 0.15 * line) & (heights <= 0.95 * line)
    heights = heights[keep]
    if heights.size < 4:
        return 0.0, int(heights.size)

    mean = float(heights.mean())
    if mean <= 0:
        return 0.0, int(heights.size)
    return float(heights.std() / mean), int(heights.size)


# --------------------------------------------------------------- ghost portrait

def ghost_agreement(image: np.ndarray, photo_box, ghost_box) -> float:
    """How alike the printed portrait and the ghost portrait are, 0 to 1.

    The ghost is a faded greyscale reprint of the same photograph, so on a
    genuine document the two carry the same face. A forger who replaces the
    portrait and leaves the ghost alone leaves two different people on one page
    - and unlike most of this module, that is a *comparison* rather than a
    texture statistic, so it does not care how the document was printed.

    Correlated on a small greyscale thumbnail with its own mean and contrast
    removed. The ghost is printed lighter and softer than the portrait by
    design, so comparing raw intensities would report every genuine document as
    a mismatch; what has to match is the structure, not the exposure.
    """
    def thumb(box):
        x1, y1, x2, y2 = (int(v) for v in box)
        patch = image[max(0, y1):y2, max(0, x1):x2]
        if patch.size == 0 or min(patch.shape[:2]) < 8:
            return None
        small = cv2.resize(to_gray(patch), (48, 64), interpolation=cv2.INTER_AREA)
        small = small.astype(np.float32)
        # Equalising first is what makes a faded reprint comparable with the
        # portrait it was made from.
        small = cv2.equalizeHist(small.astype(np.uint8)).astype(np.float32)
        return small - small.mean()

    a, b = thumb(photo_box), thumb(ghost_box)
    if a is None or b is None or a.std() < 1e-3 or b.std() < 1e-3:
        return -1.0
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0])


def run_ghost(ctx, cfg: dict) -> Signal:
    """Is the ghost portrait present, and is it the same face as the portrait?

    Two failure modes, one signal, because they are the same forgery seen from
    two sides: the ghost is gone, or the ghost no longer matches.
    """
    started = time.perf_counter()
    sid = "tamper.physical.ghost_missing"

    if not ctx.field_boxes:
        return _signal(sid, "inconclusive",
                       "The ghost portrait could not be checked - the field "
                       "detector is not yet deployed, so neither portrait was "
                       "located", confidence=0.0, started=started)

    photo_box = ctx.field_boxes.get("person_photo")
    ghost_box = ctx.field_boxes.get("ghost_photo")

    if photo_box is None:
        return _signal(sid, "inconclusive",
                       "The main portrait was not located, so the ghost portrait "
                       "has nothing to be compared against", confidence=0.0,
                       started=started)

    if ghost_box is None:
        # The profile declares this document carries one and the detector,
        # which found the main portrait on the same page, did not find it.
        return _signal(sid, "fail",
                       "This document type carries a second, faded portrait and "
                       "none was found on it. Check the area beside the printed "
                       "photograph", confidence=0.6, anchor="field:ghost_photo",
                       region=tuple(photo_box), started=started)

    agreement = ghost_agreement(ctx.image, photo_box, ghost_box)
    if agreement < 0:
        return _signal(sid, "inconclusive",
                       "The ghost portrait was located but is too small or too "
                       "faint at this capture resolution to compare against the "
                       "printed photograph", confidence=0.0,
                       anchor="field:ghost_photo", region=tuple(ghost_box),
                       started=started)

    if agreement < cfg["ghost_agreement_min"]:
        return _signal(sid, "fail",
                       f"The faded portrait and the printed photograph are not "
                       f"the same face. Compare them side by side - one of the "
                       f"two has been replaced",
                       confidence=min(0.9, 0.4 + (cfg["ghost_agreement_min"]
                                                  - agreement)),
                       anchor="field:ghost_photo", region=tuple(ghost_box),
                       started=started)
    return _signal(sid, "pass",
                   "The faded portrait matches the printed photograph",
                   confidence=0.7, anchor="field:ghost_photo",
                   region=tuple(ghost_box), started=started)


# ------------------------------------------------------------- layout geometry

def layout_reference(doc_type: str) -> dict | None:
    """Median field positions for this document type, or None if not built."""
    path = LAYOUT_DIR / f"{doc_type}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def layout_outliers(field_boxes: dict, image_shape, reference: dict,
                    limit: float) -> list[tuple[str, float, tuple]]:
    """Fields sitting further from their reference position than `limit` MADs."""
    h, w = image_shape[:2]
    if h <= 0 or w <= 0:
        return []

    out = []
    for name, box in field_boxes.items():
        stats = reference.get("fields", {}).get(name)
        if not stats or stats.get("n", 0) < MIN_REFERENCE_CARDS:
            # Too few genuine examples to say where this field belongs.
            continue
        x1, y1, x2, y2 = box
        cx, cy = ((x1 + x2) / 2) / w, ((y1 + y2) / 2) / h
        zx = abs(cx - stats["cx"]) / max(stats["mad_x"], 0.01)
        zy = abs(cy - stats["cy"]) / max(stats["mad_y"], 0.01)
        z = float(max(zx, zy))
        if z > limit:
            out.append((name, z, tuple(box)))
    return sorted(out, key=lambda item: -item[1])


# ------------------------------------------------------------------ the signals

def _signal(sid: str, verdict: str, evidence: str, *, confidence: float,
            anchor: str = "document", region=None, started=None) -> Signal:
    return Signal(
        id=sid, module="tamper", tier=1, verdict=verdict, confidence=confidence,
        trust_class="probabilistic", hard_fail=False, anchor=anchor,
        evidence=evidence, region=region,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0,
    )


def run_halftone(image: np.ndarray, cfg: dict) -> Signal:
    started = time.perf_counter()
    sid = "tamper.physical.halftone"
    fraction, region, tiles = halftone(image, cfg)
    if tiles < 4:
        return _signal(sid, "inconclusive",
                       "The capture carries too little printed detail to measure "
                       "the print screen - a higher-resolution capture of the "
                       "document would resolve it", confidence=0.0, started=started)

    if fraction >= cfg["halftone_disagree_frac"] and region is not None:
        return _signal(sid, "fail",
                       f"{fraction * 100:.0f}% of the page is printed with a "
                       f"different screen pattern from the rest, which is what a "
                       f"separately printed or reprinted area looks like",
                       confidence=min(0.9, 0.4 + fraction), region=region,
                       started=started)
    return _signal(sid, "pass",
                   f"One consistent print screen across the page, measured over "
                   f"{tiles} areas", confidence=0.6, started=started)


def run_print_consistency(ctx, cfg: dict, *, mrz: bool) -> Signal:
    """Glyph uniformity. On a passport this is the MRZ; elsewhere the text fields.

    ponytail: both report under `tamper.physical.ocrb_conformance` because that
    is the registered id and the measurement is the same one - glyph metrics
    within a printed line. The evidence string says which fields were actually
    measured, so the officer is never told "OCR-B" about a PAN card.
    """
    from modules.extraction.ocr import crop

    started = time.perf_counter()
    sid = "tamper.physical.ocrb_conformance"
    what = "machine-readable zone" if mrz else "printed text fields"

    if not ctx.field_boxes:
        return _signal(sid, "inconclusive",
                       f"The {what} could not be located - the field detector is "
                       f"not yet deployed, so print consistency was not measured",
                       confidence=0.0, started=started)

    wanted = ["mrz"] if mrz else [
        n for n in ("name", "father_name", "dob", "id_number", "address")
        if n in ctx.field_boxes
    ]
    measured: list[tuple[str, float, int, tuple]] = []
    for name in wanted:
        box = ctx.field_boxes.get(name)
        if box is None:
            continue
        patch = crop(ctx.image, box)
        cv_value, glyphs = glyph_height_cv(patch)
        if glyphs >= 4:
            measured.append((name, cv_value, glyphs, tuple(box)))

    if not measured:
        return _signal(sid, "inconclusive",
                       f"No {what} carried enough resolved characters to measure "
                       f"print consistency", confidence=0.0, started=started)

    worst = max(measured, key=lambda item: item[1])
    name, value, glyphs, box = worst
    if value >= cfg["glyph_height_cv"]:
        return _signal(sid, "fail",
                       f"Character heights in the {field_label(name)} vary by "
                       f"{value * 100:.0f}%, well beyond one machine's printing. "
                       f"That line has more than one origin",
                       confidence=min(0.9, 0.4 + value), anchor=f"field:{name}",
                       region=box, started=started)
    return _signal(sid, "pass",
                   f"Character heights are uniform across the {what} "
                   f"(worst line varies by {value * 100:.0f}%)",
                   confidence=0.65, started=started)


def run_layout(ctx, cfg: dict) -> Signal:
    started = time.perf_counter()
    sid = "tamper.physical.layout_geometry"

    if not ctx.field_boxes:
        return _signal(sid, "inconclusive",
                       "Field positions could not be measured - the field "
                       "detector is not yet deployed", confidence=0.0,
                       started=started)

    reference = layout_reference(ctx.doc_type)
    if reference is None:
        return _signal(sid, "inconclusive",
                       f"No layout reference has been built for this document "
                       f"type - run data/tools/build_layout.py", confidence=0.0,
                       started=started)

    outliers = layout_outliers(ctx.field_boxes, ctx.image.shape, reference,
                               cfg["layout_mad"])
    if outliers:
        name, z, box = outliers[0]
        return _signal(sid, "fail",
                       f"The {field_label(name)} sits well away from where it "
                       f"appears on genuine documents of this type "
                       f"({z:.0f} times the normal spread)",
                       confidence=min(0.9, 0.3 + z / 20.0),
                       anchor=f"field:{name}", region=box, started=started)

    checked = sum(1 for n in ctx.field_boxes
                  if reference.get("fields", {}).get(n, {}).get("n", 0)
                  >= MIN_REFERENCE_CARDS)
    if checked == 0:
        return _signal(sid, "inconclusive",
                       "No located field had enough genuine examples in the "
                       "reference set to check its position", confidence=0.0,
                       started=started)
    return _signal(sid, "pass",
                   f"All {checked} located fields sit where genuine documents of "
                   f"this type put them", confidence=0.6, started=started)
