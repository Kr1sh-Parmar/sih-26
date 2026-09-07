"""Extraction. Quality gate, QR, field detection and OCR.

The order matters and is not arbitrary:

    quality -> QR envelope -> detect -> OCR crops -> normalise
                                          |
                       caller then seeds the verified signed payload

OCR reads the card first; the orchestrator seeds the signed payload afterwards,
and `seed_from_payload` declines to overwrite anything OCR or the MRZ produced.
A signed value is proven and an OCR read is only a guess at the same ink - but
the printed value is the thing that has to survive in order to disagree. See
`seed_from_payload`, which is where that nearly went wrong.

When the detector weights are absent - a normal state, the repository ships
without them until they are trained - every declared text field falls back to
an `inconclusive` signal. The coverage floor then turns the verdict AMBER:
nothing was read, so nothing disagreed, and that must not be a pass (D9).

The VLM fallback (Florence-2) is still a stub.
"""
import time

from core.canonical import FIELD_ORDER
from core.profiles import field_label
from core.quality import check as quality_check
from core.registry import FIELD_DETECTOR, available
from fusion.context import NormalizedField, ScreeningContext
from fusion.signal import Signal
from modules.extraction import detect, ocr
from modules.extraction import normalize as N
from modules.extraction import qr

#: Ontology classes that carry text. The rest are graphics and have no value to
#: read, so a missing one is not a coverage gap in the same sense.
TEXT_CLASSES = {
    "name", "father_name", "dob", "gender", "address", "nationality",
    "id_number", "secondary_id", "issue_date", "expiry_date",
    "issuing_authority", "blood_group", "doc_title", "mrz",
}

#: Normaliser per field. A value that will not normalise is not stored, because
#: an unreadable field must become `inconclusive` downstream rather than a
#: plausible-looking string nobody can check.
NORMALISERS = {
    "name": N.name,
    "father_name": N.name,
    "dob": lambda v: N.iso_date(v, past=True),
    "issue_date": lambda v: N.iso_date(v),
    "expiry_date": lambda v: N.iso_date(v),
    "gender": N.gender,
    "id_number": N.id_number,
    "secondary_id": N.id_number,
    "nationality": lambda v: str(v or "").strip().upper(),
}


def normalise_field(name: str, raw: str, source: str, confidence: float,
                    box=None) -> NormalizedField | None:
    norm = NORMALISERS.get(name, lambda v: " ".join(str(v).split()))
    value = norm(raw)
    if value in (None, ""):
        return None
    return NormalizedField(raw=str(raw), value=value, source=source,
                           confidence=confidence, box=box)


def seed_from_payload(ctx: ScreeningContext, payload: dict) -> list[str]:
    """Fill ctx.fields from a verified signed payload, without clobbering OCR.

    Source is `qr`, and these values are proven by the signature - which is why
    fusion is allowed to suppress probabilistic disputes about them.

    **It must not overwrite a field OCR actually read off the card.** That is
    not a preference, it is the whole VIZ/MRZ premise. A forger alters the
    printed date of birth and leaves the signed payload and the MRZ alone; if
    the signed value replaced the printed one in ctx.fields, Layer C would then
    compare the signature against the MRZ - two things that of course agree -
    and the alteration would be invisible. The printed value has to survive to
    be the thing that disagrees.

    The signed payload is not lost: it stays in ctx.fields["signed_payload"],
    and Layer D reads it from the verification result rather than from here.
    """
    seeded = []
    for name in FIELD_ORDER:
        if name in ("doc_type",) or not payload.get(name):
            continue
        existing = ctx.fields.get(name)
        if existing is not None and existing.source in ("ocr", "mrz"):
            continue
        field = normalise_field(name, payload[name], "qr", 1.0)
        if field:
            ctx.fields[name] = field
            seeded.append(name)
    return seeded


def run(ctx: ScreeningContext, *, uploaded: bool = False,
        declared_type: bool = True) -> list[Signal]:
    """Tier 1 extraction. Mutates ctx.fields; returns signals."""
    signals: list[Signal] = list(quality_check(ctx.image))
    signals += _doctype(ctx, declared_type)

    payload, qr_signals = qr.scan(ctx.image, ctx.profile)
    signals += qr_signals
    if payload:
        ctx.fields["signed_payload"] = NormalizedField(
            raw=payload, value="", source="qr", confidence=1.0
        )

    # OCR runs before the caller seeds the signed payload, so the printed value
    # lands first and `seed_from_payload` then declines to overwrite it. Reading
    # the card is the point; the signature is the thing it gets checked against.
    signals += detect.run(ctx)
    if ctx.field_boxes:
        signals += ocr.run(ctx)
    else:
        signals += _mrz_from_its_fixed_position(ctx)

    signals += _fallback(ctx, signals)
    signals += _unread_fields(ctx)
    return signals


#: ICAO 9303 puts the machine-readable zone in a fixed band at the foot of the
#: data page. That is a published layout, not a guess, and it is the one field on
#: any of these documents whose position is specified by an international
#: standard rather than by a national design.
MRZ_BAND_TOP = 0.75


def _mrz_from_its_fixed_position(ctx: ScreeningContext) -> list[Signal]:
    """Read the MRZ without a detector, from where the standard says it is.

    This exists because the detector is the long pole: it is training on a GPU
    elsewhere, and until it lands `ctx.field_boxes` is empty and nothing is read
    off any document. But the MRZ does not need a learned detector to be found -
    ICAO fixes it at the bottom of the page - and it is the single most valuable
    field on a passport, because it is the only one on any of these six document
    types whose correctness is verifiable arithmetically.

    Reading it here switches on all five ICAO check digits in Layer A and the
    whole VIZ/MRZ cross-check in Layer C, both already written and tested.

    **The read is self-tested, and that is the load-bearing part.** Measured over
    30 generated passports this path reads 70% of them character-exact; the rest
    produce a well-formed 44-character strip with a wrong character in it. Handed
    straight to Layer A those fail a check digit, and a failed composite check
    digit is a hard fail - so a fifth of genuine passports would be detained on
    an OCR error. PP-OCR's confidence does not separate the two: the misreads
    scored *higher* on average (0.791 median) than the exact reads (0.751).

    So the ICAO check digits are used here as a **test of the read** before the
    strip is stored, rather than as a verdict about the document. If they fail,
    the honest statement is that the zone could not be read reliably, not that it
    was altered - because with a reader this accurate, a failure is far more
    likely a misread than a forgery.

    The cost is stated plainly: **this path can confirm a good machine-readable
    zone and can never report a tampered one.** That is a real loss, and it is
    smaller than the alternative, because without a detector nothing was read at
    all. It changes when the detector lands: a tight crop is a different accuracy
    regime, and `_read_mrz_field` - the detector-fed path - deliberately keeps
    the geometry gate alone so that forgery detection survives there.
    """
    if "mrz" not in ctx.profile["extract"]["detector_classes"]:
        return []
    if "mrz" in ctx.fields:
        return []

    image = ctx.warped if ctx.warped is not None else ctx.image
    height = image.shape[0]
    band = image[int(height * MRZ_BAND_TOP):, :]
    box = (0, int(height * MRZ_BAND_TOP), image.shape[1], height)

    started = time.perf_counter()
    strip, confidence, reason = ocr.read_mrz(band)
    ms = int((time.perf_counter() - started) * 1000)
    sid = "extraction.ocr.mrz.confidence"

    if strip is None:
        return [Signal(
            id=sid, module="extraction", tier=1, verdict="inconclusive",
            confidence=0.0, trust_class="probabilistic", hard_fail=False,
            anchor="field:mrz",
            evidence=f"{reason[:1].upper()}{reason[1:]}", region=box,
            latency_ms=ms,
        )]

    if not _check_digits_verify(strip):
        return [Signal(
            id=sid, module="extraction", tier=1, verdict="inconclusive",
            confidence=0.0, trust_class="probabilistic", hard_fail=False,
            anchor="field:mrz",
            evidence="The machine-readable zone was located but could not be "
                     "read reliably - its own check digits do not agree with "
                     "the characters read. Re-capture at a higher resolution.",
            region=box, latency_ms=ms,
        )]

    ctx.fields["mrz"] = NormalizedField(raw=strip, value="", source="mrz",
                                        confidence=confidence, box=box)
    lines = strip.splitlines()
    return [Signal(
        id=sid, module="extraction", tier=1, verdict="pass",
        confidence=confidence, trust_class="probabilistic", hard_fail=False,
        anchor="field:mrz",
        evidence=f"Read the machine-readable zone from its standard position at "
                 f"the foot of the page, {len(lines)} lines of {len(lines[0])} "
                 f"characters, confidence {confidence * 100:.0f}%",
        region=box, latency_ms=ms,
    )]


def _check_digits_verify(strip: str) -> bool:
    """Do the strip's own ICAO check digits agree with the characters read?

    Used as a self-test on an untargeted read, never as a verdict. See
    `_mrz_from_its_fixed_position`.
    """
    from modules.extraction import mrz as mrz_parser

    try:
        parsed = mrz_parser.parse(strip)
    except mrz_parser.MRZError:
        return False
    if not parsed.check_digits:
        return False
    return all(mrz_parser.verify(value, digit)
               for value, digit in parsed.check_digits.values())


def _fallback(ctx: ScreeningContext, so_far: list[Signal]) -> list[Signal]:
    """Florence-2, when the normal path did not read the document.

    Two triggers. The documented one is a field OCR located and read too
    faintly to rely on. The one that matters today is the other: with no
    detector weights `ocr.run` never runs at all, so *nothing* is read, and
    `<OCR_WITH_REGION>` is the only reader left that does not need a field box
    to aim at.

    It fires at most once per document. Eight seconds is the ceiling and this
    is the fallback, not a second opinion - running it per unread field would
    multiply that by however many fields were unreadable.
    """
    from modules.extraction import vlm

    nothing_located = not ctx.field_boxes
    # No trailing dot on the prefix, deliberately: the contract guard in
    # tests/test_contracts.py scans the source for anything shaped like a signal
    # id, and a prefix ending in a dot reads as one that was never registered.
    unread = [s for s in so_far
              if s.id.startswith("extraction.ocr") and s.verdict == "inconclusive"]
    if not (nothing_located or unread):
        return []

    reason = ("nothing was located on the document - the field detector is not "
              "deployed" if nothing_located else
              f"{len(unread)} field(s) were located but could not be read")
    return vlm.run(ctx, reason=reason)


def _doctype(ctx: ScreeningContext, declared: bool) -> list[Signal]:
    if declared:
        # The officer selected the type at the counter. That is not an
        # inference, so there is nothing for the classifier to be right about.
        return [Signal(
            id="extraction.doctype.confidence", module="extraction", tier=1,
            verdict="not_applicable", confidence=1.0, trust_class="arithmetic",
            hard_fail=False, anchor="document",
            evidence=f"Document type {ctx.profile['doc_type']} was selected at "
                     f"the counter, so automatic classification did not run",
        )]
    return [Signal(
        id="extraction.doctype.confidence", module="extraction", tier=1,
        verdict="inconclusive", confidence=0.0, trust_class="probabilistic",
        hard_fail=False, anchor="document",
        evidence="The document type classifier is not yet deployed",
    )]


def _unread_fields(ctx: ScreeningContext) -> list[Signal]:
    """One signal per declared text field that was never located.

    These land in the officer console as "could not evaluate X", which is the
    difference between an honest AMBER and a black box.

    A field that *was* located but could not be read is OCR's to report, under
    `extraction.ocr.<name>.confidence`. Reporting it here as well would charge
    coverage twice for one problem and show the officer the same gap in two
    places - the same mistake as summing correlated signals (D8).
    """
    started = time.perf_counter()
    deployed = available(FIELD_DETECTOR)
    declared = [c for c in ctx.profile["extract"]["detector_classes"]
                if c in TEXT_CLASSES]
    why = ("could not be located on this document" if deployed else
           "could not be read - the field detector is not yet deployed")

    out = []
    for name in declared:
        if name in ctx.fields or name in ctx.field_boxes:
            continue
        out.append(Signal(
            id=f"extraction.field.{name}.confidence", module="extraction", tier=1,
            verdict="inconclusive", confidence=0.0, trust_class="probabilistic",
            hard_fail=False, anchor=f"field:{name}",
            evidence=f"The {field_label(name)} {why}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        ))
    return out
