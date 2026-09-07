"""Face verification. context/MODULES.md, Module 4.

    document photo -> detect -> quality -> align -> 512-d
    live frame     -> detect -> quality -> passive liveness -> 512-d
                                        -> cosine -> band + margin
                                        -> [escalated] 1:N gallery

Three decisions are load-bearing here, and two of them are about what the
officer is *told* rather than what is computed.

**There is no 0-100 score.** `((cos + 1) / 2) * 100` maps a total stranger to 50
and a confident impostor to 58, and an officer reads 58 as "more than half,
probably him". The scale is wrong in the direction that admits fraudsters (D10).
What is reported is the cosine, the threshold, and the margin between them.

**The threshold is not calibrated, and every signal says so.** Published
buffalo thresholds are live-to-live; a document photo is printed, halftone
screened, overprinted, sub-300 dpi once scanned and up to ten years old (D11).
The configured value is a placeholder with `calibrated: false`, and the officer
is told that in the evidence string rather than being handed a number that looks
measured. `data/tools/calibrate_face.py` flips it when the pairs exist.

**A bad document photo does not mean "retake your selfie".** The printed photo
cannot be retaken. What is needed is a higher-resolution capture of the
*document*, and saying the wrong one sends an officer round a loop that cannot
terminate.

Live frames are optional. Without one this reports what it can about the
document photo and marks the comparison `inconclusive` - not `pass`, because
nothing was compared (D9).
"""
import time

import numpy as np

from core.profiles import load_config
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.face import detect as detector
from modules.face import embed as embedder
from modules.face import gallery, liveness
from core.registry import (FACE_DETECTOR, FACE_EMBEDDING, ModelMissing,
                           available)


def threshold(name: str = "doc_live") -> tuple[float, bool]:
    """The operating point and whether it has actually been calibrated."""
    cfg = load_config("thresholds")["face"][name]
    return float(cfg["threshold"]), bool(cfg.get("calibrated", False))


def review_band(name: str = "doc_live") -> tuple[float, float]:
    band = load_config("thresholds")["face"][name]["review_band"]
    return float(band[0]), float(band[1])


def margin_text(cosine: float, name: str = "doc_live") -> str:
    """Three bands plus margin, never a percentage."""
    t, calibrated = threshold(name)
    direction = "above" if cosine >= t else "below"
    text = (f"Document and live face match at cosine {cosine:.2f}, against a "
            f"{t:.2f} threshold, {abs(cosine - t):.2f} {direction} it")
    if not calibrated:
        text += (". That threshold is not yet calibrated on document-to-live "
                 "pairs, so treat the margin as indicative")
    return text


def certainty(value: float, band: tuple[float, float]) -> float:
    """How sure a verdict is, from how far the score sits outside its band.

    `confidence` on a Signal means certainty - fusion multiplies it by the
    signal's reliability in the noisy-OR. Putting the raw score there instead
    makes a clear impostor look like a weak finding, because a low cosine is a
    *strong* statement of mismatch. So the score is converted: anything inside
    the configured band comes out below 1.0 and the risk gate escalates it,
    anything outside is a verdict we stand behind.
    """
    low, high = band
    midpoint = (low + high) / 2
    half = max((high - low) / 2, 1e-6)
    return float(min(1.0, abs(value - midpoint) / half))


def quality_cfg() -> dict:
    return load_config("thresholds")["face"]["quality"]


def _signal(sid: str, verdict: str, evidence: str, *, confidence: float,
            anchor: str = "document", tier: int = 1, region=None,
            started=None) -> Signal:
    return Signal(
        id=sid, module="face", tier=tier, verdict=verdict, confidence=confidence,
        trust_class="probabilistic", hard_fail=False, anchor=anchor,
        evidence=evidence, region=region,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0,
    )


def _not_deployed(sid: str, what: str, *, anchor="document", tier=1) -> Signal:
    return _signal(sid, "inconclusive",
                   f"Face verification has not run - {what}",
                   confidence=0.0, anchor=anchor, tier=tier)


# ------------------------------------------------------------------- one face

def _locate(image, side: str, sid: str, anchor: str, known_region=None):
    """Detect, and report how. Returns (face, signal)."""
    started = time.perf_counter()
    try:
        face, how = detector.find(image, known_region=known_region)
    except ModelMissing:
        return None, _not_deployed(sid, "the face detector is not deployed",
                                   anchor=anchor)

    if face is None:
        return None, _signal(
            sid, "fail",
            (f"No face could be found in the {side}. "
             + ("Ask for a higher-resolution capture of the document - the "
                "printed photo cannot be retaken." if side == "document photo"
                else "Ask the traveller to face the camera and re-capture.")),
            confidence=0.85, anchor=anchor, started=started)

    where = {"direct": "", "denoised": " after noise reduction",
             "region": " only inside the printed photo area"}[how]
    return face, _signal(
        sid, "pass", f"A face was located in the {side}{where}",
        confidence=0.9 if how == "direct" else 0.7,
        anchor=anchor, region=tuple(face["box"]), started=started)


def _quality(image, face, side: str, sid: str, anchor: str, live: bool):
    """Blur, size and pose on the face crop. Returns (usable, signal)."""
    started = time.perf_counter()
    cfg = quality_cfg()
    x1, y1, x2, y2 = face["box"]
    width = x2 - x1
    sharp = detector.sharpness_of(image, face["box"])
    blur_min = cfg["live_blur_min"] if live else cfg["doc_blur_min"]
    size_min = cfg["live_min_px"] if live else cfg["doc_min_px"]

    advice = ("Ask the traveller to hold still and re-capture."
              if live else
              "Ask for a higher-resolution capture of the document - the "
              "printed photo itself cannot be retaken.")

    if width < size_min:
        return False, _signal(
            sid, "fail",
            f"The face in the {side} is only {width:.0f} pixels across, below "
            f"the {size_min} needed to compare. {advice}",
            confidence=0.9, anchor=anchor, region=tuple(face["box"]),
            started=started)

    if sharp < blur_min:
        return False, _signal(
            sid, "fail",
            f"The face in the {side} is too soft to compare (sharpness "
            f"{sharp:.0f}, below {blur_min:.0f}). {advice}",
            confidence=min(0.95, 0.5 + (blur_min - sharp) / max(blur_min, 1)),
            anchor=anchor, region=tuple(face["box"]), started=started)

    yaw = _yaw(face["landmarks"])
    if yaw > cfg["max_yaw"]:
        return False, _signal(
            sid, "fail",
            f"The face in the {side} is turned too far to one side to compare. "
            f"{advice}", confidence=0.8, anchor=anchor,
            region=tuple(face["box"]), started=started)

    return True, _signal(
        sid, "pass",
        f"The face in the {side} is sharp enough and square enough to compare "
        f"({width:.0f} pixels across)", confidence=0.85, anchor=anchor,
        region=tuple(face["box"]), started=started)


def _yaw(landmarks) -> float:
    """How far off-centre the nose sits between the eyes, 0 (square) to 1.

    Not degrees. A five-point estimate of head pose is only ever a proxy, and
    dressing it up as an angle would invite someone to trust it as one.
    """
    points = np.asarray(landmarks, dtype=np.float32).reshape(5, 2)
    left_eye, right_eye, nose = points[0], points[1], points[2]
    span = float(np.linalg.norm(right_eye - left_eye))
    if span <= 1e-6:
        return 1.0
    midpoint = (left_eye + right_eye) / 2
    return float(abs(nose[0] - midpoint[0]) / span)


# ----------------------------------------------------------------------- tiers

def run(ctx: ScreeningContext, *, tier: int = 1, store=None,
        doc_hash: str | None = None) -> list[Signal]:
    """Face signals. Reads `ctx.faces['live']` when the console supplied one."""
    if tier >= 2:
        return _tier2(ctx, store=store, doc_hash=doc_hash)

    if not (available(FACE_DETECTOR) and available(FACE_EMBEDDING)):
        source = ctx.profile["face"]["source_class"]
        region = ctx.field_boxes.get(source)
        out = [
            _not_deployed("face.doc.detected", "the face detector is not deployed",
                          anchor=f"field:{source}"),
            _not_deployed("face.doc.quality", "the face detector is not deployed",
                          anchor=f"field:{source}"),
            _not_deployed("face.live.detected", "the face detector is not deployed"),
            _not_deployed("face.match.cosine",
                          "the face embedding model is not deployed",
                          anchor=f"field:{source}"),
            _not_deployed("face.liveness.passive",
                          "the passive liveness model is not deployed"),
        ]
        if region:
            out = [Signal(**{**s.__dict__, "region": tuple(region)})
                   if s.anchor.startswith("field:") else s for s in out]
        return out

    return _tier1(ctx)


def _tier1(ctx: ScreeningContext) -> list[Signal]:
    source = ctx.profile["face"]["source_class"]
    anchor = f"field:{source}"
    out: list[Signal] = []

    # --- the document photo ----------------------------------------------
    doc_face, signal = _locate(ctx.image, "document photo", "face.doc.detected",
                               anchor, known_region=ctx.field_boxes.get(source))
    out.append(signal)

    doc_ok = False
    if doc_face is not None:
        doc_ok, quality = _quality(ctx.image, doc_face, "document photo",
                                   "face.doc.quality", anchor, live=False)
        out.append(quality)
        if doc_ok:
            ctx.faces["doc"] = doc_face
            try:
                ctx.embeddings["doc"] = embedder.of(ctx.image,
                                                    doc_face["landmarks"])
            except (ValueError, ModelMissing):
                doc_ok = False
    else:
        out.append(_signal("face.doc.quality", "inconclusive",
                           "No face was found in the document photo, so its "
                           "quality could not be assessed", confidence=0.0,
                           anchor=anchor))

    # --- the live capture --------------------------------------------------
    live_image = ctx.faces.get("live")
    if live_image is None:
        # `inconclusive`, not `not_applicable`. Every one of these six document
        # types carries a photograph, so comparing the holder against it always
        # applies - it just did not happen. Calling it inapplicable would take
        # it out of the coverage denominator and let a document with no face
        # check at all reach GREEN (D9).
        out.append(_signal("face.live.detected", "inconclusive",
                           "No live capture was supplied with this document, so "
                           "the holder was not compared against the photo",
                           confidence=0.0))
        out.append(_signal("face.match.cosine", "inconclusive",
                           "There was no live capture to compare the document "
                           "photo against", confidence=0.0, anchor=anchor))
        out.append(_liveness_signal(None, None))
        return out

    live_face, signal = _locate(live_image, "live capture", "face.live.detected",
                                "document")
    out.append(signal)
    if live_face is None:
        out.append(_signal("face.match.cosine", "inconclusive",
                           "No face was found in the live capture, so there was "
                           "nothing to compare", confidence=0.0, anchor=anchor))
        out.append(_liveness_signal(None, None))
        return out

    live_ok, quality = _quality(live_image, live_face, "live capture",
                                "face.live.quality", "document", live=True)
    out.append(quality)
    out.append(_liveness_signal(live_image, live_face))

    if not (doc_ok and live_ok):
        out.append(_signal(
            "face.match.cosine", "inconclusive",
            "The two faces were not compared - one of the captures was not good "
            "enough to embed", confidence=0.0, anchor=anchor))
        return out

    ctx.faces["live_face"] = live_face
    try:
        ctx.embeddings["live"] = embedder.of(live_image, live_face["landmarks"])
    except (ValueError, ModelMissing):
        out.append(_signal("face.match.cosine", "inconclusive",
                           "The live face could not be aligned for comparison",
                           confidence=0.0, anchor=anchor))
        return out

    cosine = embedder.cosine(ctx.embeddings["doc"], ctx.embeddings["live"])
    cut, _calibrated = threshold()
    out.append(_signal(
        "face.match.cosine", "pass" if cosine >= cut else "fail",
        margin_text(cosine),
        # Certainty, not the cosine. A cosine of 0.10 against a 0.32 threshold
        # is a *confident* mismatch, and handing fusion 0.10 would score it as
        # a barely-there finding.
        confidence=certainty(cosine, review_band()),
        anchor=anchor, region=tuple(ctx.faces["doc"]["box"])))
    return out


def _liveness_signal(image, face) -> Signal:
    started = time.perf_counter()
    sid = "face.liveness.passive"
    if not liveness.deployed():
        return _signal(sid, "inconclusive",
                       "Whether the person at the camera is live was not "
                       "checked - the passive liveness model is not deployed. "
                       "Confirm visually.", confidence=0.0, started=started)
    if image is None or face is None:
        return _signal(sid, "not_applicable",
                       "There was no live capture, so there was nothing to "
                       "check for liveness", confidence=1.0, started=started)

    value = liveness.score(image, face["box"])
    cfg = load_config("thresholds")["face"]["liveness"]
    passed = value >= cfg["passive_pass"]
    return _signal(sid, "pass" if passed else "fail",
                   (f"The capture reads as a live person ({value:.2f})" if passed
                    else f"The capture reads as a photograph or a screen rather "
                         f"than a live person ({value:.2f})"),
                   # Same reasoning as the match: a score of 0.05 is a confident
                   # spoof, not a weak one.
                   confidence=certainty(value, tuple(cfg["uncertain_band"])),
                   region=tuple(face["box"]), started=started)


def _tier2(ctx: ScreeningContext, *, store=None,
           doc_hash: str | None = None) -> list[Signal]:
    """Escalated only: 1:N duplicate identity, and active liveness.

    Active liveness needs a frame sequence the API does not carry yet, so it
    reports what is missing instead of a verdict. It is cut-list item 2 - at a
    manned counter an officer is standing there - and the passive check is the
    one that matters.
    """
    started = time.perf_counter()
    out = [_signal("face.liveness.active", "inconclusive",
                   "Blink-based liveness was not run - it needs a sequence of "
                   "frames, and this screening carried a single capture",
                   confidence=0.0, tier=2, started=started)]

    embedding = ctx.embeddings.get("live") or ctx.embeddings.get("doc")
    if embedding is None or store is None:
        out.append(_signal("face.gallery.duplicate", "inconclusive",
                           "The duplicate-identity search did not run - there "
                           "was no usable face embedding for this document",
                           confidence=0.0, tier=2))
        return out

    hits = gallery.search(store, embedding, doc_hash=doc_hash)
    if hits:
        out.append(_signal("face.gallery.duplicate", "fail",
                           gallery.describe(hits), confidence=hits[0]["cosine"],
                           tier=2, started=started))
    else:
        out.append(_signal("face.gallery.duplicate", "pass",
                           "This face has not been screened before under a "
                           "different document", confidence=0.7, tier=2,
                           started=started))
    return out
