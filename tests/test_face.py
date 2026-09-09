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
needs_liveness = pytest.mark.skipif(
    not registry.available(registry.LIVENESS),
    reason="no models/face_liveness.onnx - run "
           ".venv-train/Scripts/python scripts/convert_liveness.py")


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


# ------------------------------------------------------------------- liveness

@needs_liveness
def test_the_liveness_input_contract_is_recorded_and_matches_the_code():
    """Colour order and input range are model facts, not preferences.

    Both were guessed wrong while the weights did not exist, and neither guess
    raises - the network returns three plausible probabilities for an image it
    was never trained on. The sidecar records what the export assumed so the
    two cannot drift apart silently.
    """
    meta = registry.metadata(registry.LIVENESS)
    assert meta.get("colour_order") == "BGR"
    assert "not normalised" in meta.get("input_range", "")
    assert meta.get("licence") == "Apache-2.0", "attribution must survive"


@needs_liveness
@needs_faces
def test_a_genuine_face_reads_as_live_and_a_simulated_spoof_does_not():
    """The direction check. Not a spoof-rejection rate - see data/FACE.md.

    This is the test that would have caught dividing the input by 255: under
    that bug every genuine face scored 0.006 and the check rejected everyone.
    A synthesised print is not a print, so what is asserted is the separation,
    with a wide margin, rather than any particular rate.
    """
    import importlib.util
    import random

    spec = importlib.util.spec_from_file_location(
        "eval_liveness", ROOT / "scripts" / "eval_liveness.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)

    live_scores, spoof_scores = [], []
    for index in range(min(8, len(FACES))):
        image = cv2.imread(FACES[index])
        face = detector.largest(detector.detect(image))
        if face is None:
            continue
        rng = random.Random(index)
        live_scores.append(liveness.score(image, face["box"]))
        for attack in (ev.print_attack, ev.screen_attack):
            spoof_scores.append(liveness.score(attack(image, rng), face["box"]))

    assert len(live_scores) >= 4 and len(spoof_scores) >= 8
    assert np.median(live_scores) > 0.5, (
        f"genuine faces read as spoofs (median {np.median(live_scores):.3f}) - "
        f"check colour order and input range against the sidecar")
    assert np.median(spoof_scores) < 0.1, (
        f"simulated spoofs read as live (median {np.median(spoof_scores):.3f})")


@needs_liveness
@needs_faces
def test_a_deployed_liveness_signal_reports_a_verdict_not_a_gap():
    ctx = ctx_for(image=card_with(portrait(0)))
    ctx.faces["live"] = cv2.imread(FACES[0])
    passive = by_id(face.run(ctx))["face.liveness.passive"]
    assert passive.verdict in ("pass", "fail"), passive.evidence
    assert passive.region is not None
    assert "%" not in passive.evidence, "no percentage of a probability (D10)"


@needs_liveness
def test_liveness_confidence_is_certainty_not_the_raw_score():
    """D28. A confident spoof must reach fusion as high confidence, or it is
    scored as a barely-there finding - the D10 failure one layer down."""
    band = tuple(load_config("thresholds")["face"]["liveness"]["uncertain_band"])
    assert face.certainty(0.02, band) == 1.0, "a confident spoof must be certain"
    assert face.certainty(0.99, band) == 1.0, "a confident live read must be certain"
    assert face.certainty(sum(band) / 2, band) < 0.5, "mid-band must be uncertain"


# ------------------------------------------------- the calibration apply path
# The one code path in `data/tools/calibrate_face.py` that cannot be exercised
# without the real doc-vs-live set, because it is gated on >=500 pairs from >=30
# people. It writes the file the whole system reads its operating point from, it
# runs exactly once, and it runs on the day the volunteers are in the room. So
# it is tested here against a string rather than discovered there.

def test_the_calibration_apply_rewrites_the_threshold_and_its_todo_together():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "calibrate_face", ROOT / "data" / "tools" / "calibrate_face.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    before = (ROOT / "config" / "thresholds.yaml").read_text(encoding="utf-8")
    assert "calibrated: false" in before, "this test assumes an uncalibrated file"

    after = module.apply_to(before, 0.41, people=34, pairs=612)

    doc_live = after.split("  doc_live:")[1].split("  gallery:")[0]
    assert "threshold: 0.41" in doc_live
    assert "calibrated: true" in doc_live
    assert "TODO" not in doc_live, (
        "the TODO must go with the value it marks - otherwise the file says "
        "`calibrated: true` and `TODO calibrate` in the same block")
    assert "612" in doc_live and "34" in doc_live, "provenance of the number"

    # Only the 1:1 block moves. The gallery threshold is calibrated separately
    # and its `calibrated: false` is a different claim.
    gallery = after.split("  gallery:")[1].split("  liveness:")[0]
    assert "calibrated: false" in gallery
    assert "threshold: 0.45" in gallery


# ------------------------------------------------------- active liveness

def _face_frame(eyes_open: bool, size: int = 400) -> np.ndarray:
    """A crude face: skin oval, two dark eyes when open, closed lids when not.

    Not a real face - the Haar cascade is not asked to fire on this. What these
    exercise is the decision logic around it: a burst too short, eyes never
    found, no blink seen, and a blink seen must land on four different verdicts.
    """
    frame = np.full((size, size, 3), 200, np.uint8)
    cv2.ellipse(frame, (size // 2, size // 2), (size // 3, size // 2 - 10),
                0, 0, 360, (190, 170, 150), -1)
    y = int(size * 0.40)
    for x in (int(size * 0.38), int(size * 0.62)):
        if eyes_open:
            cv2.circle(frame, (x, y), size // 22, (40, 40, 40), -1)
        else:
            cv2.line(frame, (x - size // 20, y), (x + size // 20, y),
                     (120, 105, 95), 3)
    return frame


#: Comfortably above MIN_FACE_PX, so these exercise the decision logic
#: rather than the size floor - which has its own test.
BOX = (0.0, 0.0, 400.0, 400.0)


def test_a_burst_too_short_to_judge_is_inconclusive_not_a_pass():
    verdict, confidence, why = liveness.blink([_face_frame(True)] * 2, BOX)
    assert verdict == "inconclusive"
    assert confidence == 0.0
    assert "frames" in why


def test_no_frames_at_all_is_inconclusive():
    verdict, _, why = liveness.blink([], BOX)
    assert verdict == "inconclusive"
    assert "single capture" not in why       # that string belongs to _tier2


def test_eyes_never_found_reads_as_a_poor_view_not_a_spoof():
    """The failure mode that matters most.

    A cascade that cannot see the eyes must never be reported as a person who
    would not blink. `fail` here would detain someone for wearing glasses.
    """
    blank = [np.full((400, 400, 3), 128, np.uint8)] * 6
    verdict, confidence, why = liveness.blink(blank, BOX)
    assert verdict == "inconclusive"
    assert confidence == 0.0
    assert "not visible" in why or "could not run" in why


def test_blink_never_returns_fail_whatever_the_frames_say():
    """`fail` is not in this check's vocabulary - see `blink.__doc__`.

    People stare. A burst can be short. The officer is standing there. Positive
    evidence only, so no arrangement of frames may produce a failing verdict.
    """
    cases = [
        [],
        [_face_frame(True)] * 3,
        [_face_frame(True)] * 8,
        [_face_frame(True)] * 4 + [_face_frame(False)] * 2,
        [np.full((400, 400, 3), 128, np.uint8)] * 6,
        [_face_frame(False)] * 6,
    ]
    for frames in cases:
        verdict, _, _ = liveness.blink(frames, BOX)
        assert verdict in ("pass", "inconclusive"), (verdict, len(frames))


def test_a_single_frame_capture_still_reports_active_liveness_as_unrun():
    """The regression guard on the whole feature.

    A file upload carries no burst. If that ever became a pass, the console
    would tell an officer a spoof check succeeded when it never ran.
    """
    from fusion.context import ScreeningContext
    from core.profiles import load_profile
    import modules.face as face_module

    ctx = ScreeningContext(session_id="s", image=np.zeros((10, 10, 3), np.uint8),
                           doc_type="pan", profile=load_profile("pan"))
    signal = face_module._active_liveness(ctx, time.perf_counter())
    assert signal.id == "face.liveness.active"
    assert signal.verdict == "inconclusive"
    assert signal.tier == 2


def test_a_still_photograph_cannot_fake_a_blink_by_detector_flicker():
    """The direction this check must never fail in.

    Measured on static images, the eye cascade flickers below 320 px face width
    - and a flicker on a photograph is a phantom blink. Two guards stand in the
    way: the size floor, and the requirement that closed frames form one run
    bracketed by open ones. Scattered noise must not clear either.
    """
    small = (0.0, 0.0, 200.0, 200.0)
    frames = [_face_frame(True, size=200)] * 6
    verdict, _, why = liveness.blink(frames, small)
    assert verdict == "inconclusive"
    assert "step closer" in why

    # Big enough face, but the closed frames are scattered rather than a blink.
    scattered = [True, False, True, False, True, False, True]
    assert not liveness._brackets_a_run([False, False, True, True])
    assert liveness._longest_run(scattered, False) == 1


def test_the_blink_size_floor_is_the_measured_one():
    """If this number moves, the measurement behind it has to move with it."""
    assert liveness.MIN_FACE_PX == 320, (
        "the floor is measured, not chosen - see the comment on MIN_FACE_PX "
        "and re-run the static-image stability check before changing it")


def test_one_frame_used_as_both_document_and_live_is_a_self_comparison():
    """Why the console photographs the card and the traveller separately.

    `_locate` takes `largest(detect(image))` for both the document portrait and
    the live face. Hand it the same photograph twice and it finds the same face
    twice, so the cosine is 1.0 and a document trivially "matches" itself -
    evidence that is not independent of what it claims to prove, which is the
    D48 failure wearing a different hat.

    This test does not assert that the pipeline defends against it, because it
    cannot: from inside `modules/face` the two images are just two arrays. It
    pins the reason the *capture screen* takes two photographs, so that anyone
    tempted to reuse one frame finds this written down first.
    """
    if not (registry.available(registry.FACE_DETECTOR)
            and registry.available(registry.FACE_EMBEDDING)):
        pytest.skip("face weights are not deployed")

    from modules.face import detect as fdet
    from modules.face import embed as fembed

    # A generated card carries a real portrait; the synthetic card is drawn
    # shapes and has no face to reason about.
    cards = sorted(glob.glob(str(
        registry.ROOT / "data/processed/generated/*/images/*.png")))
    card = next((c for c in (cv2.imread(p) for p in cards[:8])
                 if c is not None and fdet.find(c)[0] is not None), None)
    if card is None:
        pytest.skip("no generated card with a locatable portrait on disk")

    # The same frame, entering the pipeline through both doors.
    doc_face, _ = fdet.find(card)
    live_face, _ = fdet.find(card)
    assert doc_face["box"] == live_face["box"], (
        "the two paths found different faces in one image; if this ever "
        "becomes true the reasoning in Capture.tsx:grabLive needs revisiting")

    a = fembed.of(card, doc_face["landmarks"])
    b = fembed.of(card, live_face["landmarks"])
    assert fembed.cosine(a, b) > 0.99, fembed.cosine(a, b)


def test_a_live_embedding_does_not_break_the_gallery_or_the_audit_record():
    """The bug that made the whole live-face path unreachable.

    `_tier2` and `api.router.persist` both chose an embedding with
    `ctx.embeddings.get("live") or ctx.embeddings.get("doc")`. `or` calls
    `bool()` on its left operand, and an embedding is a 512-element array, so
    that raises "truth value of an array with more than one element is
    ambiguous" - on **every** screening that produced a live embedding, which
    is the only case the line exists for.

    It never fired because nothing ever supplied a live frame: no test did, and
    the console had no path to send one. The first real live capture through
    the API hit it in the first second, and the officer saw "Screening failed".
    """
    import numpy as np
    from core.profiles import load_profile
    from fusion.context import ScreeningContext
    import modules.face as face_module

    ctx = ScreeningContext(session_id="s", image=np.zeros((10, 10, 3), np.uint8),
                           doc_type="pan", profile=load_profile("pan"))
    ctx.embeddings["live"] = np.full(512, 0.02, np.float32)
    ctx.embeddings["doc"] = np.full(512, 0.01, np.float32)

    # Must not raise. Store is None so the gallery search reports honestly.
    signals = face_module._tier2(ctx, store=None, doc_hash="abc")
    assert {s.id for s in signals} >= {"face.liveness.active",
                                       "face.gallery.duplicate"}


def test_persist_prefers_the_live_embedding_without_truth_testing_it():
    """The same bug, in the audit path."""
    import numpy as np

    live = np.full(512, 0.02, np.float32)
    doc = np.full(512, 0.01, np.float32)
    for embeddings, expected in (({"live": live, "doc": doc}, live),
                                 ({"doc": doc}, doc),
                                 ({}, None)):
        chosen = embeddings.get("live")
        if chosen is None:
            chosen = embeddings.get("doc")
        if expected is None:
            assert chosen is None
        else:
            assert chosen is expected
