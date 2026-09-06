"""Layer C - cross-field logic within one document.

Date ordering, validity period, age consistency, and VIZ/MRZ agreement.

The VIZ/MRZ cross-check is the single highest-value tamper signal in the
system, and it is on the never-cut list. A forger edits the printed date of
birth and leaves the machine-readable zone alone, because the MRZ looks like
noise. The two then disagree - and that is not a model output, it is two fields
being different, which the officer can read for themselves.
"""
import time
from datetime import date

from core.profiles import describe, describe_start, field_label
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import mrz as MRZ
from modules.extraction import normalize as N
from modules.validation import anchor_for, box_of, emit, raw_of, value_of

#: Standard Indian validity periods, in years. Used as a soft check: a passport
#: whose expiry is not issue+10 or issue+5 is unusual, not impossible.
VALIDITY_YEARS = {"passport": (10, 5), "dl": (20, 10, 5), "visa": (10, 5, 1)}

#: Printed fields the MRZ also carries, and the normaliser each needs.
VIZ_MRZ_FIELDS = {
    "dob": ("birth_date", lambda v: N.iso_date(v)),
    "name": ("name", lambda v: N.name(v)),
    "expiry_date": ("expiry_date", lambda v: N.iso_date(v)),
    "id_number": ("document_number", lambda v: N.id_number(v)),
    "nationality": ("nationality", lambda v: str(v or "").strip().upper()),
    "gender": ("sex", lambda v: N.gender(v)),
}


def run(ctx: ScreeningContext, today: date | None = None) -> list[Signal]:
    today = today or date.today()
    return (
        _date_order(ctx)
        + _expiry(ctx, today)
        + _validity_period(ctx)
        + _age_consistency(ctx, today)
        + viz_mrz(ctx)
    )


def _d(value):
    return date.fromisoformat(value) if value else None


def _date_order(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    dob = _d(N.iso_date(value_of(ctx, "dob") or ""))
    issue = _d(N.iso_date(value_of(ctx, "issue_date") or ""))
    expiry = _d(N.iso_date(value_of(ctx, "expiry_date") or ""))

    known = [d for d in (dob, issue, expiry) if d]
    if len(known) < 2:
        return [emit(ctx.profile, "validation.crossfield.date_order", "inconclusive",
                     "Not enough dates could be read to check their ordering",
                     confidence=0.0, started=started)]

    problems = []
    if dob and issue and dob >= issue:
        problems.append(f"date of birth {dob} is not before the issue date {issue}")
    if issue and expiry and issue >= expiry:
        problems.append(f"issue date {issue} is not before the expiry date {expiry}")
    if dob and expiry and dob >= expiry:
        problems.append(f"date of birth {dob} is not before the expiry date {expiry}")

    if problems:
        return [emit(ctx.profile, "validation.crossfield.date_order", "fail",
                     "The printed dates are inconsistent: " + "; ".join(problems),
                     started=started)]
    detail = ", ".join(
        f"{label} {value}" for label, value in
        (("born", dob), ("issued", issue), ("expires", expiry)) if value
    )
    return [emit(ctx.profile, "validation.crossfield.date_order", "pass",
                 f"Printed dates are in order: {detail}", started=started)]


def _expiry(ctx: ScreeningContext, today: date) -> list[Signal]:
    started = time.perf_counter()
    expiry = _d(N.iso_date(value_of(ctx, "expiry_date") or ""))
    region = box_of(ctx, "expiry_date")

    if "expiry_date" not in ctx.profile["extract"]["detector_classes"]:
        return [emit(ctx.profile, "validation.expiry.expired", "not_applicable",
                     f"{describe_start(ctx.profile['doc_type'])} does not carry an expiry date",
                     started=started)]
    if not expiry:
        return [emit(ctx.profile, "validation.expiry.expired", "inconclusive",
                     "The expiry date could not be read", confidence=0.0,
                     anchor=anchor_for("expiry_date"), region=region, started=started)]

    if expiry < today:
        days = (today - expiry).days
        return [emit(ctx.profile, "validation.expiry.expired", "fail",
                     f"Expired on {expiry}, {days // 365} years {days % 365 // 30} "
                     f"months ago",
                     anchor=anchor_for("expiry_date"), region=region, started=started)]

    days = (expiry - today).days
    return [emit(ctx.profile, "validation.expiry.expired", "pass",
                 f"Expires {expiry}, valid for another {days // 365} years "
                 f"{days % 365 // 30} months",
                 anchor=anchor_for("expiry_date"), region=region, started=started)]


def _validity_period(ctx: ScreeningContext) -> list[Signal]:
    started = time.perf_counter()
    doc_type = ctx.profile["doc_type"]
    allowed = VALIDITY_YEARS.get(doc_type)
    issue = _d(N.iso_date(value_of(ctx, "issue_date") or ""))
    expiry = _d(N.iso_date(value_of(ctx, "expiry_date") or ""))
    if not allowed or not (issue and expiry):
        return []

    years = (expiry - issue).days / 365.25
    ok = any(abs(years - a) < 0.6 for a in allowed)
    return [emit(
        ctx.profile, "validation.crossfield.validity_period",
        "pass" if ok else "fail",
        f"Valid for {years:.0f} years, a standard period for {describe(doc_type)}"
        if ok else
        f"Valid for {years:.1f} years, which is not a standard period for "
        f"{describe(doc_type)} ({' or '.join(str(a) for a in allowed)} years)",
        started=started,
    )]


def _age_consistency(ctx: ScreeningContext, today: date) -> list[Signal]:
    started = time.perf_counter()
    dob = _d(N.iso_date(value_of(ctx, "dob") or ""))
    if not dob:
        return []
    age = (today - dob).days / 365.25
    if 0 <= age <= 120:
        return []
    return [emit(
        ctx.profile, "validation.crossfield.date_order", "fail",
        f"Date of birth {dob} gives an age of {age:.0f}, which is not plausible",
        anchor=anchor_for("dob"), region=box_of(ctx, "dob"), started=started,
    )]


# ----------------------------------------------------------- VIZ  vs  MRZ

def viz_mrz(ctx: ScreeningContext) -> list[Signal]:
    """Compare every field the MRZ and the printed zone both carry."""
    started = time.perf_counter()
    profile = ctx.profile
    region = box_of(ctx, "mrz")

    if "mrz" not in profile["extract"]["detector_classes"]:
        return [emit(profile, "validation.vizmrz.dob_mismatch", "not_applicable",
                     f"{describe_start(profile['doc_type'])} has no machine-readable zone to "
                     f"compare the printed fields against", started=started)]

    strip = raw_of(ctx, "mrz")
    parsed = None
    if strip:
        try:
            parsed = MRZ.parse(strip)
        except MRZ.MRZError:
            parsed = None

    if parsed is None:
        return [emit(profile, "validation.vizmrz.dob_mismatch", "inconclusive",
                     "Cannot compare the printed fields against the "
                     "machine-readable zone while the zone is unreadable",
                     confidence=0.0, region=region, started=started)]

    out = []
    for field, (attr, norm) in VIZ_MRZ_FIELDS.items():
        printed = value_of(ctx, field)
        machine = getattr(parsed, attr, None)
        sid = f"validation.vizmrz.{field}_mismatch"
        box = box_of(ctx, field) or region
        shown = field_label(field)

        if machine in (None, "", "<"):
            continue
        if printed is None:
            out.append(emit(profile, sid, "inconclusive",
                            f"The printed {shown} could not be read, so it cannot "
                            f"be compared with the machine-readable zone",
                            confidence=0.0, anchor=anchor_for(field), region=box,
                            started=started))
            continue

        a, b = norm(printed), norm(machine)
        if a is None or b is None:
            out.append(emit(profile, sid, "inconclusive",
                            f"The {shown} could not be normalised for comparison",
                            confidence=0.0, anchor=anchor_for(field), region=box,
                            started=started))
            continue

        match = _agrees(field, a, b)
        out.append(emit(
            profile, sid, "pass" if match else "fail",
            f"MRZ {shown} {b} matches printed {a}" if match else
            f"MRZ {shown} {b} does not match printed {a}",
            anchor=anchor_for(field), region=box, started=started,
        ))
    return out


def _agrees(field: str, printed: str, machine: str) -> bool:
    """Names get a looser rule than the rest.

    The MRZ name field is 39 characters. A long Indian name is routinely
    truncated, and middle names are dropped before surnames are. Treating a
    truncation as a mismatch would fire on genuine documents all day and train
    the officer to ignore the signal that matters most.
    """
    if printed == machine:
        return True
    if field != "name":
        return False
    a, b = set(printed.split()), set(machine.split())
    if not a or not b:
        return False
    return a <= b or b <= a
