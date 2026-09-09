"""The checksum ratifier. Mandatory gate on 100% of VLM output.

TECHNICAL-SPEC.md section 4: *"No VLM output reaches L4 unratified."* A vision
model reading a smudged date returns a plausible date, because returning
plausible text is what it was trained to do. Every other reader in this system
either verifies arithmetically or admits it could not read; the VLM is the one
that will confidently make something up, so it gets a gate the others do not.

Three outcomes, and the middle one is the one that matters:

    checksum verifies    store it, `arithmetic` - as good as any other read
    checksum fails       **do not store it at all**
    no checksum exists   store it, `unverified` - costs coverage

**A rejected field must not reach `ctx.fields`.** It is tempting to store it
and let the score sort it out, and it is wrong: Layer C compares the printed
value against the MRZ and Layer D compares it against a signed sibling
document, so a value already known to be wrong does not sit there inertly - it
manufactures mismatches, in a system whose entire selling point is that a
mismatch means something.

`force MANUAL_REVIEW` from the spec needs no new mechanism. Unratified fields
emit `inconclusive`, which costs coverage, which trips the 0.70 floor, which
returns AMBER "re-capture required" (D9). That is manual review, through
machinery that is already written and already tested.

Two signals, not two per field. `extraction.vlm.ratified` and
`extraction.vlm.unratified` are registered as concrete ids and carry one
reliability weight each, and a screening may not emit an id twice
(CONTRACTS.md section 1). One anchor is checkable per document type, and "some
of this output could not be checked" is one condition however many fields it
covers - charging coverage per field would count one problem several times, the
mistake D8 exists to prevent.
"""
import time

from core.profiles import field_label
from fusion.context import NormalizedField, ScreeningContext
from fusion.signal import Signal
from modules.extraction import mrz as mrz_parser
from modules.validation.checksums import (ANCHORS, check_aadhaar, check_dl,
                                          check_epic, check_pan)

#: Which field carries the arithmetic anchor `checksums.ANCHORS` names for each
#: document type. The anchor table says *what* can be checked; this says *where*
#: to find it.
ANCHOR_FIELD = {
    "verhoeff_aadhaar": "id_number",
    "pan_format": "id_number",
    "epic_format": "id_number",
    "dl_state_rto": "id_number",
    "mrz_checkdigits": "mrz",
}


def anchor_for(doc_type: str) -> tuple[str, str] | None:
    """(anchor name, field it lives on), or None when this type has neither."""
    anchor = ANCHORS.get(doc_type)
    if anchor is None:
        return None
    return anchor, ANCHOR_FIELD[anchor]


def check(anchor: str, value: str, *, surname: str | None = None) -> tuple[bool, str]:
    """Run one arithmetic anchor. Reuses the functions Layer A validates with.

    Deliberately the same call, not a copy of it. Two implementations of one
    checksum that drift apart give a system where the ratifier clears what the
    validator would reject, and every test still passes.
    """
    if anchor == "verhoeff_aadhaar":
        return check_aadhaar(value)
    if anchor == "pan_format":
        return check_pan(value, surname)
    if anchor == "epic_format":
        return check_epic(value)
    if anchor == "dl_state_rto":
        return check_dl(value)
    if anchor == "mrz_checkdigits":
        return _check_mrz(value)
    return False, f"no arithmetic anchor named {anchor}"


def _check_mrz(strip: str) -> tuple[bool, str]:
    """Every ICAO check digit in the strip, or why it could not be read."""
    try:
        parsed = mrz_parser.parse(strip)
    except mrz_parser.MRZError as exc:
        return False, f"the machine-readable zone does not parse: {exc}"

    failed = [name for name, (value, digit) in parsed.check_digits.items()
              if not mrz_parser.verify(value, digit)]
    if failed:
        return False, (f"machine-readable zone check digits do not match: "
                       f"{', '.join(sorted(failed))}")
    return True, (f"all {len(parsed.check_digits)} machine-readable zone check "
                  f"digits verify")


def ratify(ctx: ScreeningContext, reads: dict[str, str], *,
           confidence: float = 0.5, started: float | None = None) -> list[Signal]:
    """Gate a set of VLM reads into `ctx.fields`. Returns signals.

    `reads` is {ontology class: raw string} straight from the model. Values are
    normalised through the same functions OCR uses, so a date that is not a date
    is discarded here exactly as it would be there.

    `started` is the caller's clock, and passing it matters more than it looks.
    The ratifier is the only producer of `extraction.vlm.*`, so its signals are
    the only place the fallback's cost can be reported. Timing from here instead
    measures the ratification - a few hundred microseconds - and throws away the
    seven seconds of Florence-2 that produced the reads. That is how a document
    which took six seconds to screen reported four milliseconds of extraction.

    CLAUDE.md: time everything, the latency budget is a requirement rather than
    a hope. A budget policed by a number that omits the expensive part is not
    policing anything.
    """
    from modules.extraction import normalise_field

    started = time.perf_counter() if started is None else started
    doc_type = ctx.profile["doc_type"]
    pair = anchor_for(doc_type)
    signals: list[Signal] = []

    surname = _surname_from(reads, ctx)
    unratified: list[str] = []
    rejected: tuple[str, str] | None = None
    ratified_field: str | None = None

    for name, raw in sorted(reads.items()):
        if not raw or name in ctx.fields:
            # A value already present came from OCR, the MRZ or a verified
            # signed payload. All three outrank a fallback read.
            continue

        checkable = pair is not None and name == pair[1]
        if checkable:
            ok, detail = check(pair[0], raw, surname=surname)
            if not ok:
                rejected = (name, detail)
                continue                      # NOT stored. See the docstring.

        field = _store(ctx, name, raw, confidence, ratified=checkable)
        if field is None:
            continue
        if checkable:
            ratified_field = name
        else:
            unratified.append(name)

    signals.append(_ratified_signal(pair, ratified_field, rejected, doc_type,
                                    started))
    if unratified:
        signals.append(_unratified_signal(unratified, started))
    return signals


def _store(ctx: ScreeningContext, name: str, raw: str, confidence: float,
           *, ratified: bool) -> NormalizedField | None:
    """Normalise and store. Returns None when the value will not normalise."""
    from modules.extraction import normalise_field

    if name == "mrz":
        # The MRZ is not a normalised value, it is a strip Layer A parses. Same
        # shape `ocr._read_mrz_field` stores.
        ctx.fields["mrz"] = NormalizedField(raw=raw, value="", source="vlm",
                                            confidence=confidence)
        return ctx.fields["mrz"]

    field = normalise_field(name, raw, "vlm", confidence)
    if field is None and " " in raw:
        field = normalise_field(name, raw.replace(" ", ""), "vlm", confidence)
    if field is None:
        return None
    ctx.fields[name] = field
    return field


def _surname_from(reads: dict, ctx: ScreeningContext) -> str | None:
    """PAN's fifth character must match the surname, so the check needs one."""
    value = reads.get("name") or (
        ctx.fields["name"].value if "name" in ctx.fields else None)
    if not value:
        return None
    parts = str(value).strip().split()
    return parts[-1] if parts else None


def _signal(sid: str, verdict: str, evidence: str, *, confidence: float,
            trust: str, anchor: str = "document", started=None) -> Signal:
    return Signal(
        id=sid, module="extraction", tier=1, verdict=verdict,
        confidence=confidence, trust_class=trust, hard_fail=False,
        anchor=anchor, evidence=evidence,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0,
    )


def _ratified_signal(pair, ratified_field, rejected, doc_type, started) -> Signal:
    sid = "extraction.vlm.ratified"

    if rejected is not None:
        name, detail = rejected
        return _signal(
            sid, "fail",
            f"The fallback reader returned a {field_label(name)} that fails its "
            f"own arithmetic check - {detail}. It was discarded rather than "
            f"used, so nothing downstream is comparing against a misread value",
            confidence=0.9, trust="arithmetic", anchor=f"field:{name}",
            started=started)

    if ratified_field is not None:
        return _signal(
            sid, "pass",
            f"The fallback reader's {field_label(ratified_field)} passes its "
            f"arithmetic check, so that read is confirmed by the document "
            f"itself rather than by the model",
            confidence=1.0, trust="arithmetic",
            anchor=f"field:{ratified_field}", started=started)

    if pair is None:
        return _signal(
            sid, "not_applicable",
            f"{doc_type.replace('_', ' ').capitalize()} carries no arithmetic "
            f"anchor, so a fallback read of it cannot be confirmed by the "
            f"document", confidence=1.0, trust="arithmetic", started=started)

    return _signal(
        sid, "inconclusive",
        f"The fallback reader did not return a usable {field_label(pair[1])}, "
        f"so none of its output could be confirmed arithmetically",
        confidence=0.0, trust="unverified", started=started)


def _unratified_signal(unratified: list[str], started) -> Signal:
    shown = ", ".join(field_label(n) for n in sorted(unratified))
    return _signal(
        "extraction.vlm.unratified", "inconclusive",
        f"Read by the fallback reader with nothing to check them against: "
        f"{shown}. These carry no arithmetic confirmation and must not be "
        f"treated as read",
        confidence=0.0, trust="unverified", started=started)
