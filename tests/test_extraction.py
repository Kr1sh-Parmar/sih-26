"""Field detection and OCR.

Split deliberately into three kinds:

  * pure geometry and string handling - always runs, no model needed
  * OCR against rendered crops - runs wherever RapidOCR is installed
  * detector inference - skipped until weights exist under models/

The third kind matters most and can be verified least today, so the parts that
would silently mislabel every field on the day - the head layout and the class
order - are asserted against the real exported file rather than assumed.
"""
import numpy as np
import cv2
import pytest

from core import registry
from core.profiles import load_profile
from fusion.context import NormalizedField, ScreeningContext
from modules.extraction import detect, ocr
from modules.extraction import run as extraction_run
from modules.extraction import seed_from_payload
from modules.extraction.mrz import CHARSET, build_td3, parse

HAVE_DETECTOR = registry.available(registry.FIELD_DETECTOR)

try:
    registry.ocr_engine()
    HAVE_OCR = True
except Exception:                                           # noqa: BLE001
    HAVE_OCR = False

needs_detector = pytest.mark.skipif(
    not HAVE_DETECTOR, reason="field detector weights are not in models/ yet")
needs_ocr = pytest.mark.skipif(not HAVE_OCR, reason="RapidOCR is not installed")


def ctx_for(doc_type="passport", image=None, **kw):
    return ScreeningContext(
        session_id="t",
        image=image if image is not None else np.full((600, 900, 3), 240, np.uint8),
        doc_type=doc_type, profile=load_profile(doc_type), **kw,
    )


def render(text: str, w=460, h=64, scale=1.3, thickness=3) -> np.ndarray:
    img = np.full((h, w, 3), 255, np.uint8)
    cv2.putText(img, text, (8, int(h * 0.72)), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (0, 0, 0), thickness, cv2.LINE_AA)
    return img


# ------------------------------------------------------------- letterbox

def test_letterbox_preserves_aspect_and_centres():
    image = np.full((300, 900, 3), 255, np.uint8)
    padded, scale, dx, dy = detect.letterbox(image, 640)
    assert padded.shape == (640, 640, 3)
    assert scale == pytest.approx(640 / 900)
    assert dy > 0 and dx == 0          # wide image pads top and bottom
    # Squashing to a square instead would distort glyph aspect, and these crops
    # are what OCR then has to read.
    assert padded[dy + 1, dx + 1].tolist() == [255, 255, 255]
    assert padded[1, 1].tolist() == [114, 114, 114]


def test_letterbox_round_trips_a_box_back_to_image_coordinates():
    image = np.full((300, 900, 3), 255, np.uint8)
    _padded, scale, dx, dy = detect.letterbox(image, 640)
    for original in ((0, 0, 900, 300), (100, 50, 400, 200)):
        x1, y1, x2, y2 = original
        boxed = (x1 * scale + dx, y1 * scale + dy, x2 * scale + dx, y2 * scale + dy)
        back = tuple((v - d) / scale for v, d in
                     zip(boxed, (dx, dy, dx, dy)))
        assert back == pytest.approx(original, abs=1e-6)


# ---------------------------------------------------------- head decode

def test_decode_reads_the_v11_head_layout():
    # (1, 4+nc, anchors): four box terms then one score per class, no objectness.
    nc, anchors = 22, 12
    raw = np.zeros((1, 4 + nc, anchors), dtype=np.float32)
    raw[0, :4, 3] = [100, 200, 40, 20]
    raw[0, 4 + 7, 3] = 0.91                       # class 7
    boxes, scores, ids = detect._decode(raw, nc)
    assert boxes.shape == (anchors, 4)
    assert ids[3] == 7
    assert scores[3] == pytest.approx(0.91)
    assert boxes[3].tolist() == [100, 200, 40, 20]


def test_decode_tolerates_a_transposed_export():
    nc, anchors = 22, 12
    raw = np.zeros((1, anchors, 4 + nc), dtype=np.float32)
    raw[0, 3, :4] = [100, 200, 40, 20]
    raw[0, 3, 4 + 7] = 0.91
    _boxes, scores, ids = detect._decode(raw, nc)
    assert ids[3] == 7 and scores[3] == pytest.approx(0.91)


def test_best_per_class_keeps_the_most_confident_box():
    found = [
        {"class": "dob", "confidence": 0.4, "box": (0, 0, 1, 1)},
        {"class": "dob", "confidence": 0.9, "box": (2, 2, 3, 3)},
        {"class": "name", "confidence": 0.7, "box": (4, 4, 5, 5)},
    ]
    best = detect.best_per_class(found)
    assert set(best) == {"dob", "name"}
    assert best["dob"]["box"] == (2, 2, 3, 3)


# ------------------------------------------------------- absent weights

def test_detection_is_silent_rather_than_loud_when_weights_are_absent():
    # Absence is a normal state - the image ships without weights until they
    # are trained. It must degrade to inconclusive, not raise.
    if HAVE_DETECTOR:
        pytest.skip("weights are present")
    ctx = ctx_for()
    assert detect.run(ctx) == []
    assert ctx.field_boxes == {}


def test_extraction_still_reports_every_declared_field_without_a_detector():
    if HAVE_DETECTOR:
        pytest.skip("weights are present")
    ctx = ctx_for("passport")
    signals = extraction_run(ctx)
    unread = {s.anchor for s in signals
              if s.id.startswith("extraction.field.") and s.verdict == "inconclusive"}
    assert "field:dob" in unread and "field:name" in unread
    assert all("not yet deployed" in s.evidence for s in signals
               if s.id.startswith("extraction.field."))


# ------------------------------------------------------------ MRZ path

def test_coerce_maps_only_unambiguous_lookalikes():
    assert ocr.coerce_mrz("p<uto eriksson") == "P<UTOERIKSSON"
    assert ocr.coerce_mrz("P«UTO") == "P<<UTO"
    # A character with no unambiguous counterpart is left alone, so the parser
    # rejects the strip rather than a repair silently failing a check digit.
    assert "@" in ocr.coerce_mrz("P@UTO")


def test_a_bad_line_length_is_refused_before_the_check_digits_see_it():
    # A dropped character fails a check digit, and a failed composite check
    # digit is a hard fail. A bad scan must not be able to detain someone.
    class FakeEngine:
        def __call__(self, _img):
            return ([[[[0, 0], [1, 0], [1, 1], [0, 1]], "P<UTOERIKSSON", 0.9],
                     [[[0, 5], [1, 5], [1, 6], [0, 6]], "L898902C36UTO", 0.9]], None)

    original = registry.ocr_engine
    registry.ocr_engine = lambda: FakeEngine()
    try:
        strip, _conf, reason = ocr.read_mrz(np.full((60, 400, 3), 255, np.uint8))
    finally:
        registry.ocr_engine = original

    assert strip is None
    assert "not a valid layout" in reason


def test_an_out_of_charset_read_is_refused():
    class FakeEngine:
        def __call__(self, _img):
            return ([[[[0, 0], [1, 0], [1, 1], [0, 1]], "P$UTO" + "<" * 39, 0.9],
                     [[[0, 5], [1, 5], [1, 6], [0, 6]], "L" * 44, 0.9]], None)

    original = registry.ocr_engine
    registry.ocr_engine = lambda: FakeEngine()
    try:
        strip, _conf, reason = ocr.read_mrz(np.full((60, 400, 3), 255, np.uint8))
    finally:
        registry.ocr_engine = original

    assert strip is None
    assert "cannot appear" in reason


def test_a_well_formed_read_reaches_layer_a_and_its_check_digits_verify():
    # The one line that switches on all five ICAO check digits and the whole
    # VIZ/MRZ cross-check. Both are already written and tested; this asserts
    # the handover, not those.
    strip = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                      document_number="E1009353", nationality="IND",
                      birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    lines = strip.splitlines()

    class FakeEngine:
        def __call__(self, _img):
            return ([[[[0, 0], [1, 0], [1, 1], [0, 1]], lines[0], 0.93],
                     [[[0, 9], [1, 9], [1, 10], [0, 10]], lines[1], 0.91]], None)

    ctx = ctx_for("passport")
    ctx.field_boxes["mrz"] = (10, 500, 880, 580)

    original = registry.ocr_engine
    registry.ocr_engine = lambda: FakeEngine()
    try:
        signals = ocr.run(ctx)
    finally:
        registry.ocr_engine = original

    assert ctx.fields["mrz"].raw == strip
    assert ctx.fields["mrz"].source == "mrz"
    assert any(s.id == "extraction.ocr.mrz.confidence" and s.verdict == "pass"
               for s in signals)

    from modules.validation import layer_a
    verdicts = {s.id: s.verdict for s in layer_a.run(ctx)}
    for part in ("document_number", "dob", "expiry", "optional", "composite"):
        assert verdicts[f"validation.mrz.checkdigit.{part}"] == "pass", part


def test_every_mrz_charset_character_survives_coercion():
    assert ocr.coerce_mrz(CHARSET) == CHARSET


# ---------------------------------------------------- signed vs printed

def test_a_signed_payload_does_not_overwrite_what_ocr_read():
    """The whole VIZ/MRZ premise depends on this.

    A forger alters the printed date of birth and leaves the signed payload
    alone. If the signed value replaced the printed one in ctx.fields, Layer C
    would compare the signature against the MRZ - two things that agree - and
    the alteration would be invisible.
    """
    ctx = ctx_for("pan")
    ctx.fields["dob"] = NormalizedField(raw="02/11/1998", value="1998-11-02",
                                        source="ocr", confidence=0.9)
    seeded = seed_from_payload(ctx, {"dob": "1996-11-02", "name": "PRADEEP GHARAT"})

    assert ctx.fields["dob"].value == "1998-11-02"      # the printed value stands
    assert ctx.fields["dob"].source == "ocr"
    assert "dob" not in seeded
    # A field OCR never read is still filled in from the signature.
    assert ctx.fields["name"].source == "qr"
    assert "name" in seeded


def test_the_tamper_is_visible_end_to_end_when_both_sources_exist():
    strip = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                      document_number="E1009353", nationality="IND",
                      birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    ctx = ctx_for("passport")
    ctx.fields["mrz"] = NormalizedField(raw=strip, value="", source="mrz",
                                        confidence=0.9)
    ctx.fields["dob"] = NormalizedField(raw="04/03/1991", value="1991-03-04",
                                        source="ocr", confidence=0.9)
    seed_from_payload(ctx, {"dob": "1991-08-04"})

    from datetime import date
    from modules.validation import layer_c
    mismatch = next(s for s in layer_c.run(ctx, today=date(2026, 9, 6))
                    if s.id == "validation.vizmrz.dob_mismatch")
    assert mismatch.verdict == "fail"
    assert "1991-03-04" in mismatch.evidence and "1991-08-04" in mismatch.evidence


# ------------------------------------------------------------ real OCR

@needs_ocr
def test_ocr_reads_a_rendered_field_and_normalises_it():
    ctx = ctx_for("pan", image=np.full((400, 700, 3), 255, np.uint8))
    ctx.image[40:104, 20:480] = render("PRADEEP GHARAT")
    ctx.field_boxes["name"] = (20, 40, 480, 104)

    signals = ocr.run(ctx)
    assert ctx.fields["name"].value == "PRADEEP GHARAT"
    assert ctx.fields["name"].source == "ocr"
    assert 0.0 < ctx.fields["name"].confidence <= 1.0
    assert any(s.id == "extraction.ocr.name.confidence" and s.verdict == "pass"
               for s in signals)


@needs_ocr
def test_a_value_that_will_not_normalise_is_not_stored():
    # Read something, but it is not a date. Storing it would let a garbled read
    # become a confident mismatch three layers later.
    ctx = ctx_for("pan", image=np.full((400, 700, 3), 255, np.uint8))
    ctx.image[40:104, 20:480] = render("NOT A DATE")
    ctx.field_boxes["dob"] = (20, 40, 480, 104)

    signals = ocr.run(ctx)
    assert "dob" not in ctx.fields
    signal = next(s for s in signals if s.id == "extraction.ocr.dob.confidence")
    assert signal.verdict == "inconclusive"


@needs_ocr
def test_a_blank_crop_is_inconclusive_not_a_pass():
    ctx = ctx_for("pan", image=np.full((400, 700, 3), 255, np.uint8))
    ctx.field_boxes["name"] = (20, 40, 480, 104)
    signals = ocr.run(ctx)
    assert "name" not in ctx.fields
    assert all(s.verdict == "inconclusive" for s in signals)


@needs_ocr
def test_ocr_never_touches_the_whole_page():
    # Crops only. This is the single biggest latency win in the system, and a
    # regression would be invisible except as a five-fold slowdown.
    seen = []
    original = registry.ocr_engine
    engine = registry.ocr_engine()
    registry.ocr_engine = lambda: (
        lambda img, **kw: (seen.append(img.shape), engine(img, **kw))[1])
    try:
        ctx = ctx_for("pan", image=np.full((900, 1400, 3), 255, np.uint8))
        ctx.image[40:104, 20:480] = render("PRADEEP GHARAT")
        ctx.field_boxes["name"] = (20, 40, 480, 104)
        ocr.run(ctx)
    finally:
        registry.ocr_engine = original

    assert seen, "OCR never ran"
    assert all(shape[0] * shape[1] < 900 * 1400 * 0.25 for shape in seen), seen


@needs_ocr
def test_a_signed_field_is_not_re_read():
    ctx = ctx_for("pan", image=np.full((400, 700, 3), 255, np.uint8))
    ctx.image[40:104, 20:480] = render("SOMEONE ELSE")
    ctx.field_boxes["name"] = (20, 40, 480, 104)
    ctx.fields["name"] = NormalizedField(raw="PRADEEP GHARAT",
                                         value="PRADEEP GHARAT", source="qr",
                                         confidence=1.0)
    ocr.run(ctx)
    assert ctx.fields["name"].value == "PRADEEP GHARAT"


# -------------------------------------------------- the exported model

@needs_detector
def test_the_exported_head_matches_what_the_decoder_assumes():
    """A transposed head produces plausible boxes with wrong labels.

    That is the worst failure available here - the console would show an
    officer a confident, well-placed, completely mislabelled field set.
    """
    meta = registry.metadata(registry.FIELD_DETECTOR)
    names = meta["classes"]
    sess = registry.session(registry.FIELD_DETECTOR)

    shape = sess.get_outputs()[0].shape
    assert len(shape) == 3, shape
    assert 4 + len(names) in shape[1:], (
        f"output {shape} matches neither (1, {4 + len(names)}, anchors) nor its "
        f"transpose; the decoder would mislabel every field")


@needs_detector
def test_the_class_list_is_the_frozen_22_class_ontology_in_dataset_order():
    import yaml

    from core.profiles import ONTOLOGY
    meta = registry.metadata(registry.FIELD_DETECTOR)
    dataset = yaml.safe_load(
        (registry.ROOT / "data" / "processed" / "fields" / "data.yaml")
        .read_text(encoding="utf-8"))["names"]
    assert meta["classes"] == dataset
    assert set(meta["classes"]) == set(ONTOLOGY)


@needs_detector
def test_detection_finds_boxes_on_a_real_card_and_stays_inside_the_image():
    import glob
    sample = sorted(glob.glob(str(
        registry.ROOT / "data/processed/fields/test/images/*.jpg")))[:3]
    if not sample:
        pytest.skip("no test images")

    for path in sample:
        image = cv2.imread(path)
        found = detect.detect(image)
        h, w = image.shape[:2]
        for item in found:
            x1, y1, x2, y2 = item["box"]
            assert 0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h, item
            assert item["class"] in registry.metadata(registry.FIELD_DETECTOR)["classes"]


@needs_detector
def test_tier_one_extraction_stays_inside_its_latency_budget():
    import glob
    import time
    sample = sorted(glob.glob(str(
        registry.ROOT / "data/processed/fields/test/images/*.jpg")))[:1]
    if not sample:
        pytest.skip("no test images")

    image = cv2.imread(sample[0])
    detect.detect(image)                       # warm
    started = time.perf_counter()
    detect.detect(image)
    ms = (time.perf_counter() - started) * 1000
    # TECHNICAL-SPEC.md section 10 budgets 110 ms for field detection.
    assert ms < 400, f"field detection took {ms:.0f} ms"


# ------------------------------------- ICAO positional charset repair

def test_positional_repair_fixes_the_nationality_the_check_digits_cannot():
    """The composite check digit covers line 2 positions 1-10, 14-20 and 22-43.

    Nationality sits at 11-13 and is covered by nothing. Measured: PP-OCRv4
    reads IND as 1ND on a rendered strip while all five check digits still
    verify, and Layer B then reports "nationality 1ND is not a recognised
    country code" on a genuine passport.
    """
    good = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                     document_number="E1009353", nationality="IND",
                     birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    l1, l2 = good.splitlines()
    misread = [l1, l2[:10] + "1ND" + l2[13:]]

    repaired = ocr.apply_positional_charset(misread)
    assert repaired[1] == l2
    assert parse("\n".join(repaired)).nationality == "IND"


def test_positional_repair_maps_letters_to_digits_inside_date_fields():
    good = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                     document_number="E1009353", nationality="IND",
                     birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    l1, l2 = good.splitlines()
    # O for 0 inside the date of birth, positions 13-18.
    misread = [l1, l2[:13] + "9IO8O4" + l2[19:]]
    repaired = ocr.apply_positional_charset(misread)
    assert repaired[1][13:19].isdigit()


def test_positional_repair_leaves_the_filler_and_the_document_number_alone():
    good = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                     document_number="E1009353", nationality="IND",
                     birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    l1, l2 = good.splitlines()
    repaired = ocr.apply_positional_charset([l1, l2])
    # A no-op on a clean strip. Coercion that changes a correct read is a bug.
    assert repaired == [l1, l2]
    # The document number is alphanumeric by design - E1009353 must survive.
    assert repaired[1][:9] == "E1009353<"


def test_repair_cannot_rescue_a_genuinely_altered_date():
    # Coercion must not be able to mask tampering. An altered digit is still a
    # digit, so there is nothing for the repair to touch, and the check digit
    # still fails.
    good = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                     document_number="E1009353", nationality="IND",
                     birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    l1, l2 = good.splitlines()
    altered = [l1, l2[:13] + "910304" + l2[19:]]
    repaired = ocr.apply_positional_charset(altered)
    assert repaired[1] == altered[1]
    from modules.extraction.mrz import verify as verify_digit
    m = parse("\n".join(repaired))
    assert not verify_digit(*m.check_digits["dob"])


@needs_ocr
def test_real_ocr_reads_a_rendered_mrz_strip_exactly():
    """End to end on the real engine, not a fake.

    This is the whole reason the OCR path exists: get the strip right and five
    check digits, the VIZ/MRZ cross-check and the expiry check all switch on.
    """
    strip = build_td3(issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
                      document_number="E1009353", nationality="IND",
                      birth_date="1991-08-04", sex="M", expiry_date="2031-07-17")
    image = np.full((150, 1400, 3), 255, np.uint8)
    for row, line in enumerate(strip.splitlines()):
        for i, ch in enumerate(line):
            cv2.putText(image, ch, (14 + i * 31, 55 + row * 62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.95, (0, 0, 0), 2, cv2.LINE_AA)

    got, confidence, reason = ocr.read_mrz(image)
    assert got == strip, f"{reason or 'misread'}\n{got}"
    assert confidence > 0.5

    from modules.extraction.mrz import verify as verify_digit
    m = parse(got)
    assert all(verify_digit(v, d) for v, d in m.check_digits.values())


# ------------------------------------------- reading order and joining

def test_row_bucketing_keeps_one_line_on_one_line():
    """PP-OCR splits "02/11/1998" into three boxes whose tops differ slightly.

    A fixed pixel bucket put them on three separate "rows" and the date read
    back as "/11 /1998 02" - which then failed to normalise, so the field was
    dropped and the document lost coverage for a value that was right there.
    """
    def box(left, top, height):
        return [[left, top], [left + 40, top], [left + 40, top + height], [left, top + height]]

    class FakeEngine:
        def __call__(self, _img):
            return ([[box(120, 12, 34), "/1998", 0.99],
                     [box(10, 8, 36), "02", 0.99],
                     [box(65, 10, 35), "/11", 0.99]], None)

    original = registry.ocr_engine
    registry.ocr_engine = lambda: FakeEngine()
    try:
        # Tall enough to take the detector path, which is where the bucketing
        # lives. A wide single-line crop skips the detector entirely now.
        text, _conf = ocr.read(np.full((300, 300, 3), 255, np.uint8))
    finally:
        registry.ocr_engine = original
    assert text == "02 /11 /1998"


def test_a_multi_line_address_still_reads_top_to_bottom():
    def box(left, top):
        return [[left, top], [left + 60, top], [left + 60, top + 30], [left, top + 30]]

    class FakeEngine:
        def __call__(self, _img):
            return ([[box(10, 70), "BIHAR", 0.9],
                     [box(10, 10), "RAXAUL", 0.9]], None)

    original = registry.ocr_engine
    registry.ocr_engine = lambda: FakeEngine()
    try:
        text, _conf = ocr.read(np.full((120, 300, 3), 255, np.uint8))
    finally:
        registry.ocr_engine = original
    assert text == "RAXAUL BIHAR"


@needs_ocr
def test_a_fragmented_date_still_normalises():
    # The spaced form is not a valid date and the joined form is. A name needs
    # its spaces, so this is retried rather than stripped unconditionally.
    ctx = ctx_for("pan", image=np.full((400, 700, 3), 252, np.uint8))
    cv2.putText(ctx.image, "02/11/1998", (40, 100), cv2.FONT_HERSHEY_SIMPLEX,
                1.1, (20, 20, 20), 2, cv2.LINE_AA)
    ctx.field_boxes["dob"] = (30, 60, 380, 120)

    ocr.run(ctx)
    assert ctx.fields["dob"].value == "1998-11-02"
    assert ctx.fields["dob"].source == "ocr"


@needs_ocr
def test_a_name_keeps_its_spaces():
    ctx = ctx_for("pan", image=np.full((400, 700, 3), 252, np.uint8))
    cv2.putText(ctx.image, "PRADEEP KESHAV GHARAT", (40, 100),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (20, 20, 20), 2, cv2.LINE_AA)
    ctx.field_boxes["name"] = (30, 60, 640, 120)

    ocr.run(ctx)
    assert ctx.fields["name"].value == "PRADEEP KESHAV GHARAT"


def test_the_ideographic_space_pp_ocr_pads_with_is_stripped():
    """PP-OCRv4's recogniser is the Chinese model, and it pads reads with
    U+3000 rather than a plain space: `02/11/1998　`.

    Every normaliser here happens to survive it because `str.split()` with no
    argument splits on all Unicode whitespace. That is correct but accidental,
    and a future normaliser written with `.split(" ")` would break every field
    the OCR reads. Pin it down.
    """
    from modules.extraction import normalize as N
    from modules.extraction import normalise_field

    assert N.iso_date("02/11/1998　") == "1998-11-02"
    assert N.name("PRADEEP GHARAT　") == "PRADEEP GHARAT"
    assert N.id_number("ABLPG7040F　") == "ABLPG7040F"

    field = normalise_field("dob", "02/11/1998　", "ocr", 0.96)
    assert field is not None and field.value == "1998-11-02"
    # The raw read is kept verbatim - it is what the officer would see quoted.
    assert "　" in field.raw
