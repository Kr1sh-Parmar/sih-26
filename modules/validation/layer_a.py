"""Layer A - intra-document integrity. Cryptographic and arithmetic.

The backbone. Ed25519 over the canonical payload, the five ICAO MRZ check
digits, Verhoeff on Aadhaar, and the structural anchors for the three documents
that have nothing better.

`NO_CRYPTO_ANCHOR` is the honest state for a document with no verifiable
signature. It is not a pass, and it must not be presented as one.
"""
import time

from core.profiles import describe, describe_start
from core.trust import TrustAnchorStore, verify_payload
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import mrz as MRZ
from modules.validation import anchor_for, box_of, emit, raw_of, value_of
from modules.validation.checksums import (
    check_aadhaar, check_dl, check_epic, check_pan,
)

#: Which MRZ check digit belongs to which printed field, for the overlay.
_MRZ_ANCHORS = {
    "document_number": "id_number",
    "dob": "dob",
    "expiry": "expiry_date",
    "optional": "secondary_id",
}


def run(ctx: ScreeningContext, anchors: TrustAnchorStore | None = None) -> list[Signal]:
    return (
        _signature(ctx, anchors)
        + _mrz_check_digits(ctx)
        + _document_anchor(ctx)
    )


# ------------------------------------------------------------- signature

def _signature(ctx: ScreeningContext, anchors: TrustAnchorStore | None) -> list[Signal]:
    started = time.perf_counter()
    profile = ctx.profile
    declared = profile["verify"]["signature"] != "none"
    envelope = raw_of(ctx, "signed_payload")

    if not declared:
        return [emit(profile, "validation.signature.valid", "not_applicable",
                     f"{describe_start(profile['doc_type'])} carries no signature, so it has no "
                     f"cryptographic anchor of its own",
                     trust="unverified", started=started)]

    if not envelope:
        # NO_CRYPTO_ANCHOR. Inconclusive, not pass - it costs coverage, which is
        # exactly right: we learned nothing about this document cryptographically.
        return [emit(profile, "validation.signature.valid", "inconclusive",
                     "No signed payload was found, so this document has no "
                     "cryptographic anchor",
                     trust="unverified", confidence=0.0, started=started)]

    if anchors is None or not len(anchors):
        return [emit(profile, "validation.signature.valid", "inconclusive",
                     "The trust anchor store holds no issuer keys, so the "
                     "signature could not be checked",
                     trust="unverified", confidence=0.0, started=started)]

    v = verify_payload(envelope, anchors)
    signals = [emit(profile, "validation.signature.valid",
                    "pass" if v.ok else "fail", v.detail,
                    trust="cryptographic", started=started)]

    if v.issuer_id:
        trusted = v.state != "UNKNOWN_ISSUER"
        signals.append(emit(
            profile, "validation.signature.issuer_trusted",
            "pass" if trusted else "fail",
            f"Issuer {v.issuer_id} is present in the trust anchor store" if trusted
            else f"Issuer {v.issuer_id} is not present in the trust anchor store",
            trust="cryptographic",
        ))
    return signals


def verified_payload(ctx: ScreeningContext, anchors: TrustAnchorStore | None):
    """The verification result, for the orchestrator to seed fields and for
    fusion's signed-field set. Returns None when there is nothing to verify."""
    envelope = raw_of(ctx, "signed_payload")
    if not envelope or anchors is None:
        return None
    return verify_payload(envelope, anchors)


# --------------------------------------------------------- MRZ check digits

def _mrz_check_digits(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    profile = ctx.profile
    has_mrz = "mrz" in profile["extract"]["detector_classes"]
    region = box_of(ctx, "mrz")

    if not has_mrz:
        # Aadhaar genuinely has no MRZ. not_applicable, excluded from coverage.
        return [emit(profile, "validation.mrz.checkdigit.composite", "not_applicable",
                     f"{describe_start(profile['doc_type'])} has no machine-readable zone",
                     started=started)]

    strip = raw_of(ctx, "mrz")
    if not strip:
        return [emit(profile, "validation.mrz.checkdigit.composite", "inconclusive",
                     "The machine-readable zone could not be read",
                     confidence=0.0, region=region, started=started)]

    try:
        parsed = MRZ.parse(strip)
    except MRZ.MRZError as exc:
        return [emit(profile, "validation.mrz.checkdigit.composite", "inconclusive",
                     f"The machine-readable zone could not be parsed: {exc}",
                     confidence=0.0, region=region, started=started)]

    signals = []
    for name, (value, digit) in parsed.check_digits.items():
        ok = MRZ.verify(value, digit)
        field = _MRZ_ANCHORS.get(name)
        label = name.replace("_", " ")
        signals.append(emit(
            profile, f"validation.mrz.checkdigit.{name}",
            "pass" if ok else "fail",
            f"MRZ {label} check digit {digit} is correct" if ok else
            f"MRZ {label} check digit is {digit}, but the printed characters "
            f"give {MRZ.check_digit(value)}",
            anchor=anchor_for(field) if field else "document",
            region=region, started=started,
        ))
    return signals


# ----------------------------------------------------- per-document anchor

def _document_anchor(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    profile = ctx.profile
    doc_type = profile["doc_type"]
    number = value_of(ctx, "id_number")
    region = box_of(ctx, "id_number")
    sid = f"validation.format.{doc_type}.id_number"

    if doc_type in ("passport", "visa"):
        return []      # the MRZ check digits are the anchor

    if not number:
        return [emit(profile, sid, "inconclusive",
                     "The identity number could not be read",
                     confidence=0.0, anchor=anchor_for("id_number"),
                     region=region, started=started)]

    if doc_type == "aadhaar":
        ok, detail = check_aadhaar(number)
        return [emit(profile, "validation.verhoeff.aadhaar",
                     "pass" if ok else "fail", detail,
                     anchor=anchor_for("id_number"), region=region, started=started)]

    if doc_type == "pan":
        surname = _surname(value_of(ctx, "name"))
        ok, detail = check_pan(number, surname)
    elif doc_type == "voter_id":
        ok, detail = check_epic(number)
    elif doc_type == "dl":
        ok, detail = check_dl(number)
    else:
        return []

    return [emit(profile, sid, "pass" if ok else "fail", detail,
                 anchor=anchor_for("id_number"), region=region, started=started)]


def _surname(full_name: str | None) -> str | None:
    """Last token of a printed Indian name. Good enough for the PAN fifth
    character, and wrong often enough that a mismatch is reported as a format
    failure rather than a hard fail."""
    if not full_name:
        return None
    parts = full_name.split()
    return parts[-1] if parts else None
