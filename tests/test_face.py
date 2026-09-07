"""Module 4 - face verification.

Model-dependent tests are gated on the weights being present, the same way the
detector tests are. Everything that encodes a *decision* rather than a
measurement runs unconditionally, because those are the things that must not
regress whether or not a model is deployed:

  * no percentage anywhere, ever (D10)
  * an uncalibrated threshold says so, in the sentence the officer reads (D11)
  * a soft document photo asks for a better capture of the *document*
  * nothing is ever silently absent - no face is a signal, not a gap in the list
  * `face.*` signals carry weight in every profile

That last one is a regression test for a real bug: no profile had a `face.*`
weight pattern, only `face.match.cosine`, so a liveness check that correctly
rejected a printed photo held to the camera scored exactly zero and could not
move the verdict. That is Scene 4 of the demo.
"""
import glob
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from core import registry
from core.profiles import DOC_TYPES, load_config, load_profile, weight_for
from fusion.context import ScreeningContext
from fusion.findings import build_findings
from fusion.score import score
from modules import face
from modules.face import detect as detector
from modules.face import embed as embedder
from modules.face import gallery, liveness

ROOT = Path(__file__).resolve().parents[1]
FACES = sorted(glob.glob(str(ROOT / "data" / "raw" / "face" / "sfhq" / "**" /
                             "*.jpg"), recursive=True))

HAVE_MODELS = (registry.available(registry.FACE_DETECTOR)
               and registry.available(registry.FACE_EMBEDDING))

needs_models = pytest.mark.skipif(
    not HAVE_MODELS,
    reason="face weights are not in models/ yet - run scripts/fetch_face_models.py")
needs_faces = pytest.mark.skipif(
    not FACES, reason="no synthetic faces in data/raw/face (gitignored)")


def ctx_for(doc_type="passport", image=None, **kw):
    return ScreeningContext(
        session_id="t",
        image=image if image is not None else np.full((600, 900, 3), 200, np.uint8),
        doc_type=doc_type, profile=load_profile(doc_type), **kw,
    )


def by_id(signals):
    return {s.id: s for s in signals}


def card_with(portrait: np.ndarray, at=(60, 80)) -> np.ndarray:
    """A document-shaped image with a face printed on it."""
    card = np.full((600, 900, 3), 235, np.uint8)
    h, w = portrait.shape[:2]
    x, y = at
    card[y:y + h, x:x + w] = portrait
    cv2.putText(card, "SPECIMEN", (420, 300), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (30, 30, 30), 2, cv2.LINE_AA)
    return card


def portrait(index: int, size=(240, 200)) -> np.ndarray:
    image = cv2.imread(FACES[index])
    found = detector.largest(detector.detect(image)) if HAVE_MODELS else None
    if found is not None:
        x1, y1, x2, y2 = (int(v) for v in found["box"])
        pad = int((x2 - x1) * 0.45)
        image = image[max(0, y1 - pad):y2 + pad, max(0, x1 - pad):x2 + pad]
    return cv2.resize(image, size, interpolation=cv2.INTER_AREA)


# ------------------------------------------------------- decisions, always run

def test_the_score_is_never_a_percentage():
    """`((cos + 1) / 2) * 100` maps a stranger to 50 and an impostor to 58.

    An officer reads 58 as "more than half, probably him". The scale is wrong
    in the direction that admits fraudsters (D10), so no percentage of a cosine
    may appear anywhere the officer can see.
    """
    for cosine in (-0.4, 0.0, 0.16, 0.31, 0.55, 0.9):
        text = face.margin_text(cosine)
        assert "%" not in text
        assert f"{cosine:.2f}" in text
        # The stranger-maps-to-50 number must not be reachable from the text.
        assert str(round(((cosine + 1) / 2) * 100)) not in text.replace("0.", "")


def test_an_uncalibrated_threshold_says_so_where_the_officer_reads_it():
    cut, calibrated = face.threshold()
    assert not calibrated, (
        "the threshold is marked calibrated; if the pairs now exist, update "
        "this test and data/FACE.md, otherwise something set the flag by hand")
    assert "not yet calibrated" in face.margin_text(cut + 0.1)


def test_the_gallery_threshold_is_stricter_than_one_to_one():
    """A 1:1 comparison is one test; a gallery search is one per row. The same
    per-comparison error rate produces far more false alarms."""
    assert gallery.threshold() > face.threshold()[0]


def test_every_profile_gives_face_signals_real_weight():
    """The regression test for the bug that would have silenced liveness.

    A signal with no matching weight pattern resolves to 0.0, which makes it
    invisible to both coverage and the score - it renders as evidence and
    changes nothing.
    """
    for doc_type in DOC_TYPES:
        profile = load_profile(doc_type)
        for sid in ("face.doc.detected", "face.doc.quality", "face.live.detected",
                    "face.live.quality", "face.liveness.passive",
                    "face.liveness.active", "face.match.cosine",
                    "face.gallery.duplicate"):
            assert weight_for(profile, sid) > 0, f"{doc_type} / {sid}"


def test_the_specific_cosine_weight_still_beats_the_wildcard():
    """`weight_for` picks the longest matching pattern, so adding `face.*` must
    not have flattened the deliberate 0.15 on the match itself."""
    profile = load_profile("passport")
    assert weight_for(profile, "face.match.cosine") == 0.15
    assert weight_for(profile, "face.liveness.passive") == 0.10


def test_liveness_reports_a_gap_rather_than_a_pass_when_not_deployed():
    """A spoof check that has not run must never look like one that passed.

    At a manned counter the officer is the liveness check, and the console has
    to say the machine is not helping with this one.
    """
    if liveness.deployed():
        pytest.skip("liveness weights are deployed")
    signals = by_id(face.run(ctx_for()))
    passive = signals["face.liveness.passive"]
    assert passive.verdict == "inconclusive"
    assert "not deployed" in passive.evidence
    assert "Confirm visually" in passive.evidence


def test_no_live_capture_is_inconclusive_not_not_applicable():
    """Every one of the six types carries a photograph, so comparing the holder
    against it always applies - it just did not happen. `not_applicable` would
    leave the coverage denominator and let a document with no face check at all
    reach GREEN (D9)."""
    signals = by_id(face.run(ctx_for()))
    assert signals["face.match.cosine"].verdict == "inconclusive"
    assert signals["face.live.detected"].verdict == "inconclusive"


def test_missing_weights_produce_signals_rather_than_silence():
    if HAVE_MODELS:
        pytest.skip("face weights are present")
    signals = by_id(face.run(ctx_for()))
    for sid in ("face.doc.detected", "face.match.cosine"):
        assert signals[sid].verdict == "inconclusive"
        assert "not deployed" in signals[sid].evidence


def test_a_low_coverage_face_result_cannot_produce_green():
    """The property that makes all of the above worth doing."""
    profile = load_profile("passport")
    signals = face.run(ctx_for())
    verdict = score(signals, profile, build_findings(signals))
    assert verdict.band != "GREEN"


# ----------------------------------------------------------- with the weights

@needs_models
@needs_faces
def test_a_face_is_found_on_a_document_and_in_a_live_frame():
    card = card_with(portrait(0))
    found, how = detector.find(card)
    assert found is not None and how in ("direct", "denoised", "region")


@needs_models
@needs_faces
def test_the_same_person_matches_and_a_different_person_does_not():
    """The one measurement that says the alignment is right.

    A broken alignment still produces plausible embeddings - it just moves
    genuine pairs apart faster than impostor pairs, which looks like a
    threshold problem rather than a bug.
    """
    live = cv2.imread(FACES[0])
    same = card_with(portrait(0))
    other = card_with(portrait(1))

    def cosine_between(document, camera):
        a = detector.largest(detector.detect(document))
        b = detector.largest(detector.detect(camera))
        assert a is not None and b is not None
        return embedder.cosine(embedder.of(document, a["landmarks"]),
                               embedder.of(camera, b["landmarks"]))

    genuine = cosine_between(same, live)
    impostor = cosine_between(other, live)
    assert genuine > impostor + 0.2, f"genuine {genuine:.2f} impostor {impostor:.2f}"
    assert genuine > face.threshold()[0]


@needs_models
@needs_faces
def test_impostors_stay_below_the_configured_threshold():
    cut = face.threshold()[0]
    vectors = []
    for index in range(min(8, len(FACES))):
        image = cv2.imread(FACES[index])
        found = detector.largest(detector.detect(image))
        if found is not None:
            vectors.append(embedder.of(image, found["landmarks"]))
    assert len(vectors) >= 4

    crossed = [embedder.cosine(vectors[i], vectors[j])
               for i in range(len(vectors)) for j in range(i + 1, len(vectors))]
    assert max(crossed) < cut, (
        f"an impostor pair reached {max(crossed):.2f} against a {cut:.2f} "
        f"threshold")


@needs_models
@needs_faces
def test_a_soft_document_photo_asks_for_a_better_document_capture():
    """Not "retake your selfie". The printed photo cannot be retaken, and
    saying the wrong thing sends an officer round a loop that never ends."""
    soft = cv2.GaussianBlur(card_with(portrait(0)), (0, 0), 4)
    signals = by_id(face.run(ctx_for(image=soft)))
    quality = signals["face.doc.quality"]
    if quality.verdict != "fail":
        pytest.skip("this portrait survived the blur; nothing to assert")
    assert "capture of the document" in quality.evidence
    assert "selfie" not in quality.evidence.lower()


@needs_models
@needs_faces
def test_a_matching_pair_passes_end_to_end_through_the_module():
    ctx = ctx_for(image=card_with(portrait(0)))
    ctx.faces["live"] = cv2.imread(FACES[0])
    signals = by_id(face.run(ctx))
    assert signals["face.match.cosine"].verdict == "pass"
    assert "cosine" in signals["face.match.cosine"].evidence
    assert ctx.embeddings["doc"].shape == (512,)
    assert ctx.embeddings["live"].shape == (512,)


@needs_models
@needs_faces
def test_a_mismatched_pair_fails_end_to_end():
    ctx = ctx_for(image=card_with(portrait(1)))
    ctx.faces["live"] = cv2.imread(FACES[0])
    signals = by_id(face.run(ctx))
    assert signals["face.match.cosine"].verdict == "fail"


@needs_models
@needs_faces
def test_the_cosine_rides_on_confidence_so_the_risk_gate_can_read_it():
    """`fusion/gate.py` decides escalation by testing whether the review band
    contains the signal's `confidence`. If the cosine stops living there, the
    gate silently stops escalating borderline matches."""
    from fusion.gate import decide
    ctx = ctx_for(image=card_with(portrait(0)))
    ctx.faces["live"] = cv2.imread(FACES[0])
    match = by_id(face.run(ctx))["face.match.cosine"]

    low, high = face.review_band()
    assert 0.0 <= match.confidence <= 1.0
    borderline = type(match)(**{**match.__dict__,
                                "confidence": (low + high) / 2,
                                "verdict": "pass"})
    decision, _reason = decide([borderline], load_profile("passport"))
    assert decision == "escalate"


@needs_models
@needs_faces
def test_every_face_signal_that_located_something_carries_a_region():
    ctx = ctx_for(image=card_with(portrait(0)))
    ctx.faces["live"] = cv2.imread(FACES[0])
    signals = by_id(face.run(ctx))
    assert signals["face.doc.detected"].region is not None
    assert signals["face.match.cosine"].region is not None


@needs_models
@needs_faces
def test_tier_two_signals_are_tagged_tier_two():
    """The router drops any that are not, so a mistagged gallery hit is an
    invisible finding."""
    ctx = ctx_for(image=card_with(portrait(0)))
    for signal in face.run(ctx, tier=2):
        assert signal.tier == 2, signal.id


@needs_models
@needs_faces
def test_the_gallery_finds_a_returning_face_under_a_different_document():
    from core.store import Store
    store = Store(":memory:")
    image = cv2.imread(FACES[0])
    found = detector.largest(detector.detect(image))
    vector = embedder.of(image, found["landmarks"])

    event = store.record_event(
        session_id="earlier", doc_type="aadhaar", doc_hash="hash-a",
        verdict="GREEN", score=0.0, coverage=1.0, signals=[],
        model_versions={}, id_number=None)
    store.add_face(event, vector)

    assert gallery.search(store, vector, doc_hash="hash-b"), "a duplicate identity was missed"
    assert not gallery.search(store, vector, doc_hash="hash-a"), (
        "the same document coming back is a re-capture, not a duplicate identity")


@needs_models
@needs_faces
def test_tier_one_face_verification_stays_inside_its_320ms_budget():
    """TECHNICAL-SPEC.md section 2, L6: two faces plus passive liveness."""
    ctx = ctx_for(image=card_with(portrait(0)))
    ctx.faces["live"] = cv2.imread(FACES[0])

    for _ in range(2):
        face.run(ctx)
    started = time.perf_counter()
    runs = 3
    for _ in range(runs):
        face.run(ctx)
    per_call_ms = (time.perf_counter() - started) * 1000 / runs
    assert per_call_ms < 320, f"tier 1 face took {per_call_ms:.0f} ms"
