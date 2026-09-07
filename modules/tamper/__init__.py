"""Tampering, two tracks. context/MODULES.md, Module 3.

The profile speaks in check names, the contract speaks in signal ids, and this
module is the only place the two meet. It runs what can actually be run and is
explicit about what cannot - three families are blocked by something structural
rather than by effort, and each says which:

  guilloche        measured on documents that carry a real one, three ways,
                   and none of them separates a break from ordinary variation -
                   see data/TAMPERING.md
  stamps           the 22-class ontology has no stamp class and no stamp
                   detector is deployed
  halftone         measured, and it does not work at this capture resolution -
                   detection rate equals the false-positive rate at every
                   threshold, so any verdict from it is a coin flip wearing a
                   number. `physical.halftone()` and its evaluation are kept so
                   the claim stays checkable on a higher-resolution scan; see
                   data/TAMPERING.md

Those report `inconclusive` with that sentence, not a bare "not evaluated". The
difference matters at the counter: an officer who reads "not evaluated" once and
later discovers it meant "cannot ever be evaluated" stops trusting the whole
evidence list. Being blocked costs coverage, which is correct - a document
cannot reach GREEN on evidence that was never gathered (D9).

The physical/digital split is D12. At a live counter the scanner writes the
file, so EXIF is clean and the image is single-JPEG by construction: those
checks are `not_applicable` on scanner input and only become a gap on an upload.
Copy-move and noise residual are the exception and run on everything - they are
pixel-domain, and a photo pasted onto a card is still two regions with one
origin after the scanner has written a perfectly innocent file.
"""
from core.profiles import load_config
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.tamper import digital, physical

#: Profile check name to signal id. Several checks share an id deliberately -
#: `font_consistency` and `ocrb_conformance` are one measurement (glyph metrics
#: within a printed line) applied to different crops, and there is no registered
#: id for the former.
PHYSICAL = {
    "halftone": "tamper.physical.halftone",
    "ocrb_conformance": "tamper.physical.ocrb_conformance",
    "font_consistency": "tamper.physical.ocrb_conformance",
    "layout_geometry": "tamper.physical.layout_geometry",
    "guilloche": "tamper.physical.guilloche_break",
    "ghost_portrait": "tamper.physical.ghost_missing",
    "stamp_duplicate": "tamper.stamp.duplicate",
    "stamp_date_logic": "tamper.stamp.date_logic",
    "stamp_count": "tamper.stamp.count_mismatch",
    # Handled by the always-on pixel track below, not by the profile dispatch.
    "copy_move": None,
}

#: Checks that are blocked by something we cannot fix by writing more code, and
#: the sentence an officer gets instead of a verdict.
BLOCKED = {
    "tamper.physical.halftone":
        "The print screen was not checked - at the resolution these captures "
        "arrive at, the measurement does not separate altered documents from "
        "genuine ones",
    "tamper.physical.guilloche_break":
        "The security background pattern was not checked - measured three ways "
        "on documents that carry a real one, and none of them separates a break "
        "from ordinary variation in the pattern",
    "tamper.stamp.duplicate":
        "Stamps were not compared - no stamp detector is deployed and the field "
        "ontology has no stamp class",
    "tamper.stamp.date_logic":
        "Stamp dates were not checked - no stamp detector is deployed, so no "
        "stamp dates were read",
    "tamper.stamp.count_mismatch":
        "The stamp count was not checked - no stamp detector is deployed",
}

#: Compression and metadata forensics. Meaningless on scanner input (D12).
UPLOAD_ONLY = {
    "tamper.digital.exif_software": "file metadata analysis",
    "tamper.digital.double_jpeg": "compression history analysis",
    "tamper.digital.ela": "error level analysis",
}


def run(ctx: ScreeningContext, *, tier: int = 1, uploaded: bool = False,
        raw: bytes | None = None) -> list[Signal]:
    """Tampering signals for this document.

    `raw` is the original uploaded bytes, passed down rather than carried on the
    context: `ScreeningContext` is a frozen contract, and `ctx.image` has already
    been decoded and downscaled, which destroys the file-level structure EXIF and
    the quantisation tables live in. Nothing here re-decodes the input.
    """
    cfg = load_config("thresholds")["tamper"]
    declared = list(ctx.profile["tamper"].get("checks", []))
    out: list[Signal] = []
    seen: set[str] = set()

    # --- physical track, tier 1 -------------------------------------------
    for check in declared:
        sid = PHYSICAL.get(check)
        if sid is None or sid in seen:
            continue
        seen.add(sid)

        if sid in BLOCKED:
            out.append(_blocked(sid))
        elif sid == "tamper.physical.ghost_missing":
            out.append(physical.run_ghost(ctx, cfg))
        elif sid == "tamper.physical.layout_geometry":
            out.append(physical.run_layout(ctx, cfg))
        elif sid == "tamper.physical.ocrb_conformance":
            out.append(physical.run_print_consistency(
                ctx, cfg, mrz=("ocrb_conformance" in declared)))

    # --- digital track, tier 1, uploads only ------------------------------
    if uploaded:
        out += digital.run_uploads(ctx.image, raw, cfg)
    else:
        out += [_scanner_na(sid, what) for sid, what in UPLOAD_ONLY.items()]

    # --- pixel forensics, tier 2, every input -----------------------------
    if tier >= 2:
        out += digital.run_always(ctx.image, cfg)

    return out


def _blocked(sid: str) -> Signal:
    return Signal(
        id=sid, module="tamper", tier=1, verdict="inconclusive", confidence=0.0,
        trust_class="probabilistic", hard_fail=False, anchor="document",
        evidence=BLOCKED[sid], latency_ms=0,
    )


def _scanner_na(sid: str, what: str) -> Signal:
    """`not_applicable`, not `pass`. The check did not run and did not clear it.

    It stays out of the coverage denominator because on scanner input it is
    genuinely inapplicable, not merely unmeasured - the scanner wrote the file,
    so there is no editing history in it to find.
    """
    return Signal(
        id=sid, module="tamper", tier=1, verdict="not_applicable", confidence=1.0,
        trust_class="arithmetic", hard_fail=False, anchor="document",
        evidence=f"Scanner input, so {what} does not apply - this file was "
                 f"written by the scanner, not by whoever made the document",
        latency_ms=0,
    )
