"""Layer D - cross-document trust propagation. The headline (D19).

Four of six Indian identity documents carry no cryptographic integrity today.
When one document in a session *is* signed, its verified payload becomes ground
truth for the others presented alongside it:

    signed document verifies
      -> its name / date of birth / gender are PROVEN
      -> compare against the unsigned document's printed fields
      -> a mismatch is a hard fail with cryptographic backing

Officer scans an Aadhaar and a PAN together. The signed Aadhaar payload says
1996, the PAN prints 1998. No machine learning anywhere in that sentence.

The trust class of the resulting signal is `cryptographic` only because one
side of the comparison is. If no prior document in the session was signed,
there is nothing to propagate and this layer stays silent rather than inventing
a weaker version of itself.
"""
import time

from core.profiles import field_label, label
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import normalize as N
from modules.validation import (anchor_for, box_of, comparable, emit,
                                is_printed, source_of, value_of)

#: How to compare each propagated field. Same normalisers as the VIZ/MRZ check,
#: so the two layers cannot disagree about what "equal" means.
COMPARE = {
    "name": N.name,
    "father_name": N.name,
    "dob": lambda v: N.iso_date(v),
    "gender": N.gender,
    "nationality": lambda v: str(v or "").strip().upper(),
}


def signed_priors(ctx: ScreeningContext) -> list[dict]:
    """Prior documents in this session whose signature actually verified.

    A prior document that failed verification proves nothing and must not be
    used as ground truth - that would let a forged Aadhaar condemn a genuine
    PAN.
    """
    return [
        d for d in ctx.prior_docs
        if d.get("verified") and d.get("payload")
    ]


def run(ctx: ScreeningContext, *, anchors=None) -> list[Signal]:
    return _own_signature(ctx, anchors) + _cross_document(ctx)


def _own_signature(ctx: ScreeningContext, anchors) -> list[Signal]:
    """The printed fields against THIS document's own verified payload.

    The hole this closes. Layer D compared a signed document against the *other*
    documents in the session and never against the card carrying the signature,
    so a genuine signed Aadhaar with its printed date of birth altered - the QR
    left alone, so the signature still verifies - produced no failing signal at
    all. Measured: printed 1988-11-02 against a signed payload of 1960-03-24,
    zero failures.

    A signature proves the payload. It says nothing about the ink until someone
    compares the two, and until this ran, nobody did.

    Stronger evidence than the cross-document form and weighted accordingly:
    there is one physical card here, and the signature travels on it.
    """
    from modules.validation import layer_a

    started = time.perf_counter()
    fields = ctx.profile["verify"].get("cross_document") or []
    if not fields:
        return []

    verification = layer_a.verified_payload(ctx, anchors)
    if not verification or not verification.ok or not verification.payload:
        return []

    payload = verification.payload
    out: list[Signal] = []
    for field in fields:
        if field not in COMPARE:
            continue
        proven = payload.get(field)
        if not proven:
            continue

        sid = f"validation.signed.{field}_mismatch"
        shown = field_label(field)
        box = box_of(ctx, field)
        printed = value_of(ctx, field)

        if not printed:
            out.append(emit(
                ctx.profile, sid, "inconclusive",
                f"The printed {shown} could not be read, so it could not be "
                f"checked against this document's own signature",
                trust="cryptographic", confidence=0.0,
                anchor=anchor_for(field), region=box, started=started))
            continue

        if not is_printed(ctx, field):
            # The value came out of the very payload we would be checking it
            # against. Comparing a signature with itself always agrees and
            # proves nothing - the same mistake the VIZ/MRZ check made.
            out.append(emit(
                ctx.profile, sid, "inconclusive",
                f"The {shown} shown was taken from the signed payload itself, "
                f"not read off the card, so it cannot corroborate that payload",
                trust="cryptographic", confidence=0.0,
                anchor=anchor_for(field), region=box, started=started))
            continue

        if not comparable(ctx, field):
            out.append(emit(
                ctx.profile, sid, "inconclusive",
                f"The {shown} was only recovered by the fallback reader, which "
                f"cannot be relied on to the character, so it is not used to "
                f"dispute this document's signature",
                trust="cryptographic", confidence=0.0,
                anchor=anchor_for(field), region=box, started=started))
            continue

        norm = COMPARE[field]
        a, b = norm(proven), norm(printed)
        if a is None or b is None:
            out.append(emit(
                ctx.profile, sid, "inconclusive",
                f"The {shown} could not be normalised for comparison against "
                f"this document's signature",
                trust="cryptographic", confidence=0.0,
                anchor=anchor_for(field), region=box, started=started))
            continue

        match = a == b
        out.append(emit(
            ctx.profile, sid, "pass" if match else "fail",
            f"The {shown} printed on this document, {b}, matches what its own "
            f"signature covers"
            if match else
            f"This document's own signature covers {shown} {a}, but the card "
            f"prints {b}. The signature verifies, so the payload is genuine - "
            f"it is the printing that disagrees with it",
            trust="cryptographic",
            anchor=anchor_for(field), region=box, started=started))
    return out


def _cross_document(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    priors = signed_priors(ctx)
    fields = ctx.profile["verify"].get("cross_document") or []
    if not priors or not fields:
        return []

    out: list[Signal] = []
    for prior in priors:
        source = label(prior["doc_type"]) if prior.get("doc_type") else "signed document"
        payload = prior["payload"]

        for field in fields:
            if field not in COMPARE:
                continue
            proven = payload.get(field)
            printed = value_of(ctx, field)
            if not proven:
                continue

            sid = f"validation.crossdoc.{field}_mismatch"
            shown = field_label(field)
            box = box_of(ctx, field)

            if not printed:
                out.append(emit(
                    ctx.profile, sid, "inconclusive",
                    f"The printed {shown} could not be read, so it cannot be "
                    f"checked against the signed {source} in this session",
                    trust="cryptographic", confidence=0.0,
                    anchor=anchor_for(field), region=box, started=started,
                ))
                continue

            if not comparable(ctx, field):
                # Read by the VLM fallback, which has no checksum behind it. It
                # may fill a gap; it may not contradict a signed payload.
                out.append(emit(
                    ctx.profile, sid, "inconclusive",
                    f"The {shown} on this document was only recovered by the "
                    f"fallback reader, which cannot be relied on to the "
                    f"character, so it is not used to dispute the signed "
                    f"{source}",
                    trust="cryptographic", confidence=0.0,
                    anchor=anchor_for(field), region=box, started=started,
                ))
                continue

            norm = COMPARE[field]
            a, b = norm(proven), norm(printed)
            if a is None or b is None:
                out.append(emit(
                    ctx.profile, sid, "inconclusive",
                    f"The {shown} could not be normalised for comparison against "
                    f"the signed {source}",
                    trust="cryptographic", confidence=0.0,
                    anchor=anchor_for(field), region=box, started=started,
                ))
                continue

            match = a == b
            out.append(emit(
                ctx.profile, sid, "pass" if match else "fail",
                f"The signed {source} payload {shown} {a} matches this "
                f"{label(ctx.profile['doc_type'])}"
                if match else
                f"The signed {source} payload gives {shown} {a}; this "
                f"{label(ctx.profile['doc_type'])} prints {b}",
                trust="cryptographic",
                anchor=anchor_for(field), region=box, started=started,
            ))
    return out


def as_prior(doc_type: str, verification, fields: dict | None = None) -> dict:
    """Build the `prior_docs` entry for a document just screened.

    Only the verified payload travels. Printed values from an unsigned document
    are not ground truth and deliberately do not propagate - otherwise the
    first forged document in a session poisons every one after it.
    """
    verified = bool(verification and verification.ok)
    return {
        "doc_type": doc_type,
        "verified": verified,
        "payload": dict(verification.payload) if verified else {},
        "issuer_id": verification.issuer_id if verification else None,
        "fields": fields or {},
    }
