"""The checksum ratifier - the mandatory gate on VLM output.

The property that matters is not that good reads get through; it is that a read
which fails its own arithmetic check **never reaches `ctx.fields`**. Layer C
compares the printed value against the MRZ and Layer D compares it against a
signed sibling, so a value already known to be wrong does not sit there
inertly - it manufactures mismatches in the two checks the whole system is sold
on.

Fixtures are real generated documents where the deps allow it, so the numbers
being ratified are the same ones Layer A would validate.
"""
import numpy as np
import pytest

from core.profiles import load_profile, reliability, weight_for
from fusion.context import NormalizedField, ScreeningContext
from fusion.findings import build_findings
from fusion.score import score
from modules.extraction import ratify
from modules.extraction.mrz import build_td3
from modules.validation.checksums import verhoeff_digit

try:
    # The generator imports Faker and Pillow *inside* its functions, to keep them
    # out of the screening path's import graph. So importing the module proves
    # nothing about whether it can run, and this probe used to pass in the
    # screening image - where those dependencies are deliberately absent - and
    # then fail at call time. Probe the dependency, not the module.
    import faker            # noqa: F401
    from PIL import Image   # noqa: F401
    from data.generator import build as build_doc
    from data.generator.identity import build as build_identity
    HAVE_GENERATOR = True
except Exception:                                            # noqa: BLE001
    HAVE_GENERATOR = False

needs_generator = pytest.mark.skipif(
    not HAVE_GENERATOR,
    reason="build-time deps absent: pip install -r requirements-build.txt")


def ctx_for(doc_type="aadhaar", **kw):
    return ScreeningContext(
        session_id="t", image=np.zeros((10, 10, 3), np.uint8),
        doc_type=doc_type, profile=load_profile(doc_type), **kw)


def by_id(signals):
    return {s.id: s for s in signals}


def valid_aadhaar(payload="23456789012"):
    return payload[:11] + verhoeff_digit(payload[:11])


# ------------------------------------------------------------- the hard rule

def test_a_read_that_fails_its_checksum_is_never_stored():
    """The whole point. A known-wrong value in ctx.fields is not inert - Layer C
    and Layer D compare against it and produce confident mismatches."""
    ctx = ctx_for("aadhaar")
    number = valid_aadhaar()
    corrupted = number[:-1] + str((int(number[-1]) + 1) % 10)

    signals = by_id(ratify.ratify(ctx, {"id_number": corrupted}))
    assert "id_number" not in ctx.fields, "a rejected value reached ctx.fields"
    assert signals["extraction.vlm.ratified"].verdict == "fail"
    assert "discarded" in signals["extraction.vlm.ratified"].evidence


def test_a_read_that_passes_its_checksum_is_stored_as_arithmetic():
    ctx = ctx_for("aadhaar")
    signals = by_id(ratify.ratify(ctx, {"id_number": valid_aadhaar()}))

    assert ctx.fields["id_number"].source == "vlm"
    ratified = signals["extraction.vlm.ratified"]
    assert ratified.verdict == "pass"
    assert ratified.trust_class == "arithmetic", (
        "a value the document itself confirms is not probabilistic")


def test_a_field_with_no_checksum_is_stored_but_unverified():
    ctx = ctx_for("aadhaar")
    signals = by_id(ratify.ratify(ctx, {"name": "PRADEEP GHARAT",
                                        "dob": "1991-08-04"}))
    assert ctx.fields["name"].value == "PRADEEP GHARAT"
    unratified = signals["extraction.vlm.unratified"]
    assert unratified.verdict == "inconclusive"
    assert unratified.trust_class == "unverified"


def test_unratified_output_alone_cannot_produce_green():
    """`force MANUAL_REVIEW` from the spec, through the coverage floor rather
    than through a new mechanism."""
    ctx = ctx_for("aadhaar")
    signals = ratify.ratify(ctx, {"name": "PRADEEP GHARAT"})
    verdict = score(signals, ctx.profile, build_findings(signals))
    assert verdict.band != "GREEN"


# ------------------------------------------------------- per document type

@needs_generator
@pytest.mark.parametrize("doc_type", ["aadhaar", "pan", "voter_id", "dl"])
def test_a_generated_number_ratifies_for_every_type_that_has_an_anchor(doc_type):
    who = build_identity(4)
    number = {"aadhaar": who.aadhaar, "pan": who.pan,
              "voter_id": who.epic, "dl": who.dl}[doc_type]

    ctx = ctx_for(doc_type)
    signals = by_id(ratify.ratify(ctx, {"id_number": number,
                                        "name": who.name}))
    assert signals["extraction.vlm.ratified"].verdict == "pass", \
        signals["extraction.vlm.ratified"].evidence


@needs_generator
def test_a_generated_mrz_ratifies_and_a_tampered_one_does_not():
    who = build_identity(6)
    strip = who.mrz()

    ctx = ctx_for("passport")
    assert by_id(ratify.ratify(ctx, {"mrz": strip}))[
        "extraction.vlm.ratified"].verdict == "pass"
    assert ctx.fields["mrz"].raw == strip

    # Flip one digit of the date of birth and leave its check digit alone.
    lines = strip.split("\n")
    body = list(lines[1])
    body[13] = "9" if body[13] != "9" else "8"
    tampered = lines[0] + "\n" + "".join(body)

    ctx2 = ctx_for("passport")
    signals = by_id(ratify.ratify(ctx2, {"mrz": tampered}))
    assert signals["extraction.vlm.ratified"].verdict == "fail"
    assert "mrz" not in ctx2.fields


def test_pan_is_checked_against_the_surname_the_reader_returned():
    """The fifth character rule is only a check if the surname is supplied."""
    ctx = ctx_for("pan")
    signals = by_id(ratify.ratify(ctx, {"id_number": "ABCPG1234X",
                                        "name": "PRADEEP GHARAT"}))
    assert signals["extraction.vlm.ratified"].verdict == "pass"

    wrong = ctx_for("pan")
    signals = by_id(ratify.ratify(wrong, {"id_number": "ABCPZ1234X",
                                          "name": "PRADEEP GHARAT"}))
    assert signals["extraction.vlm.ratified"].verdict == "fail"
    assert "id_number" not in wrong.fields


# ---------------------------------------------------------------- structure

def test_a_value_already_read_is_never_overwritten_by_the_fallback():
    """OCR, the MRZ and a verified signed payload all outrank a fallback read.

    Same rule `seed_from_payload` follows in the other direction: the reader
    that can be checked wins over the one that cannot.
    """
    ctx = ctx_for("aadhaar")
    ctx.fields["name"] = NormalizedField(raw="REAL", value="REAL", source="ocr",
                                         confidence=0.9)
    ratify.ratify(ctx, {"name": "HALLUCINATED"})
    assert ctx.fields["name"].value == "REAL"
    assert ctx.fields["name"].source == "ocr"


def test_a_value_that_will_not_normalise_is_discarded_like_an_ocr_read():
    ctx = ctx_for("aadhaar")
    ratify.ratify(ctx, {"dob": "not a date at all"})
    assert "dob" not in ctx.fields


def test_the_ratifier_emits_each_id_at_most_once():
    """tests/test_signal_identity.py enforces this across a whole screening;
    two bugs in this repo were exactly an id emitted twice."""
    ctx = ctx_for("aadhaar")
    signals = ratify.ratify(ctx, {"id_number": valid_aadhaar(),
                                  "name": "A B", "dob": "1991-08-04",
                                  "gender": "M", "address": "somewhere"})
    ids = [s.id for s in signals]
    assert len(ids) == len(set(ids)), ids


def test_both_ids_are_registered_and_weighted():
    profile = load_profile("aadhaar")
    for sid in ("extraction.vlm.ratified", "extraction.vlm.unratified"):
        assert 0 < reliability(sid) <= 1.0, sid
        assert weight_for(profile, sid) > 0, sid


def test_a_type_with_no_anchor_says_so_rather_than_failing():
    """Every one of the six has an anchor today, so this guards the branch
    against a seventh type arriving without one."""
    assert ratify.anchor_for("passport") == ("mrz_checkdigits", "mrz")
    assert ratify.anchor_for("not_a_document") is None


def test_nothing_checkable_read_is_inconclusive_not_a_pass():
    ctx = ctx_for("passport")
    signals = by_id(ratify.ratify(ctx, {"name": "PRADEEP GHARAT"}))
    assert signals["extraction.vlm.ratified"].verdict == "inconclusive"


def test_the_ratifier_and_layer_a_agree_because_they_are_the_same_call():
    """Two implementations of one checksum drifting apart would give a system
    where the ratifier clears what the validator rejects."""
    from modules.validation.checksums import check_aadhaar
    number = valid_aadhaar("34567890123")
    assert ratify.check("verhoeff_aadhaar", number) == check_aadhaar(number)
