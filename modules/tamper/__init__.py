"""Tampering, two tracks. STUB - no model is wired yet.

Every check the profile declares returns `inconclusive`, which is the honest
answer: we did not evaluate it. That deliberately costs coverage, so a document
screened today cannot reach GREEN on tampering evidence that does not exist.
When the real checks land they replace these one at a time and coverage climbs
on its own.

The one thing that is real here is the physical/digital split. At a live counter
the scanner writes the file, so EXIF is clean and the image is single-JPEG by
construction - a professionally printed physical forgery passes every digital
forensic completely, because the image genuinely *is* a fresh scan. It is the
object that is fake (D12). So the digital track is `not_applicable` on scanner
input and only becomes a gap on an upload.
"""
import time

from fusion.context import ScreeningContext
from fusion.signal import Signal

#: Profile check name to signal id. The profile speaks in checks, the contract
#: speaks in signal ids, and this is the only place the two meet.
PHYSICAL = {
    "ocrb_conformance": "tamper.physical.ocrb_conformance",
    "guilloche": "tamper.physical.guilloche_break",
    "ghost_portrait": "tamper.physical.ghost_missing",
    "layout_geometry": "tamper.physical.layout_geometry",
    "halftone": "tamper.physical.halftone",
    "font_consistency": "tamper.physical.ocrb_conformance",
    "stamp_duplicate": "tamper.stamp.duplicate",
    "stamp_date_logic": "tamper.stamp.date_logic",
    "stamp_count": "tamper.stamp.count_mismatch",
    "copy_move": "tamper.digital.copy_move",
}

#: Digital track. Uploads only.
DIGITAL = (
    "tamper.digital.exif_software",
    "tamper.digital.double_jpeg",
    "tamper.digital.ela",
    "tamper.digital.noise_residual",
)

TIER2 = {"tamper.digital.copy_move", "tamper.digital.noise_residual"}


def _pending(sid: str, evidence: str, tier: int = 1, ms: int = 0) -> Signal:
    return Signal(
        id=sid, module="tamper", tier=tier, verdict="inconclusive",
        confidence=0.0, trust_class="probabilistic", hard_fail=False,
        anchor="document", evidence=evidence, latency_ms=ms,
    )


def run(ctx: ScreeningContext, *, tier: int = 1, uploaded: bool = False) -> list[Signal]:
    started = time.perf_counter()
    out: list[Signal] = []
    seen: set[str] = set()

    for check in ctx.profile["tamper"].get("checks", []):
        sid = PHYSICAL.get(check)
        if not sid or sid in seen:
            continue
        seen.add(sid)
        this_tier = 2 if sid in TIER2 else 1
        if this_tier > tier:
            continue
        out.append(_pending(
            sid,
            f"{check.replace('_', ' ').capitalize()} has not been evaluated - "
            f"the detector for this check is not yet deployed",
            tier=this_tier,
        ))

    for sid in DIGITAL:
        if sid in seen:
            continue
        this_tier = 2 if sid in TIER2 else 1
        if this_tier > tier:
            continue
        if not uploaded:
            out.append(Signal(
                id=sid, module="tamper", tier=this_tier, verdict="not_applicable",
                confidence=1.0, trust_class="arithmetic", hard_fail=False,
                anchor="document",
                evidence="Scanner input, so file metadata and compression checks "
                         "do not apply",
            ))
        else:
            out.append(_pending(sid, f"{sid.rsplit('.', 1)[-1].replace('_', ' ')} "
                                     f"has not been evaluated on this upload",
                                tier=this_tier))

    ms = int((time.perf_counter() - started) * 1000)
    return [Signal(**{**s.__dict__, "latency_ms": ms}) for s in out]
