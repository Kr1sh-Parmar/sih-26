"""Layer B - format conformance. Arithmetic, no key, no model.

Field lengths, charsets, country codes, gender codes, date formats. Cheap and
dull, and it catches the OCR misreads that would otherwise become a confident
wrong answer three layers later.

This layer judges shape, never plausibility. `^[0-9]{12}$` passing for
000000000000 is Layer A's problem, and Layer A has the checksum.
"""
import time

from core.profiles import describe, describe_start, field_label
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import normalize as N
from modules.validation import anchor_for, box_of, emit, value_of

#: Fields that must parse as a date if they are present at all.
DATE_FIELDS = ("dob", "issue_date", "expiry_date")

#: Printed length ceilings. Generous - this catches an OCR run-on that swallowed
#: the next line, not a long name.
MAX_LENGTH = {"name": 80, "father_name": 80, "address": 240, "id_number": 24}


def run(ctx: ScreeningContext) -> list[Signal]:
    signals: list[Signal] = []
    signals += _dates(ctx)
    signals += _nationality(ctx)
    signals += _gender(ctx)
    signals += _lengths(ctx)
    signals += _forbidden_classes(ctx)
    return signals


def _dates(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    out = []
    for field in DATE_FIELDS:
        value = value_of(ctx, field)
        if value is None:
            continue
        sid = f"validation.format.{ctx.profile['doc_type']}.{field}"
        ok = N.iso_date(value) is not None
        out.append(emit(
            ctx.profile, sid, "pass" if ok else "fail",
            f"The {field_label(field)} {value} is a valid date"
            if ok else
            f"The {field_label(field)} could not be read as a date: {value!r}",
            anchor=anchor_for(field), region=box_of(ctx, field), started=started,
        ))
    return out


def _nationality(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    value = value_of(ctx, "nationality")
    if value is None:
        return []
    sid = f"validation.format.{ctx.profile['doc_type']}.nationality"
    ok = N.is_country_code(value)
    name = N.country_codes().get(value.upper(), "")
    return [emit(
        ctx.profile, sid, "pass" if ok else "fail",
        f"Nationality {value.upper()} is a recognised country code"
        + (f" ({name})" if name else "")
        if ok else
        f"Nationality {value.upper()} is not a recognised ISO 3166 or ICAO code",
        anchor=anchor_for("nationality"), region=box_of(ctx, "nationality"),
        started=started,
    )]


def _gender(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    value = value_of(ctx, "gender")
    if value is None:
        return []
    sid = f"validation.format.{ctx.profile['doc_type']}.gender"
    code = N.gender(value)
    return [emit(
        ctx.profile, sid, "pass" if code else "fail",
        f"Gender code {code} is valid" if code else
        f"Gender {value!r} is not one of the codes M, F or unspecified",
        anchor=anchor_for("gender"), region=box_of(ctx, "gender"), started=started,
    )]


def _lengths(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    out = []
    for field, ceiling in MAX_LENGTH.items():
        value = value_of(ctx, field)
        if value is None or len(value) <= ceiling:
            continue
        out.append(emit(
            ctx.profile, f"validation.format.{ctx.profile['doc_type']}.{field}",
            "fail",
            f"The {field_label(field)} is {len(value)} characters, "
            f"longer than the {ceiling} expected on this document",
            anchor=anchor_for(field), region=box_of(ctx, field), started=started,
        ))
    return out


def _forbidden_classes(ctx: ScreeningContext) -> list[Signal]:
    """A class that should never appear on this document appearing anyway.

    An MRZ detected on a Voter ID is not a format error, it is a sign that
    somebody built the document out of parts.
    """
    started = time.perf_counter()
    forbidden = set(ctx.profile["extract"].get("forbidden_classes", []))
    present = sorted(forbidden & set(ctx.field_boxes))
    if not present:
        return []
    return [emit(
        ctx.profile, f"validation.format.{ctx.profile['doc_type']}.layout", "fail",
        f"{describe_start(ctx.profile['doc_type'])} should not carry "
        f"{', '.join(p.replace('_', ' ') for p in present)}, but it was detected "
        f"on this document",
        trust="probabilistic", confidence=0.8,
        region=tuple(ctx.field_boxes[present[0]]), started=started,
    )]
