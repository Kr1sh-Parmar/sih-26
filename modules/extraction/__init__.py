"""Extraction. Quality gate and QR are real; the detector, OCR and the VLM
fallback are stubs.

What works today, with no model at all: the capture quality gate, and the
signed payload carried in a QR. That is enough to run the whole cryptographic
and cross-document path end to end - which is the headline demo - because the
signature covers the field values themselves.

What does not work yet is reading the printed page. Until the field detector
and OCR land, a document with no QR yields no fields, its checks come back
`inconclusive`, and the coverage floor turns the verdict AMBER. That is the
system behaving correctly, not a gap being papered over.
"""
import time

from core.canonical import FIELD_ORDER
from core.quality import check as quality_check
from fusion.context import NormalizedField, ScreeningContext
from fusion.signal import Signal
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
    """Populate ctx.fields from a verified signed payload.

    Source is `qr`, and these values are proven by the signature - which is why
    fusion is allowed to suppress probabilistic disputes about them.
    """
    seeded = []
    for name in FIELD_ORDER:
        if name in ("doc_type",) or not payload.get(name):
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

    signals += _unread_fields(ctx)
    return signals


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
    """One signal per declared text field we could not read.

    These land in the officer console as "could not evaluate X", which is the
    difference between an honest AMBER and a black box.
    """
    started = time.perf_counter()
    declared = [c for c in ctx.profile["extract"]["detector_classes"]
                if c in TEXT_CLASSES]
    out = []
    for name in declared:
        if name in ctx.fields:
            continue
        out.append(Signal(
            id=f"extraction.field.{name}.confidence", module="extraction", tier=1,
            verdict="inconclusive", confidence=0.0, trust_class="probabilistic",
            hard_fail=False, anchor=f"field:{name}",
            evidence=f"The {name.replace('_', ' ')} could not be read - the field "
                     f"detector and OCR are not yet deployed",
            latency_ms=int((time.perf_counter() - started) * 1000),
        ))
    return out
