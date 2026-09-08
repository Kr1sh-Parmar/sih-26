"""The synthetic document generator.

`CLAUDE.md` rule 4 says every document image comes from `data/generator/`. That
puts the generator on the critical path for the training set, the forgery set
and three of the five demo scenes, so what is asserted here is that the
documents are **valid under the system's own checks**, not that they look nice:

  * every number passes the function Layer A validates it with;
  * the MRZ parses and all five ICAO check digits verify;
  * the signed payload verifies through the real trust anchor store;
  * every field drawn has a label, and the labels are usable as YOLO training data.

The generator is build-time tooling, so its dependencies - Pillow, Faker, the
Noto fonts - are not in the screening image. These tests skip when they are
absent rather than failing a clean checkout, the same way the detector and face
tests do.
"""
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data" / "templates" / "fonts"

try:
    import PIL  # noqa: F401
    import faker  # noqa: F401
    HAVE_DEPS = True
except ImportError:                                              # pragma: no cover
    HAVE_DEPS = False

HAVE_FONTS = (FONTS / "NotoSans-Regular.ttf").exists()

needs_generator = pytest.mark.skipif(
    not (HAVE_DEPS and HAVE_FONTS),
    reason="build-time deps absent: pip install -r requirements-build.txt "
           "&& python scripts/fetch_fonts.py")

pytestmark = needs_generator

if HAVE_DEPS:
    from data.generator import DOC_TYPES, build, session
    from data.generator import identity as I
    from data.generator import render
    from data.generator.render import ONTOLOGY, load_template
    from modules.extraction import mrz
    from modules.validation.checksums import (check_aadhaar, check_dl,
                                              check_epic, check_pan)


# ------------------------------------------------------------------ identities

@pytest.mark.parametrize("seed", [0, 1, 7, 42, 99])
def test_every_number_passes_the_check_that_guards_it(seed):
    """The generator uses the same functions Layer A validates with.

    If it computed its own check digits and the two ever disagreed, every
    generated document would be quietly invalid and the validation tests would
    still pass - because they would be testing the same bug twice.
    """
    who = I.build(seed)
    for ok, detail in (check_aadhaar(who.aadhaar),
                       check_pan(who.pan, who.surname),
                       check_epic(who.epic),
                       check_dl(who.dl)):
        assert ok, detail


def test_the_pan_fifth_character_really_is_the_surname_initial():
    """Not incidentally true - it is the published rule Layer A enforces."""
    for seed in range(20):
        who = I.build(seed)
        assert who.pan[4] == who.surname[0], f"{who.pan} vs {who.surname}"


def test_the_mrz_parses_and_every_check_digit_verifies():
    for seed in (2, 13, 77):
        who = I.build(seed)
        parsed = mrz.parse(who.mrz())
        assert parsed.birth_date == who.dob
        assert parsed.expiry_date == who.expiry_date
        assert parsed.surname == who.surname
        assert parsed.document_number == who.passport_number
        assert len(parsed.check_digits) == 5, parsed.check_digits
        for name, (value, digit) in parsed.check_digits.items():
            assert mrz.verify(value, digit), f"{name} does not verify"


def test_an_identity_is_reproducible_from_its_seed():
    """Tests assert about documents; they can only do that if the same seed
    gives the same person every time."""
    a, b = I.build(31), I.build(31)
    assert (a.aadhaar, a.pan, a.dob, a.name) == (b.aadhaar, b.pan, b.dob, b.name)
    assert I.build(32).aadhaar != a.aadhaar


# -------------------------------------------------------------------- rendering

@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_every_template_names_only_frozen_ontology_classes(doc_type):
    """A template naming a new class is a bug, not a new class."""
    spec = load_template(doc_type)
    for item in spec["fields"]:
        assert item["class"] in ONTOLOGY, item["class"]


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_every_drawn_field_has_a_label_inside_the_image(doc_type):
    """The labels are the whole reason this is code rather than vector art."""
    doc = build(doc_type, seed=5)
    w, h = doc.size
    assert doc.labels, f"{doc_type} drew nothing"
    for name, x1, y1, x2, y2 in doc.labels:
        assert name in ONTOLOGY
        assert 0 <= x1 < x2 <= w, f"{name} box {x1}-{x2} outside width {w}"
        assert 0 <= y1 < y2 <= h, f"{name} box {y1}-{y2} outside height {h}"


@pytest.mark.parametrize("doc_type", DOC_TYPES)
def test_yolo_labels_are_normalised_and_in_range(doc_type):
    for line in build(doc_type, seed=6).yolo_labels():
        index, cx, cy, bw, bh = line.split()
        assert 0 <= int(index) < len(ONTOLOGY)
        for value in (float(cx), float(cy), float(bw), float(bh)):
            assert 0.0 <= value <= 1.0, line


def test_the_four_classes_with_no_real_instances_are_now_drawn():
    """`ghost_photo`, `barcode`, `hologram` and `doc_title` have zero instances
    in the scraped set (data/TRAINING.md), which is why the detector cannot
    learn them. This is the gap the generator exists to close."""
    drawn = set()
    for doc_type in DOC_TYPES:
        drawn |= {name for name, *_ in build(doc_type, seed=3).labels}
    for missing in ("ghost_photo", "barcode", "hologram", "doc_title"):
        assert missing in drawn, missing


def test_the_same_seed_draws_the_same_document():
    a, b = build("aadhaar", seed=8), build("aadhaar", seed=8)
    assert np.array_equal(a.image, b.image)


def test_devanagari_actually_renders_rather_than_falling_back_to_boxes():
    """Noto Sans Devanagari covers U+0900-097F and no Latin at all, so a
    bilingual label drawn wholly in it renders the English half as tofu. The
    renderer splits by script; this checks the split still happens."""
    from data.generator.render import _runs
    runs = _runs("नाम / Name")
    assert [deva for _segment, deva in runs] == [True, False]
    assert "".join(segment for segment, _d in runs) == "नाम / Name"


# ------------------------------------------------------------------- signatures

def _anchors():
    from core.store import Store
    return Store(ROOT / "var" / "screening.db").trust_anchors()


@pytest.mark.skipif(not (ROOT / "var" / "issuer" / "SIH-REF-01.key").exists(),
                    reason="no issuer key; run python -m issuer.cli init")
def test_a_signed_document_verifies_through_the_real_trust_store():
    from core.trust import verify_payload
    doc = build("aadhaar", seed=9, sign=True)
    result = verify_payload(doc.envelope, _anchors())
    assert result.ok, result.state
    assert result.is_reference, "the reference issuer must not look governmental"
    assert result.payload["dob"] == doc.identity.dob
    assert result.payload["id_number"] == doc.identity.aadhaar


# --------------------------------------------------------------------- sessions

@pytest.mark.skipif(not (ROOT / "var" / "issuer" / "SIH-REF-01.key").exists(),
                    reason="no issuer key; run python -m issuer.cli init")
def test_a_session_puts_one_persons_face_on_all_their_documents():
    """The bug this caught: the portrait was picked from the render seed, so
    one identity's Aadhaar and PAN carried two different faces. Scene 3 puts
    them side by side, so an officer would have seen two different people and
    the face module would have flagged a generator artefact as a mismatch."""
    import cv2
    docs = session(seed=11, disagree_on="dob")
    crops = []
    for doc in docs:
        box = next(b for name, *b in doc.labels if name == "person_photo")
        x1, y1, x2, y2 = box
        crops.append(cv2.resize(doc.image[y1:y2, x1:x2], (96, 96)))
    difference = np.abs(crops[0].astype(int) - crops[1].astype(int)).mean()
    assert difference < 12, f"different faces on one person's documents ({difference:.0f})"


def test_a_named_portrait_lands_on_the_card_and_a_missing_one_is_loud():
    """What makes the doc-vs-live calibration set obtainable at all.

    A volunteer's own government ID may never be used (CLAUDE.md rule 4), so
    the document half of a pair is their photograph rendered onto a synthetic
    card, printed and scanned. Before `portrait_path` the generator could only
    pick from the SFHQ pool by seed, so there was no way to put a specific
    person on a specific card - which quietly blocked the whole session.

    The missing-file case raises rather than falling back to the pool. A silent
    fallback would pair one volunteer's document with a stranger's face, and a
    genuine pair scored as an impostor pair drags the threshold *down* - making
    the system more willing to accept a stranger. Nothing downstream can see
    that happen.
    """
    import cv2
    pool = render.faces()
    if len(pool) < 2:
        pytest.skip("no face pool; run python data/tools/pull_faces.py")

    def card(portrait):
        who = I.build(seed=3)
        who.extras["face_seed"] = 0          # pool face 0, deliberately not ours
        if portrait is not None:
            who.extras["portrait_path"] = str(portrait)
        return render.render("aadhaar", who)

    def photo_on(doc):
        box = next(b for name, *b in doc.labels if name == "person_photo")
        x1, y1, x2, y2 = box
        page = np.array(doc.image.convert("RGB"))    # render() yields PIL
        return cv2.resize(page[y1:y2, x1:x2], (96, 96)).astype(int)

    chosen = pool[7 % len(pool)]
    named = photo_on(card(chosen))
    pooled = photo_on(card(None))
    assert np.abs(named - pooled).mean() > 12, (
        "portrait_path was ignored - the card still shows the pool face"
    )

    with pytest.raises(FileNotFoundError):
        card(ROOT / "data" / "raw" / "faces" / "__no_such_volunteer__.jpg")


@pytest.mark.skipif(not (ROOT / "var" / "issuer" / "SIH-REF-01.key").exists(),
                    reason="no issuer key; run python -m issuer.cli init")
def test_a_disagreeing_session_is_signed_on_one_side_only():
    """Scene 3: the signed document's payload is proven, and the unsigned one
    contradicts it. Both halves have to be true or the demo is a coincidence."""
    docs = session(seed=12, disagree_on="dob")
    signed, unsigned = docs[0], docs[1]
    assert signed.envelope, "the propagating document must actually be signed"
    assert not unsigned.envelope
    assert signed.identity.dob != unsigned.identity.dob
    assert signed.identity.name == unsigned.identity.name, (
        "only the date of birth should differ; a different name is a different case")


# --------------------------------------------------------- against the pipeline

def test_a_generated_document_decodes_and_screens():
    """The generator is only worth anything if the real pipeline can read it."""
    import cv2

    from api import router as pipeline
    from core.store import Store

    doc = build("passport", seed=14)
    raw = cv2.imencode(".png", doc.image)[1].tobytes()
    ctx = pipeline.build_context(raw, "passport", "generated")

    verdict = None
    for event in pipeline.screen(ctx, store=Store(":memory:")):
        if event.type == "verdict":
            verdict = event.payload
    assert verdict is not None
    assert verdict["band"] in ("GREEN", "AMBER", "RED")


def test_a_mutated_generated_document_is_caught_by_the_tamper_module():
    """The forgery set and the tamper module have to meet somewhere."""
    from core.profiles import load_config
    from data.tools import mutate
    from modules.tamper import digital

    doc = build("aadhaar", seed=15)
    forged, mask = mutate.copy_move(doc.image, seed=2)
    _count, region = digital.copy_move(forged, load_config("thresholds")["tamper"])
    if region is None:
        pytest.skip("this mutation was not detected; the rate is in data/TAMPERING.md")
    x1, y1, x2, y2 = (int(v) for v in region)
    assert mask[y1:y2, x1:x2].mean() > 32, "the region did not land on the edit"


# ------------------------------------------------------------ layout agreement

def test_generated_layouts_agree_with_the_measured_reference():
    """Templates are hand-written, so they can drift from what real cards do.

    Checked against `config/layout/*.json` - the medians measured over labelled
    genuine cards - only where that reference is worth believing: at least 50
    source cards and a spread under a fifth of the page. Passport `mrz` has a
    median absolute deviation of half the page and is excluded by that rule,
    which is the rule doing its job rather than an exception to it.
    """
    from modules.tamper.physical import MIN_REFERENCE_CARDS, layout_reference

    checked = drifted = 0
    for doc_type in DOC_TYPES:
        reference = layout_reference(doc_type)
        if reference is None:
            continue
        doc = build(doc_type, seed=4)
        w, h = doc.size
        for name, x1, y1, x2, y2 in doc.labels:
            stats = reference["fields"].get(name)
            if not stats or stats["n"] < MIN_REFERENCE_CARDS:
                continue
            if max(stats["mad_x"], stats["mad_y"]) > 0.20:
                continue
            checked += 1
            cx, cy = ((x1 + x2) / 2) / w, ((y1 + y2) / 2) / h
            zx = abs(cx - stats["cx"]) / max(stats["mad_x"], 0.01)
            zy = abs(cy - stats["cy"]) / max(stats["mad_y"], 0.01)
            if max(zx, zy) > 12:
                drifted += 1

    assert checked >= 5, f"only {checked} fields had a usable reference"
    assert drifted / checked < 0.5, (
        f"{drifted}/{checked} generated fields sit far from where real cards "
        f"put them - the templates have drifted")
