"""One check, one signal id. The invariant, enforced.

A signal id is not a label - it is the key a re-scoring reads years later, the
key `reliability()` looks a weight up under, and the key a profile names in
`weights` and `hard_fail`. Two different checks sharing one id breaks all three
quietly:

  * the audit log cannot say which of them produced a verdict;
  * both are scored at whichever weight the id carries, so the softer check
    borrows the harder one's authority;
  * they land in the same anchor group and **both count against coverage**,
    which is the correlated-signal double count D8 exists to prevent.

Two real instances were found by exactly this check and are what it now guards.
`core/quality.py` filed brightness under the blur id on the document path, and
under `face.live.quality` - the *face crop* gate's id - on the live path. And
`modules/extraction/qr.py` emitted `validation.signature.valid` for a condition
Layer A already reported, so on a passport, where it is weighted 0.25, a missing
signature dragged coverage down twice as hard as it should.

Neither looked wrong. Both were one line.
"""
import collections

import numpy as np
import pytest

from api import router as pipeline
from core.profiles import DOC_TYPES, reliability
from core.quality import check, is_usable
from core.store import Store
from data.tools import mutate


def ids_of(signals):
    return [s.id for s in signals]


def duplicates(signals):
    counts = collections.Counter(ids_of(signals))
    return {name: n for name, n in counts.items() if n > 1}


# ------------------------------------------------------------- the quality gate

@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("shade", [12, 128, 250])
def test_the_quality_gate_gives_each_check_its_own_id(live, shade):
    """Dark, normal and washed out, on both capture paths."""
    image = np.full((700, 900, 3), shade, np.uint8)
    signals = check(image, live=live)
    assert not duplicates(signals), duplicates(signals)
    assert len(signals) == 3, "resolution, blur and brightness, always"


def test_brightness_is_scored_as_brightness_and_not_as_blur():
    """The consequence of the collision, not just its shape.

    Sharing the blur id meant a washed-out capture was weighted 0.80 - blur's
    reliability - rather than its own.
    """
    dark = np.full((700, 900, 3), 10, np.uint8)
    by_id = {s.id: s for s in check(dark)}
    assert "extraction.quality.brightness" in by_id
    assert by_id["extraction.quality.brightness"].verdict == "fail"
    assert reliability("extraction.quality.brightness") == 0.70
    assert reliability("extraction.quality.blur") == 0.80


def test_the_live_path_does_not_borrow_the_face_crop_gate_s_id():
    """`face.live.quality` belongs to the face-crop gate in modules/face.

    The whole-frame brightness check reported under it, so on a dark live
    capture two unrelated checks filed under one name.
    """
    dark = np.full((700, 900, 3), 10, np.uint8)
    assert "face.live.quality" not in ids_of(check(dark, live=True))


def textured(mean: int) -> np.ndarray:
    """A sharp image at a chosen brightness.

    Flat fill will not do: a uniform field has zero Laplacian variance, so the
    blur check fails and every assertion about brightness is really an
    assertion about blur.
    """
    rng = np.random.default_rng(0)
    noise = rng.integers(-40, 41, size=(700, 900, 1), dtype=np.int16)
    return np.clip(noise + mean, 0, 255).astype(np.uint8).repeat(3, axis=2)


def test_a_washed_out_capture_is_not_worth_spending_model_time_on():
    """`is_usable` gates on any quality failure, not only on blur.

    It used to match the `.quality.blur` suffix, so splitting brightness out
    would silently have narrowed it - a washed-out capture would have been
    judged worth spending model time on.
    """
    even = check(textured(128))
    assert all(s.verdict == "pass" for s in even), ids_of(even)
    assert is_usable(even)

    glare = check(textured(250))
    assert not is_usable(glare)
    assert {s.id for s in glare if s.verdict == "fail"} == {
        "extraction.quality.brightness"}


def test_the_brightness_evidence_tells_the_officer_what_to_do():
    """It is the sentence they act on, so it has to name the remedy."""
    dark = {s.id: s for s in check(np.full((700, 900, 3), 5, np.uint8))}
    assert "Re-capture" in dark["extraction.quality.brightness"].evidence
    live = {s.id: s for s in check(np.full((700, 900, 3), 5, np.uint8), live=True)}
    assert "glare" in live["face.live.quality.brightness"].evidence


# ------------------------------------------------------- the whole pipeline

@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_a_screening_never_emits_one_id_twice(doc_type):
    """The general guard, and the one that found the signature duplicate.

    Every id in this system is emitted by exactly one check, so a full run
    should contain no id twice. Templated families - one signal per field, one
    per MRZ check digit - are still unique, because the field name is in the id.
    """
    raw = mutate.as_jpeg(mutate.synthetic_card(seed=3))
    ctx = pipeline.build_context(raw, doc_type, "identity")
    # A dark live frame, so the brightness and face paths both fire.
    ctx.faces["live"] = np.full((500, 500, 3), 12, np.uint8)

    for _ in pipeline.screen(ctx, store=Store(":memory:"), uploaded=True, raw=raw):
        pass

    assert not duplicates(ctx.signals), (
        f"{doc_type} emitted an id more than once: {duplicates(ctx.signals)}. "
        f"Two checks sharing an id double-count against coverage and cannot be "
        f"told apart in the audit log.")


def test_extraction_does_not_report_validation_verdicts():
    """Module boundaries, checked where they actually broke.

    `qr.py` emitted `validation.signature.valid`. Extraction locates and reads;
    whether a signature verifies is validation's to say.
    """
    from modules.extraction import qr
    payload, signals = qr.scan(np.full((400, 400, 3), 200, np.uint8),
                               {"extract": {"detector_classes": ["qr_code"]},
                                "doc_type": "passport"})
    assert payload is None
    assert signals == [], (
        "extraction is emitting signals for a check another module owns")
