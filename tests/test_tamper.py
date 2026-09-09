"""Module 3 - tampering.

Two kinds of test here, and the second kind is the one that would catch a real
regression.

**Structure**, on hand-built contexts: which checks run on which input, what a
blocked check says, that `not_applicable` and `inconclusive` are not confused,
that every failing signal carries a region. These need no image on disk.

**Behaviour**, on genuine cards from the held-out split with mutations applied:
each check fires on the family it can see and stays quiet on untouched cards.
Those are skipped when the dataset is absent, because `data/processed/` is
gitignored and a fresh clone has no cards - the same pattern the detector tests
use for absent weights.

The false-positive assertions matter more than the detection ones. A check that
misses a forgery costs one signal; a check that accuses genuine documents makes
an officer stop reading the evidence list, which costs every signal.

Measured operating points live in data/TAMPERING.md. The bounds asserted below
are deliberately looser than the measured numbers - a test that pins an exact
rate fails on a different sample of the same distribution and teaches everyone
to ignore it.
"""
import glob
import random
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from core.decode import downscale
from core.profiles import load_config, load_profile
from data.tools import mutate
from fusion.context import ScreeningContext
from modules import tamper
from modules.tamper import digital, physical

ROOT = Path(__file__).resolve().parents[1]
CARDS = sorted(glob.glob(str(ROOT / "data" / "processed" / "fields" / "test" /
                             "images" / "*.jpg")))

needs_cards = pytest.mark.skipif(
    not CARDS, reason="no genuine cards in data/processed/fields (gitignored)")

CFG = load_config("thresholds")["tamper"]


def ctx_for(doc_type="passport", image=None, **kw):
    return ScreeningContext(
        session_id="t",
        image=image if image is not None else mutate.synthetic_card(seed=1),
        doc_type=doc_type, profile=load_profile(doc_type), **kw,
    )


def by_id(signals):
    return {s.id: s for s in signals}


def sample_cards(n, seed=0):
    random.seed(seed)
    picked = random.sample(CARDS, min(n, len(CARDS)))
    for path in picked:
        raw = cv2.imread(path)
        if raw is not None:
            yield downscale(raw)


# ------------------------------------------------------------------- structure

def test_scanner_input_makes_the_compression_checks_not_applicable():
    """The scanner wrote the file, so there is no editing history in it (D12).

    `not_applicable`, never `pass`: the check did not clear the document, it
    did not apply. The difference is arithmetic - `not_applicable` leaves the
    coverage fraction entirely, `pass` would raise it.
    """
    signals = by_id(tamper.run(ctx_for(), uploaded=False))
    for sid in tamper.UPLOAD_ONLY:
        assert signals[sid].verdict == "not_applicable", sid


def test_uploads_get_a_real_verdict_on_the_compression_checks():
    """EXIF is excluded: a file with no Software tag is genuinely
    `not_applicable`, which the next test pins down."""
    card = mutate.synthetic_card(seed=2)
    raw = mutate.as_jpeg(card)
    signals = by_id(tamper.run(ctx_for(image=card), uploaded=True, raw=raw))
    for sid in ("tamper.digital.double_jpeg", "tamper.digital.ela"):
        assert signals[sid].verdict in ("pass", "fail"), sid


def test_an_upload_with_no_bytes_is_inconclusive_not_a_pass():
    """Missing evidence is a gap. Silently passing would be the dangerous read."""
    signals = by_id(tamper.run(ctx_for(), uploaded=True, raw=None))
    assert signals["tamper.digital.exif_software"].verdict == "inconclusive"
    assert signals["tamper.digital.double_jpeg"].verdict == "inconclusive"


def test_blocked_checks_say_why_rather_than_just_reporting_nothing():
    """An officer who reads "not evaluated" must be able to see what is missing.

    Every blocked check names its own obstacle - no template, no training data,
    no stamp class, or a measurement that does not discriminate - because a bare
    "not evaluated" repeated five times reads as a broken system.
    """
    signals = by_id(tamper.run(ctx_for("passport")))
    for sid in tamper.BLOCKED:
        if sid not in signals:
            continue
        assert signals[sid].verdict == "inconclusive", sid
        assert len(signals[sid].evidence) > 40, sid
        assert signals[sid].evidence != "not evaluated"


def test_pixel_forensics_run_on_scanner_input_too():
    """Copy-move and noise residual are pixel-domain, not compression-domain.

    A photo pasted onto a card and then scanned is still two regions with one
    origin. Filing these under "uploads only" alongside EXIF would mean the
    counter never runs the one check that finds a physically altered card.
    """
    signals = by_id(tamper.run(ctx_for(), tier=2, uploaded=False))
    for sid in ("tamper.digital.copy_move", "tamper.digital.noise_residual"):
        assert signals[sid].verdict in ("pass", "fail"), sid
        assert signals[sid].tier == 2


def test_tier_two_checks_do_not_run_in_tier_one():
    """The router drops signals whose tier does not match, so emitting them
    early is not merely wasted work - it is invisible wasted work."""
    ids = {s.id for s in tamper.run(ctx_for(), tier=1)}
    assert "tamper.digital.copy_move" not in ids
    assert "tamper.digital.noise_residual" not in ids


#: The two byte-domain checks have nothing to point at. EXIF and the
#: quantisation table are properties of the file, not of a place on the page,
#: and inventing a rectangle for them would send an officer to look at a region
#: that has nothing to do with the finding.
NO_REGION = {"tamper.digital.exif_software", "tamper.digital.double_jpeg"}


def test_every_failing_pixel_check_carries_a_region_for_the_overlay():
    """MODULES.md definition of done. A finding an officer cannot locate on the
    document is a number, not evidence."""
    for image in sample_cards(6, seed=3) if CARDS else [mutate.synthetic_card()]:
        mutated, _mask = mutate.splice(image, seed=1)
        signals = tamper.run(ctx_for(image=mutated), tier=2, uploaded=True,
                             raw=mutate.as_jpeg(mutated))
        for s in signals:
            if s.verdict == "fail" and s.id not in NO_REGION:
                assert s.region is not None, s.id


def test_a_profile_only_gets_the_checks_it_declares():
    """PAN declares no MRZ and no stamps; it must not be charged coverage for
    them."""
    ids = {s.id for s in tamper.run(ctx_for("pan"))}
    assert "tamper.stamp.duplicate" not in ids
    assert "tamper.physical.layout_geometry" in ids


def test_every_emitted_id_has_a_reliability_weight_and_a_profile_weight():
    from core.profiles import reliability, weight_for
    profile = load_profile("passport")
    for s in tamper.run(ctx_for("passport"), tier=2, uploaded=True,
                        raw=mutate.as_jpeg(mutate.synthetic_card())):
        assert 0 < reliability(s.id) <= 1.0, s.id
        assert weight_for(profile, s.id) > 0, s.id


# ------------------------------------------------------------- the byte domain

def test_exif_reads_the_software_tag_and_absence_is_not_innocence():
    """EXIF is one delete away, so no tag must never read as a clean bill."""
    plain = mutate.as_jpeg(mutate.synthetic_card())
    assert digital.exif_software(plain) is None

    signal = by_id(tamper.run(ctx_for(), uploaded=True, raw=plain))
    assert signal["tamper.digital.exif_software"].verdict == "not_applicable"


def test_exif_flags_an_editor_and_clears_a_camera():
    from tests.exif_fixture import with_software          # local helper
    card = mutate.synthetic_card()
    edited = with_software(mutate.as_jpeg(card), "Adobe Photoshop 25.0")
    camera = with_software(mutate.as_jpeg(card), "NIKON D7500 Ver.1.01")

    assert digital.exif_software(edited) == "Adobe Photoshop 25.0"
    assert by_id(tamper.run(ctx_for(), uploaded=True,
                            raw=edited))["tamper.digital.exif_software"].verdict == "fail"
    assert by_id(tamper.run(ctx_for(), uploaded=True,
                            raw=camera))["tamper.digital.exif_software"].verdict == "pass"


def test_a_standard_libjpeg_table_is_recognised_as_standard():
    """OpenCV writes IJG tables, which is what every camera and scanner does.

    If this ever fails, the quantisation check has started calling ordinary
    files edited - which is a false accusation on every upload.
    """
    for quality in (60, 75, 90, 95):
        raw = mutate.as_jpeg(mutate.synthetic_card(), quality=quality)
        table = digital.quant_tables(raw)[0]
        found, exact = digital.standard_quality(table)
        assert exact, f"quality {quality} table was not recognised as standard"
        assert abs(found - quality) <= 1


def test_a_non_jpeg_upload_is_not_applicable_rather_than_a_failure():
    png = cv2.imencode(".png", mutate.synthetic_card())[1].tobytes()
    signal = by_id(tamper.run(ctx_for(), uploaded=True, raw=png))
    assert signal["tamper.digital.double_jpeg"].verdict == "not_applicable"


# --------------------------------------------------------------------- physics

def test_glyph_metrics_separate_one_printing_from_two():
    """Uniform machine printing against a line with a second font mixed in."""
    uniform = np.full((60, 520, 3), 240, np.uint8)
    cv2.putText(uniform, "PRADEEP GHARAT", (8, 44), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, (20, 20, 20), 2, cv2.LINE_AA)

    mixed = uniform.copy()
    cv2.putText(mixed, "1998", (330, 52), cv2.FONT_HERSHEY_DUPLEX,
                1.9, (20, 20, 20), 3, cv2.LINE_AA)

    even, n_even = physical.glyph_height_cv(uniform)
    uneven, n_mixed = physical.glyph_height_cv(mixed)
    assert n_even >= 4 and n_mixed >= 4
    assert uneven > even


def test_layout_reference_exists_for_every_document_type():
    """The check is worthless without one, and it is cheap to build."""
    from core.profiles import DOC_TYPES
    for doc_type in DOC_TYPES:
        reference = physical.layout_reference(doc_type)
        assert reference is not None, (
            f"no config/layout/{doc_type}.json - run data/tools/build_layout.py")
        assert reference["fields"], doc_type


def test_a_field_moved_across_the_card_is_out_of_place():
    reference = physical.layout_reference("pan")
    name = next(n for n, f in reference["fields"].items()
                if f["n"] >= physical.MIN_REFERENCE_CARDS)
    stats = reference["fields"][name]
    shape = (600, 900, 3)

    where_it_belongs = {name: (stats["cx"] * 900 - 40, stats["cy"] * 600 - 15,
                               stats["cx"] * 900 + 40, stats["cy"] * 600 + 15)}
    assert not physical.layout_outliers(where_it_belongs, shape, reference,
                                        CFG["layout_mad"])

    # Mirrored across the card. The measured spread on real cards is wide - a
    # PAN date of birth moves by five percent of the page between captures - so
    # a field has to be genuinely somewhere else before this fires. That is the
    # right way round: the check should never argue with a crooked scan.
    moved_x = (1 - stats["cx"]) * 900
    moved_y = (1 - stats["cy"]) * 600
    moved = {name: (moved_x - 40, moved_y - 15, moved_x + 40, moved_y + 15)}
    outliers = physical.layout_outliers(moved, shape, reference, CFG["layout_mad"])
    assert outliers and outliers[0][0] == name


def test_a_field_with_too_few_genuine_examples_is_never_checked():
    """A position measured on a handful of cards from one source is not a fact
    about the document type, and checking against it accuses genuine cards."""
    reference = {"fields": {"signature": {"cx": 0.5, "cy": 0.5,
                                          "mad_x": 0.01, "mad_y": 0.01, "n": 25}}}
    boxes = {"signature": (0.0, 0.0, 20.0, 20.0)}
    assert not physical.layout_outliers(boxes, (600, 900, 3), reference, 5.0)


def test_layout_and_print_consistency_are_inconclusive_without_a_detector():
    """No field boxes means nothing was measured. Saying so costs coverage,
    which is correct - it must not read as a clean document (D9)."""
    signals = by_id(tamper.run(ctx_for("passport")))
    assert signals["tamper.physical.layout_geometry"].verdict == "inconclusive"
    assert signals["tamper.physical.ocrb_conformance"].verdict == "inconclusive"
    assert "detector" in signals["tamper.physical.layout_geometry"].evidence


# -------------------------------------------------------------------- behaviour

@needs_cards
def test_copy_move_finds_a_duplicated_patch_and_leaves_genuine_cards_alone():
    """The number that matters is the second one.

    Measured at 50% detection against 6% false positives on 150 genuine cards
    (data/TAMPERING.md). The bounds here are loose on purpose - pinning the
    exact rate makes the test fail on a different sample and teaches everyone
    to ignore it.
    """
    detected = flagged = total = 0
    for n, image in enumerate(sample_cards(30, seed=4)):
        total += 1
        if digital.copy_move(image, CFG)[1] is not None:
            flagged += 1
        mutated, _mask = mutate.copy_move(image, seed=n)
        if digital.copy_move(mutated, CFG)[1] is not None:
            detected += 1

    assert total >= 10
    assert flagged / total <= 0.20, (
        f"{flagged}/{total} genuine cards flagged as copy-move")
    assert detected / total >= 0.25, (
        f"only {detected}/{total} duplications found")
    assert detected > flagged


@needs_cards
def test_ela_separates_a_spliced_region_from_an_untouched_card():
    clean = [digital.ela(image)[0] for image in sample_cards(20, seed=5)]
    spliced = [digital.ela(mutate.splice(image, seed=n)[0])[0]
               for n, image in enumerate(sample_cards(20, seed=5))]
    assert np.median(spliced) > np.median(clean)


@needs_cards
def test_the_copy_move_region_lands_on_what_was_actually_moved():
    """A highlight in the wrong place is worse than no highlight - the officer
    checks the clean half of the card and concludes the system is wrong.

    Either end of the duplication counts. The finding is "these two areas are
    the same picture", so pointing at either one has told the truth.
    """
    hits = overlaps = 0
    for n, image in enumerate(sample_cards(30, seed=6)):
        mutated, mask = mutate.copy_move(image, seed=n)
        _count, region = digital.copy_move(mutated, CFG)
        if region is None:
            continue
        hits += 1
        x1, y1, x2, y2 = (int(v) for v in region)
        if mask[y1:y2, x1:x2].mean() > 64:
            overlaps += 1
    if hits == 0:
        pytest.skip("no duplication was detected in this sample")
    assert overlaps / hits >= 0.5, (
        f"only {overlaps}/{hits} highlighted regions landed on the duplicated area")


# --------------------------------------------------------------------- latency

@needs_cards
def test_tier_one_tampering_stays_inside_its_160ms_budget():
    """TECHNICAL-SPEC.md section 2, L5. The budget is a requirement."""
    image = next(sample_cards(1, seed=7))
    ctx = ctx_for("aadhaar", image=image)
    raw = mutate.as_jpeg(image)

    for _ in range(2):
        tamper.run(ctx, tier=1, uploaded=True, raw=raw)
    started = time.perf_counter()
    runs = 5
    for _ in range(runs):
        tamper.run(ctx, tier=1, uploaded=True, raw=raw)
    per_call_ms = (time.perf_counter() - started) * 1000 / runs
    assert per_call_ms < 160, f"tier 1 tampering took {per_call_ms:.0f} ms"


@needs_cards
def test_tier_two_tampering_stays_inside_its_600ms_budget():
    image = next(sample_cards(1, seed=8))
    ctx = ctx_for("aadhaar", image=image)

    tamper.run(ctx, tier=2)
    started = time.perf_counter()
    tamper.run(ctx, tier=2)
    per_call_ms = (time.perf_counter() - started) * 1000
    assert per_call_ms < 600, f"tier 2 tampering took {per_call_ms:.0f} ms"


# --------------------------------------------------------------- ghost portrait

HAVE_GENERATOR = True
try:
    # The generator imports Faker and Pillow *inside* its functions, to keep them
    # out of the screening path's import graph. So importing the module proves
    # nothing about whether it can run, and this probe used to pass in the
    # screening image - where those dependencies are deliberately absent - and
    # then fail at call time. Probe the dependency, not the module.
    import faker            # noqa: F401
    from PIL import Image   # noqa: F401
    from data.generator import build as build_document
except Exception:                                                # noqa: BLE001
    HAVE_GENERATOR = False

needs_generator = pytest.mark.skipif(
    not HAVE_GENERATOR,
    reason="build-time deps absent: pip install -r requirements-build.txt "
           "&& python scripts/fetch_fonts.py")


def boxes_of(doc):
    return {name: tuple(box) for name, *box in doc.labels}


@needs_generator
def test_a_genuine_ghost_portrait_matches_the_printed_photograph():
    """The ghost is the same photograph printed a second time, faded."""
    for doc_type in ("passport", "aadhaar"):
        doc = build_document(doc_type, seed=4)
        boxes = boxes_of(doc)
        agreement = physical.ghost_agreement(
            doc.image, boxes["person_photo"], boxes["ghost_photo"])
        assert agreement >= CFG["ghost_agreement_min"], (
            f"{doc_type} genuine ghost scored {agreement:.3f}")


@needs_generator
def test_swapping_the_portrait_and_leaving_the_ghost_is_caught():
    """The forgery this check exists for: a forger replaces the photograph and
    forgets the faded copy, leaving two different people on one page."""
    caught = 0
    for doc_type in ("passport", "aadhaar"):
        for seed in range(4):
            doc = build_document(doc_type, seed=seed)
            boxes = boxes_of(doc)
            forged, _mask = mutate.photo_swap(doc.image, seed=seed)
            agreement = physical.ghost_agreement(
                forged, boxes["person_photo"], boxes["ghost_photo"])
            if agreement < CFG["ghost_agreement_min"]:
                caught += 1
    assert caught == 8, f"only {caught}/8 portrait swaps were caught"


@needs_generator
def test_the_ghost_check_reports_a_verdict_through_the_module():
    doc = build_document("passport", seed=6)
    ctx = ctx_for("passport", image=doc.image, field_boxes=boxes_of(doc))
    signal = by_id(tamper.run(ctx))["tamper.physical.ghost_missing"]
    assert signal.verdict == "pass"
    assert signal.region is not None


def test_a_missing_ghost_is_a_failure_not_a_gap():
    """The detector found the main portrait on the same page and no ghost. On a
    document type that carries one, that is the finding, not an absence of one."""
    ctx = ctx_for("passport", field_boxes={"person_photo": (60, 80, 190, 240)})
    signal = by_id(tamper.run(ctx))["tamper.physical.ghost_missing"]
    assert signal.verdict == "fail"
    assert "none was found" in signal.evidence


def test_the_ghost_check_is_inconclusive_without_a_detector():
    """No field boxes means neither portrait was located. Saying so costs
    coverage, which is correct - it must not read as a clean document (D9)."""
    signal = by_id(tamper.run(ctx_for("passport")))["tamper.physical.ghost_missing"]
    assert signal.verdict == "inconclusive"
    assert "detector" in signal.evidence


def test_guilloche_is_blocked_by_measurement_not_by_a_missing_template():
    """D25's sibling. The template exists now - the generator draws real
    guilloche - so the old reason expired. It stays blocked because three
    formulations were measured and none separated a break from genuine
    variation, and that reason has to be the one the officer reads."""
    signal = by_id(tamper.run(ctx_for("passport")))["tamper.physical.guilloche_break"]
    assert signal.verdict == "inconclusive"
    assert "measured" in signal.evidence
    assert "template" not in signal.evidence.lower()
    assert "drawing" not in signal.evidence.lower()
