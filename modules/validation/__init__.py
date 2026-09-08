"""Validation, six layers. context/MODULES.md, Module 2.

Every layer is a pure function of the context: no I/O, no mutation beyond the
signals it returns. Layers A and E need a trust anchor store and a watchlist,
which are injected rather than opened, so each layer stays unit-testable with a
hand-built ScreeningContext and no fixture on disk.

Layers A to D combined are budgeted at under 15 ms. They are the backbone and
the fast path: a checksum failure, an invalid signature, an expired document or
a watchlist hit returns RED before a single model runs.
"""
import time

from fusion.context import ScreeningContext
from fusion.signal import Signal


def emit(profile: dict, sid: str, verdict: str, evidence: str, *,
         trust="arithmetic", confidence=1.0, anchor="document", tier=1,
         region=None, started=None) -> Signal:
    """Build a validation Signal, taking hard_fail from the profile.

    A module cannot decide its own importance, and it should not have to
    remember which of six documents treats its check as fatal.
    """
    from core.profiles import is_hard_fail
    return Signal(
        id=sid, module="validation", tier=tier, verdict=verdict,
        confidence=confidence, trust_class=trust,
        hard_fail=is_hard_fail(profile, sid), anchor=anchor,
        evidence=evidence, region=region,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0,
    )


#: Sources whose reading is exact enough to *contradict* a value that has been
#: proven cryptographically or read from a machine-readable zone.
#:
#: `vlm` is deliberately absent. The Florence-2 fallback transcribes a date
#: correctly and then returns CHABRA for CHHABRA - see data/EXTRACTION.md. That
#: is fine for filling a gap in an evidence list and fatal for a comparison: a
#: one-character misread against a signed payload fires
#: `validation.crossdoc.name_mismatch`, which is a hard fail on four profiles,
#: carrying trust class `cryptographic` because the *other* side of the
#: comparison is signed. A genuine document would be detained on an OCR error,
#: reported with the strongest certainty the system has.
#:
#: A disagreement between a proven value and an unchecked fallback read is not
#: evidence of tampering. It is evidence that the read was unreliable, and the
#: honest verdict is `inconclusive` - which costs coverage, because agreement
#: genuinely was not established (D9).
COMPARABLE_SOURCES = frozenset({"ocr", "mrz", "qr"})

#: Sources that are actually *ink on the document*. The signed QR payload is
#: not one of them, and the distinction is the whole VIZ/MRZ premise.
#:
#: The VIZ/MRZ check exists to catch a forger who alters the printed date and
#: leaves the machine-readable zone alone. Both of those live on the card. The
#: signed payload does not - it is what the issuer put in the QR, and the
#: issuer generated it and the MRZ together from one record. Comparing them
#: proves they agree with each other and says nothing whatever about the print.
#:
#: Treating `qr` as a printed value made every VIZ/MRZ check pass on a passport
#: whose printed fields were never read, with the evidence string "matches
#: printed" naming a value that was never printed anywhere. A document with the
#: entire printed band wiped and retyped scored GREEN.
#: `vlm` belongs here: the fallback reader reads ink off the page, so its
#: output IS a printed value - just an unreliable one, which is what
#: COMPARABLE_SOURCES separately keeps out of a dispute. `qr` is the only
#: source that never touched the document.
PRINTED_SOURCES = frozenset({"ocr", "mrz", "vlm"})


def source_of(ctx: ScreeningContext, field: str) -> str | None:
    f = ctx.fields.get(field)
    return f.source if f else None


def comparable(ctx: ScreeningContext, field: str) -> bool:
    """True when this field was read well enough to dispute a proven value."""
    f = ctx.fields.get(field)
    return bool(f and f.value and f.source in COMPARABLE_SOURCES)


def is_printed(ctx: ScreeningContext, field: str) -> bool:
    """True when this value was read off the document rather than out of a QR.

    Two callers, for the same reason. The VIZ/MRZ check compares print against
    the machine-readable zone; the within-document signature check compares
    print against this card's own payload. Both are claims about ink, and a
    value lifted out of the QR cannot corroborate the QR.

    Layer D's *cross-document* half deliberately does not use this: there the
    payload belonging to a different document is the entire point.
    """
    f = ctx.fields.get(field)
    return bool(f and f.value and f.source in PRINTED_SOURCES)


def value_of(ctx: ScreeningContext, field: str) -> str | None:
    f = ctx.fields.get(field)
    return f.value if f and f.value else None


def raw_of(ctx: ScreeningContext, field: str) -> str | None:
    f = ctx.fields.get(field)
    return f.raw if f and f.raw else None


def box_of(ctx: ScreeningContext, field: str):
    f = ctx.fields.get(field)
    if f and f.box:
        return tuple(f.box)
    box = ctx.field_boxes.get(field)
    return tuple(box) if box else None


def anchor_for(field: str) -> str:
    return f"field:{field}"


def run(ctx: ScreeningContext, *, anchors=None, store=None) -> list[Signal]:
    """All six layers, in order. Returns signals; does not mutate ctx.signals."""
    from modules.validation import layer_a, layer_b, layer_c, layer_d, layer_e, layer_f

    signals: list[Signal] = []
    signals += layer_a.run(ctx, anchors=anchors)
    signals += layer_b.run(ctx)
    signals += layer_c.run(ctx)
    signals += layer_d.run(ctx, anchors=anchors)
    if store is not None:
        signals += layer_e.run(ctx, store=store)
        signals += layer_f.run(ctx, store=store)
    return signals
