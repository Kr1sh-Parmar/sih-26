"""Field OCR. RapidOCR - PP-OCRv4 detection, classification and recognition,
running on ONNX Runtime CPU.

**Crops only. Never the whole page.** This is the single biggest latency win in
the system, 5-10x, and it is why the field detector matters more than the OCR
engine choice (TECHNICAL-SPEC.md section 10). Whole-page OCR also produces text
with no field identity, which is worse than useless downstream.

Why RapidOCR and not PaddleOCR: identical PP-OCRv4 models, but exported to ONNX
and run on onnxruntime, which is what CLAUDE.md rule 2 requires. The models ship
inside the wheel, so nothing is fetched at runtime.

The MRZ has its own path, because it is the only field on any of these six
documents whose correctness is verifiable arithmetically. That makes a misread
there uniquely dangerous: a single wrong character fails a check digit, and a
failed composite check digit is a hard fail. So the MRZ read is gated on line
geometry before it is allowed anywhere near Layer A.
"""
import re
import time

import cv2
import numpy as np

from core.profiles import field_label
from core import registry
from fusion.context import NormalizedField, ScreeningContext
from fusion.signal import Signal
from modules.extraction.mrz import CHARSET

#: Below this the read is a guess. It becomes `inconclusive` and costs
#: coverage, which is the honest outcome - not a plausible string nobody can
#: check (D9).
MIN_CONFIDENCE = 0.55

#: A tight detector box clips ascenders and the first glyph. Cheap insurance.
PAD_RATIO = 0.06

#: Width-to-height above which a crop is treated as a single line of text.
#: Three stacked address lines come in well under this; a name or a date is
#: well over it.
SINGLE_LINE_ASPECT = 3.0

#: Line geometries the parser supports. A read whose lengths match none of
#: these has dropped or gained a character, which the check digits would report
#: as tampering rather than as a bad scan.
#: ponytail: TD1 (3x30) is absent because mrz.parse() only handles two-line
#: formats. Accepting a geometry we cannot parse just moves the failure one
#: layer later with a worse message.
MRZ_GEOMETRY = ((2, 44), (2, 36))

#: OCR-B glyph pairs that are genuinely ambiguous at scan resolution.
_TO_DIGIT = str.maketrans("OQDILZSBGT", "0001125867")
_TO_ALPHA = str.maketrans("012568", "OIZSGB")

#: Which positions ICAO constrains to letters and which to digits. Line 1 is
#: entirely alphabetic. On line 2, positions 0-27 are laid out identically in
#: TD3, MRV-A and MRV-B, so this holds for every format the parser accepts.
#: Beyond 27 the formats diverge and nothing is coerced.
_L2_DIGITS = set(range(13, 20)) | set(range(21, 28)) | {9}
_L2_ALPHA = set(range(10, 13)) | {20}

#: Characters outside the OCR-B charset with one unambiguous counterpart.
#: Nothing speculative here: a wrong guess manufactures a check-digit failure,
#: and a check-digit failure detains someone.
_MRZ_SUBSTITUTIONS = {
    "«": "<<", "»": ">>", "‹": "<", "›": ">", "〈": "<", "《": "<<",
    "—": "<", "–": "<", "—": "<", "–": "<", "_": "<", "-": "<",
}


def crop(image: np.ndarray, box, pad: float = PAD_RATIO) -> np.ndarray | None:
    x1, y1, x2, y2 = box
    h, w = image.shape[:2]
    px, py = (x2 - x1) * pad, (y2 - y1) * pad
    x1, y1 = int(max(0, x1 - px)), int(max(0, y1 - py))
    x2, y2 = int(min(w, x2 + px)), int(min(h, y2 + py))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    return image[y1:y2, x1:x2]


def read(patch: np.ndarray) -> tuple[str, float]:
    """One crop to (text, confidence). Empty string when nothing was read.

    A field crop is a single line of text, so recognition runs directly on it
    and PP-OCR's *detector* is skipped. That is not only faster - the detector
    is trained on pages and fragments a short crop, splitting "02/11/1998" into
    "02", "/11", "/1998" with overlapping boxes that rejoin as "02/11//1998"
    and fail to parse as a date. Recognition-only returns it whole.

    An address wraps, so anything tall enough to hold more than one line keeps
    the detector.
    """
    if patch is None or patch.size == 0:
        return "", 0.0

    h, w = patch.shape[:2]
    if h < 32:
        factor = 32 / h
        patch = cv2.resize(patch, None, fx=factor, fy=factor,
                           interpolation=cv2.INTER_CUBIC)

    engine = registry.ocr_engine()
    if w / max(h, 1) >= SINGLE_LINE_ASPECT:
        result, _elapse = engine(patch, use_det=False, use_cls=False, use_rec=True)
        if not result:
            return "", 0.0
        # Recognition-only returns (text, confidence) pairs, with no box. The
        # split/join also drops the ideographic space PP-OCR pads lines with.
        text = " ".join(" ".join(str(row[0]).split()) for row in result).strip()
        confidence = min((float(row[1]) for row in result), default=0.0)
        return text, confidence

    result, _elapse = engine(patch)
    if not result:
        return "", 0.0

    # Reading order: top to bottom, then left to right. The row tolerance is a
    # fraction of the median glyph height rather than a fixed pixel count.
    heights = sorted(_height(r[0]) for r in result)
    tolerance = max(4.0, heights[len(heights) // 2] * 0.6)
    lines = sorted(result, key=lambda r: (round(_top(r[0]) / tolerance), _left(r[0])))
    text = " ".join(" ".join(str(r[1]).split()) for r in lines if str(r[1]).strip())
    confidence = min((float(r[2]) for r in lines), default=0.0)
    return text, confidence


def _top(box) -> float:
    return min(p[1] for p in box)


def _left(box) -> float:
    return min(p[0] for p in box)


def _height(box) -> float:
    return max(p[1] for p in box) - min(p[1] for p in box)


# ------------------------------------------------------------------- MRZ

def coerce_mrz(text: str) -> str:
    """Best-effort repair to the OCR-B charset. Never invents a character.

    Anything still outside the charset after this is left alone, so the parser
    rejects the strip and the check is `inconclusive` - rather than a silently
    corrected string that fails a check digit and reads as forgery.
    """
    for wrong, right in _MRZ_SUBSTITUTIONS.items():
        text = text.replace(wrong, right)
    return re.sub(r"[ \t]+", "", text.upper())


def apply_positional_charset(lines: list[str]) -> list[str]:
    """Repair OCR-B glyph confusions using the layout ICAO already specifies.

    This is not guesswork. Doc 9303 fixes which positions are alphabetic and
    which are numeric, so a digit sitting in the nationality field is a
    recognition error with exactly one sensible reading.

    It matters because the composite check digit covers positions 1-10, 14-20
    and 22-43 of line 2 - and *not* 11-13, the nationality. Measured on a
    rendered strip, PP-OCRv4 read IND as 1ND while all five check digits still
    verified. Layer B would then have reported "nationality 1ND is not a
    recognised country code" on a genuine passport: a false accusation, arrived
    at confidently, against a real traveller.

    Coercion cannot manufacture a passing check digit. In digit-only positions
    it only maps letters to digits, and a wrong repair still fails its check
    digit one time in ten less often than the unrepaired read does.
    """
    if len(lines) != 2:
        return lines

    first = lines[0].translate(_TO_ALPHA)      # line 1 is alphabetic throughout
    second = []
    for i, ch in enumerate(lines[1]):
        if ch == "<":
            second.append(ch)
        elif i in _L2_DIGITS:
            second.append(ch.translate(_TO_DIGIT))
        elif i in _L2_ALPHA:
            second.append(ch.translate(_TO_ALPHA))
        else:
            second.append(ch)
    return [first, "".join(second)]


def read_mrz(patch: np.ndarray) -> tuple[str | None, float, str]:
    """Read the MRZ strip. Returns (strip or None, confidence, reason).

    None means "do not hand this to Layer A". The check digits are a powerful
    validator but they cannot tell a forged document from a bad scan, so the
    geometry check has to happen first.
    """
    if patch is None or patch.size == 0:
        return None, 0.0, "the machine-readable zone crop was empty"

    if patch.shape[0] < 48:
        factor = 48 / patch.shape[0]
        patch = cv2.resize(patch, None, fx=factor, fy=factor,
                           interpolation=cv2.INTER_CUBIC)

    result, _elapse = registry.ocr_engine()(patch)
    if not result:
        return None, 0.0, "no text could be recognised in the machine-readable zone"

    rows = sorted(result, key=lambda r: _top(r[0]))
    lines = [coerce_mrz(str(r[1])) for r in rows]
    lines = [l for l in lines if l]
    lines = apply_positional_charset(lines)
    confidence = min((float(r[2]) for r in rows), default=0.0)

    bad = {c for line in lines for c in line} - set(CHARSET)
    if bad:
        return None, confidence, (
            f"the machine-readable zone contains characters that cannot appear "
            f"in it ({''.join(sorted(bad))[:8]}), so it was not read"
        )

    shape = (len(lines), len(lines[0]) if lines else 0)
    if not all(len(l) == shape[1] for l in lines) or shape not in MRZ_GEOMETRY:
        got = "/".join(str(len(l)) for l in lines) or "0"
        return None, confidence, (
            f"the machine-readable zone read as {len(lines)} lines of {got} "
            f"characters, which is not a valid layout, so it was not used"
        )

    return "\n".join(lines), confidence, ""


# ------------------------------------------------------------------- run

def run(ctx: ScreeningContext) -> list[Signal]:
    """OCR every located field. Mutates ctx.fields; returns signals.

    A field already present from a verified signed payload is left alone: that
    value is proven by a signature and an OCR read is not.
    """
    from modules.extraction import TEXT_CLASSES, normalise_field

    source = ctx.warped if ctx.warped is not None else ctx.image
    signals: list[Signal] = []

    for name, box in sorted(ctx.field_boxes.items()):
        if name not in TEXT_CLASSES:
            continue                       # graphics carry no value to read
        if name == "mrz":
            signals += _read_mrz_field(ctx, source, box)
            continue
        if name in ctx.fields and ctx.fields[name].source == "qr":
            continue                       # signed value wins over a read

        signals += _read_text_field(ctx, source, name, box)

    return signals


def _read_text_field(ctx: ScreeningContext, source, name: str, box) -> list[Signal]:
    from modules.extraction import normalise_field

    started = time.perf_counter()
    text, confidence = read(crop(source, box))
    ms = int((time.perf_counter() - started) * 1000)
    sid = f"extraction.ocr.{name}.confidence"
    shown = field_label(name)

    if not text:
        return [_unread(sid, name, f"The {shown} could not be read from the "
                                   f"document", ms, region=box)]

    if confidence < MIN_CONFIDENCE:
        return [_unread(sid, name,
                        f"The {shown} read as {text!r} but too faintly to rely "
                        f"on ({confidence * 100:.0f}%). Re-capture at a higher "
                        f"resolution.", ms, region=box)]

    field = normalise_field(name, text, "ocr", confidence, box=tuple(box))
    if field is None and " " in text:
        # PP-OCR emits one box per glyph run, so a date or an identity number
        # comes back as fragments joined by spaces. A name needs those spaces
        # and a date must not have them, so rather than guess per field, try
        # the joined form when the spaced one is not a valid value.
        field = normalise_field(name, text.replace(" ", ""), "ocr", confidence,
                                box=tuple(box))
    if field is None:
        # Read something, but it is not a valid value for this field - a date
        # that is not a date. Storing it would let a garbled read become a
        # confident mismatch three layers later.
        return [_unread(sid, name,
                        f"The {shown} read as {text!r}, which is not a valid "
                        f"{shown}", ms, region=box)]

    ctx.fields[name] = field
    return [Signal(
        id=sid, module="extraction", tier=1, verdict="pass",
        confidence=confidence, trust_class="probabilistic", hard_fail=False,
        anchor=f"field:{name}",
        evidence=f"Read the {shown} as {field.value}, confidence "
                 f"{confidence * 100:.0f}%",
        region=tuple(box), latency_ms=ms,
    )]


def _read_mrz_field(ctx: ScreeningContext, source, box) -> list[Signal]:
    started = time.perf_counter()
    strip, confidence, reason = read_mrz(crop(source, box, pad=0.02))
    ms = int((time.perf_counter() - started) * 1000)
    sid = "extraction.ocr.mrz.confidence"

    if strip is None:
        return [_unread(sid, "mrz", reason[:1].upper() + reason[1:], ms, region=box)]

    # This one line switches on all five ICAO check digits in Layer A and the
    # whole VIZ/MRZ cross-check in Layer C. Both are already written and tested.
    ctx.fields["mrz"] = NormalizedField(
        raw=strip, value="", source="mrz", confidence=confidence,
        box=tuple(box),
    )
    lines = strip.count("\n") + 1
    return [Signal(
        id=sid, module="extraction", tier=1, verdict="pass",
        confidence=confidence, trust_class="probabilistic", hard_fail=False,
        anchor="field:mrz",
        evidence=f"Read the machine-readable zone, {lines} lines of "
                 f"{len(strip.split(chr(10))[0])} characters, confidence "
                 f"{confidence * 100:.0f}%",
        region=tuple(box), latency_ms=ms,
    )]


def _unread(sid: str, name: str, evidence: str, ms: int, region=None) -> Signal:
    """Read failed. `inconclusive`, so it costs coverage rather than passing."""
    return Signal(
        id=sid, module="extraction", tier=1, verdict="inconclusive",
        confidence=0.0, trust_class="probabilistic", hard_fail=False,
        anchor=f"field:{name}", evidence=evidence,
        region=tuple(region) if region else None, latency_ms=ms,
    )
