"""Validation layers A-F, with hand-built contexts and no fixtures on disk.

Every identity number here is synthetic: the Aadhaar numbers carry a computed
Verhoeff digit over an arbitrary payload, and the passport numbers are made up.
"""
import time
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from core.profiles import load_config, load_profile
from core.store import Store
from core.trust import Anchor, TrustAnchorStore, verify_payload
from fusion.context import NormalizedField, ScreeningContext
from issuer.sign import Keypair, sign
from modules.extraction import mrz as M
from modules.validation import (layer_a, layer_b, layer_c, layer_d, layer_e,
                                layer_f, run)
from modules.validation.checksums import verhoeff_digit

TODAY = date(2026, 9, 6)


def field(value, raw=None, source="ocr", box=None):
    return NormalizedField(raw=raw if raw is not None else value, value=value,
                           source=source, confidence=1.0, box=box)


def ctx_for(doc_type, fields=None, *, prior_docs=None, field_boxes=None):
    return ScreeningContext(
        session_id="test-session",
        image=np.zeros((10, 10, 3), np.uint8),
        doc_type=doc_type,
        profile=load_profile(doc_type),
        fields=fields or {},
        field_boxes=field_boxes or {},
        prior_docs=prior_docs or [],
    )


def passport_ctx(*, printed_dob="1991-08-04", mrz_dob="1991-08-04", **over):
    strip = M.build_td3(
        issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
        document_number="E1009353", nationality="IND", birth_date=mrz_dob,
        sex="M", expiry_date="2031-07-17",
    )
    fields = {
        "mrz": field("", raw=strip, source="mrz", box=(90, 900, 1564, 1050)),
        "name": field("MUHAMAD SABRI"),
        "dob": field(printed_dob, box=(600, 470, 950, 525)),
        "id_number": field("E1009353"),
        "nationality": field("IND"),
        "gender": field("M"),
        "issue_date": field("2021-07-18"),
        "expiry_date": field("2031-07-17"),
    }
    fields.update(over)
    return ctx_for("passport", fields)


def by_id(signals):
    return {s.id: s for s in signals}


def aadhaar_number(payload_11="23456789012"):
    return payload_11 + verhoeff_digit(payload_11)


# ----------------------------------------------------------------- Layer A

def test_no_signature_is_inconclusive_not_pass():
    # NO_CRYPTO_ANCHOR. Treating this as a pass is how an unsigned document
    # gets to look as good as a signed one.
    s = by_id(layer_a.run(passport_ctx()))["validation.signature.valid"]
    assert s.verdict == "inconclusive"
    assert s.trust_class == "unverified"


def test_verified_signature_is_cryptographic_and_passes():
    keypair = Keypair.generate("SIH-REF-01")
    anchors = TrustAnchorStore([
        Anchor("SIH-REF-01", keypair.public_key, "ed25519", True)
    ])
    envelope = sign({"doc_type": "passport", "name": "MUHAMAD SABRI",
                     "dob": "1991-08-04", "id_number": "E1009353"}, keypair)
    ctx = passport_ctx(signed_payload=field("", raw=envelope, source="qr"))

    signals = by_id(layer_a.run(ctx, anchors=anchors))
    assert signals["validation.signature.valid"].verdict == "pass"
    assert signals["validation.signature.valid"].trust_class == "cryptographic"
    assert signals["validation.signature.issuer_trusted"].verdict == "pass"


def test_a_signature_from_an_unknown_issuer_fails_and_names_the_issuer():
    theirs = Keypair.generate("MADE-UP-AUTHORITY")
    envelope = sign({"doc_type": "passport", "name": "MUHAMAD SABRI"}, theirs)
    ctx = passport_ctx(signed_payload=field("", raw=envelope, source="qr"))
    anchors = TrustAnchorStore([
        Anchor("SIH-REF-01", Keypair.generate().public_key, "ed25519", True)
    ])
    signals = by_id(layer_a.run(ctx, anchors=anchors))
    assert signals["validation.signature.valid"].verdict == "fail"
    assert "MADE-UP-AUTHORITY" in signals["validation.signature.issuer_trusted"].evidence


def test_all_five_mrz_check_digits_are_emitted_and_pass_on_a_clean_document():
    signals = by_id(layer_a.run(passport_ctx()))
    for part in ("document_number", "dob", "expiry", "optional", "composite"):
        s = signals[f"validation.mrz.checkdigit.{part}"]
        assert s.verdict == "pass", part
        assert s.trust_class == "arithmetic"


def test_aadhaar_has_no_mrz_so_the_check_is_not_applicable():
    ctx = ctx_for("aadhaar", {"id_number": field(aadhaar_number())})
    s = by_id(layer_a.run(ctx))["validation.mrz.checkdigit.composite"]
    assert s.verdict == "not_applicable"


def test_unreadable_mrz_is_inconclusive_not_not_applicable():
    # The difference between these two is the difference between AMBER and a
    # GREEN verdict on a blurred photo.
    ctx = passport_ctx(mrz=field("", raw="", source="mrz"))
    s = by_id(layer_a.run(ctx))["validation.mrz.checkdigit.composite"]
    assert s.verdict == "inconclusive"


def test_verhoeff_runs_as_the_aadhaar_anchor():
    ok = ctx_for("aadhaar", {"id_number": field(aadhaar_number())})
    assert by_id(layer_a.run(ok))["validation.verhoeff.aadhaar"].verdict == "pass"

    bad = aadhaar_number()[:-1] + str((int(aadhaar_number()[-1]) + 1) % 10)
    broken = ctx_for("aadhaar", {"id_number": field(bad)})
    assert by_id(layer_a.run(broken))["validation.verhoeff.aadhaar"].verdict == "fail"


def test_pan_anchor_uses_the_surname():
    ctx = ctx_for("pan", {"id_number": field("ABLPG7040F"),
                          "name": field("PRADEEP KESHAV GHARAT")})
    assert by_id(layer_a.run(ctx))["validation.format.pan.id_number"].verdict == "pass"


# ----------------------------------------------------------------- Layer B

def test_unreadable_date_fails_format_not_silently_passes():
    ctx = passport_ctx(dob=field("19!1-0X-04"))
    assert by_id(layer_b.run(ctx))["validation.format.passport.dob"].verdict == "fail"


def test_icao_supplementary_country_codes_are_accepted():
    # D for Germany is Doc 9303, not ISO 3166. A check driven only by the ISO
    # list would flag a genuine German passport.
    ctx = passport_ctx(nationality=field("D"))
    assert by_id(layer_b.run(ctx))["validation.format.passport.nationality"].verdict == "pass"


def test_unknown_country_code_fails():
    ctx = passport_ctx(nationality=field("ZZZ"))
    assert by_id(layer_b.run(ctx))["validation.format.passport.nationality"].verdict == "fail"


def test_a_forbidden_class_appearing_is_itself_a_signal():
    ctx = ctx_for("voter_id", {"id_number": field("ABC1234567")},
                  field_boxes={"mrz": (10, 900, 900, 980)})
    s = by_id(layer_b.run(ctx))["validation.format.voter_id.layout"]
    assert s.verdict == "fail"
    assert "should not carry" in s.evidence


# ----------------------------------------------------------------- Layer C

def test_viz_mrz_mismatch_is_caught_and_names_both_values():
    # Scene 2: the forger edited the printed date and left the MRZ alone.
    ctx = passport_ctx(printed_dob="1991-08-04", mrz_dob="1991-03-04")
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.vizmrz.dob_mismatch"]
    assert s.verdict == "fail"
    assert "1991-03-04" in s.evidence and "1991-08-04" in s.evidence


def test_viz_mrz_agreement_passes_on_every_shared_field():
    signals = by_id(layer_c.run(passport_ctx(), today=TODAY))
    for f in ("dob", "name", "expiry_date", "id_number", "nationality", "gender"):
        assert signals[f"validation.vizmrz.{f}_mismatch"].verdict == "pass", f


def test_a_truncated_mrz_name_is_not_a_mismatch():
    # The MRZ name field is 39 characters and long Indian names get truncated.
    # Calling that forgery would train the officer to ignore the signal.
    ctx = passport_ctx(name=field("MUHAMAD SABRI BIN ABDULLAH"))
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.vizmrz.name_mismatch"]
    assert s.verdict == "pass"


def test_a_genuinely_different_name_is_still_a_mismatch():
    ctx = passport_ctx(name=field("PRADEEP GHARAT"))
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.vizmrz.name_mismatch"]
    assert s.verdict == "fail"


def test_unreadable_mrz_makes_viz_mrz_inconclusive_not_pass():
    ctx = passport_ctx(mrz=field("", raw="", source="mrz"))
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.vizmrz.dob_mismatch"]
    assert s.verdict == "inconclusive"


def test_aadhaar_viz_mrz_is_not_applicable():
    ctx = ctx_for("aadhaar", {"id_number": field(aadhaar_number())})
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.vizmrz.dob_mismatch"]
    assert s.verdict == "not_applicable"


def test_expired_document_is_caught():
    ctx = passport_ctx(expiry_date=field("2020-01-01"),
                       mrz_dob="1991-08-04")
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.expiry.expired"]
    assert s.verdict == "fail"
    assert "Expired" in s.evidence


def test_date_ordering_catches_an_issue_date_after_expiry():
    ctx = passport_ctx(issue_date=field("2032-01-01"))
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.crossfield.date_order"]
    assert s.verdict == "fail"


def test_non_standard_validity_period_is_flagged():
    ctx = passport_ctx(issue_date=field("2029-07-18"))
    s = by_id(layer_c.run(ctx, today=TODAY))["validation.crossfield.validity_period"]
    assert s.verdict == "fail"
    assert "not a standard" in s.evidence


# ----------------------------------------------------------------- Layer D

def signed_aadhaar_prior(dob="1996-11-02", name="PRADEEP KESHAV GHARAT"):
    keypair = Keypair.generate("SIH-REF-01")
    anchors = TrustAnchorStore([
        Anchor("SIH-REF-01", keypair.public_key, "ed25519", True)
    ])
    envelope = sign({"doc_type": "aadhaar", "id_number": aadhaar_number(),
                     "name": name, "dob": dob, "gender": "M"}, keypair)
    return layer_d.as_prior("aadhaar", verify_payload(envelope, anchors))


def pan_ctx(dob="1998-11-02", prior=None):
    return ctx_for("pan", {
        "id_number": field("ABLPG7040F"),
        "name": field("PRADEEP KESHAV GHARAT", box=(110, 300, 800, 355)),
        "dob": field(dob, box=(110, 480, 560, 535)),
    }, prior_docs=[prior] if prior else [])


def test_the_headline_a_signed_aadhaar_contradicts_an_unsigned_pan():
    signals = by_id(layer_d.run(pan_ctx(prior=signed_aadhaar_prior())))
    s = signals["validation.crossdoc.dob_mismatch"]
    assert s.verdict == "fail"
    assert s.trust_class == "cryptographic"
    assert "1996-11-02" in s.evidence and "1998-11-02" in s.evidence
    assert signals["validation.crossdoc.name_mismatch"].verdict == "pass"


def test_matching_documents_propagate_a_pass_not_silence():
    signals = by_id(layer_d.run(pan_ctx(dob="1996-11-02",
                                        prior=signed_aadhaar_prior())))
    assert signals["validation.crossdoc.dob_mismatch"].verdict == "pass"


def test_nothing_propagates_without_a_signed_prior():
    assert layer_d.run(pan_ctx()) == []


def test_an_unverified_prior_is_not_ground_truth():
    # A forged Aadhaar must not be able to condemn a genuine PAN.
    theirs = Keypair.generate("MADE-UP")
    envelope = sign({"doc_type": "aadhaar", "dob": "1996-11-02"}, theirs)
    prior = layer_d.as_prior("aadhaar", verify_payload(envelope, TrustAnchorStore()))
    assert prior["verified"] is False
    assert layer_d.run(pan_ctx(prior=prior)) == []


# ----------------------------------------------------------------- Layer E

@pytest.fixture
def seeded_store():
    store = Store(":memory:")
    store.add_watchlist_entry(
        source="synthetic", name="WANTED PERSON",
        name_key="PERSON WANTED", aliases=["W. PERSON"],
        dob="1980-01-01", doc_numbers=["X9999999"],
    )
    return store


def test_watchlist_clean_document_passes(seeded_store):
    ctx = passport_ctx()
    s = by_id(layer_e.run(ctx, store=seeded_store))["validation.watchlist.hit"]
    assert s.verdict == "pass"


def test_watchlist_hit_by_document_number(seeded_store):
    ctx = passport_ctx(id_number=field("X9999999"))
    s = by_id(layer_e.run(ctx, store=seeded_store))["validation.watchlist.hit"]
    assert s.verdict == "fail"
    assert "WANTED PERSON" in s.evidence


def test_watchlist_name_match_is_order_insensitive(seeded_store):
    ctx = passport_ctx(name=field("Wanted Person"), dob=field("1980-01-01"),
                       mrz_dob="1980-01-01")
    s = by_id(layer_e.run(ctx, store=seeded_store))["validation.watchlist.hit"]
    assert s.verdict == "fail"


def test_a_namesake_with_a_different_dob_is_inconclusive_not_a_detention(seeded_store):
    ctx = passport_ctx(name=field("Wanted Person"))
    s = by_id(layer_e.run(ctx, store=seeded_store))["validation.watchlist.hit"]
    assert s.verdict == "inconclusive"
    assert "Manual check" in s.evidence


def test_a_transliteration_variant_is_found_but_never_detains(seeded_store):
    """The spelling this layer could not previously see.

    "Wonted Person" is one vowel per token away from "Wanted Person" and lands
    in the same Soundex bucket. Finding it is the point of the near-match path -
    and reporting it as `fail` would be a detention decided by a spell-checker,
    so it must not.
    """
    ctx = passport_ctx(name=field("Wonted Person"))
    s = by_id(layer_e.run(ctx, store=seeded_store))["validation.watchlist.hit"]
    assert s.verdict == "inconclusive"
    assert s.verdict != "fail"          # hard_fail in every profile. Never guess it.
    assert "WANTED PERSON" in s.evidence
    assert "sounds like" in s.evidence


def test_a_near_match_is_less_confident_than_an_exact_one(seeded_store):
    near = by_id(layer_e.run(passport_ctx(name=field("Wonted Person")),
                             store=seeded_store))["validation.watchlist.hit"]
    exact = by_id(layer_e.run(passport_ctx(name=field("Wanted Person"),
                                           dob=field("1980-01-01"),
                                           mrz_dob="1980-01-01"),
                              store=seeded_store))["validation.watchlist.hit"]
    assert near.confidence < exact.confidence


def test_an_unrelated_name_is_still_a_clean_pass(seeded_store):
    """The failure that matters more than the miss: a near-match path that
    fires on everything teaches an officer to ignore the whole evidence list."""
    s = by_id(layer_e.run(passport_ctx(name=field("Ravi Sharma")),
                          store=seeded_store))["validation.watchlist.hit"]
    assert s.verdict == "pass"


def test_soundex_collapses_the_transliterations_it_is_there_for():
    assert layer_e.soundex("GHARAT") == layer_e.soundex("GHORAT")
    assert layer_e.soundex("PRADEEP") == layer_e.soundex("PRODEEP")
    # Order-insensitive, for the same reason the exact key is.
    assert (layer_e.phonetic_key("GHARAT PRADEEP")
            == layer_e.phonetic_key("PRADEEP GHARAT"))


def test_two_stores_of_equal_size_do_not_share_an_index():
    """A module-level cache keyed on row count would have failed this."""
    a, b = Store(":memory:"), Store(":memory:")
    for store, name in ((a, "ALPHA ONE"), (b, "BETA TWO")):
        store.add_watchlist_entry(source="synthetic", name=name,
                                  name_key=" ".join(sorted(name.split())))
    assert layer_e._nearest(a, "Alpha One") is None      # exact, handled earlier
    assert layer_e._nearest(a, "Beta Two") is None       # not on store a at all


def test_an_empty_watchlist_is_inconclusive_not_a_clean_pass():
    ctx = passport_ctx()
    s = by_id(layer_e.run(ctx, store=Store(":memory:")))["validation.watchlist.hit"]
    assert s.verdict == "inconclusive"


# --------------------------------------------------------------- the budget

def test_layers_a_to_d_run_inside_the_15ms_budget():
    ctx = passport_ctx()
    anchors = TrustAnchorStore()
    for _ in range(5):        # warm the profile and country-code caches
        run(ctx, anchors=anchors)

    started = time.perf_counter()
    for _ in range(20):
        run(ctx, anchors=anchors)
    per_call_ms = (time.perf_counter() - started) / 20 * 1000
    assert per_call_ms < 15, f"Layers A-D took {per_call_ms:.1f} ms, budget is 15"


# ------------------------- unverified reads may not contradict proven values

def test_a_fallback_read_cannot_hard_fail_a_genuine_document():
    """The worst failure this system can produce, and it was reachable.

    Florence-2 transcribes a date perfectly and then returns CHABRA for
    CHHABRA (data/EXTRACTION.md). Layer D compared whatever sat in
    `ctx.fields`, so a one-character misread against a signed payload fired
    `validation.crossdoc.name_mismatch` - a hard fail on four profiles -
    carrying trust class `cryptographic`, because the *other* side of the
    comparison is signed.

    A genuine traveller detained on an OCR error, and the console telling the
    officer it was certain. That is precisely the laundering of a probabilistic
    read into a cryptographic verdict that D3 exists to prevent.

    A disagreement between a proven value and an unchecked fallback read is not
    evidence of tampering; it is evidence the read was unreliable.
    """
    prior = signed_aadhaar_prior()
    ctx = pan_ctx(prior=prior)
    ctx.fields["name"] = field("PRADEEP KESHAV GHARAX", source="vlm")

    s = by_id(layer_d.run(ctx))["validation.crossdoc.name_mismatch"]
    assert s.verdict == "inconclusive", (
        "an unratified fallback read is disputing a cryptographically proven "
        "field, which can detain a genuine traveller on a transcription error")
    assert "fallback reader" in s.evidence


def test_an_ocr_read_still_hard_fails_a_real_mismatch():
    """The guard must not have bought safety by going blind.

    Layer D trust propagation is the headline demo and is on the never-cut
    list; an OCR-sourced disagreement has to keep firing.
    """
    ctx = pan_ctx(prior=signed_aadhaar_prior())
    ctx.fields["name"] = field("PRADEEP KESHAV GHARAX", source="ocr")

    s = by_id(layer_d.run(ctx))["validation.crossdoc.name_mismatch"]
    assert s.verdict == "fail"
    assert s.trust_class == "cryptographic"


def test_a_fallback_read_cannot_contradict_the_machine_readable_zone():
    """Same guard, Layer C. `validation.vizmrz.dob_mismatch` is a hard fail on
    passport, and it is the single highest-value tamper signal - which is
    exactly why it must not fire on a transcription error."""
    ctx = passport_ctx()
    ctx.fields["dob"] = field("1991-08-05", source="vlm")

    s = by_id(layer_c.run(ctx, today=TODAY))["validation.vizmrz.dob_mismatch"]
    assert s.verdict == "inconclusive"
    assert "fallback reader" in s.evidence


def test_the_comparable_guard_admits_the_sources_that_earned_it():
    """`qr` is comparable because a signed payload is proven; `mrz` because it
    carries its own check digits; `ocr` because it is gated on a confidence
    floor. `vlm` has none of the three."""
    from modules.validation import COMPARABLE_SOURCES
    assert COMPARABLE_SOURCES == frozenset({"ocr", "mrz", "qr"})


# ----------------------------------------------------------------- Layer F


def _event_at(store, post, *, hours_ago, number="E1009353", session="other"):
    """Record one screening at `post`, backdated. Layer F reads created_at."""
    import os
    was = os.environ.get("SCREENING_POST_ID")
    os.environ["SCREENING_POST_ID"] = post
    try:
        event_id = store.record_event(
            session_id=session, doc_type="passport", doc_hash="h" * 8,
            verdict="GREEN", score=0.1, coverage=0.9, signals=[],
            model_versions={}, id_number=number,
        )
    finally:
        if was is None:
            os.environ.pop("SCREENING_POST_ID", None)
        else:
            os.environ["SCREENING_POST_ID"] = was
    stamp = (datetime.utcnow() - timedelta(hours=hours_ago)).isoformat()
    with store._tx() as c:
        c.execute("UPDATE screening_events SET created_at = ? WHERE id = ?",
                  (stamp, event_id))
    return event_id


@pytest.fixture
def one_post(monkeypatch):
    monkeypatch.setenv("SCREENING_POST_ID", "raxaul")
    return Store(":memory:")


def test_transit_is_not_applicable_on_a_standalone_post(monkeypatch):
    """The default, and it must stay the default. One post cannot see transit,
    and a check that fires on a re-capture trains officers to ignore it."""
    monkeypatch.delenv("SCREENING_POST_ID", raising=False)
    ctx = passport_ctx(id_number=field("E1009353"))
    s = by_id(layer_f.run(ctx, Store(":memory:")))[
        "validation.history.impossible_transit"]
    assert s.verdict == "not_applicable"


def test_the_same_document_at_two_distant_posts_within_the_hour(one_post):
    # Sunauli to Raxaul is ~148 km of road. Twenty minutes is not possible.
    _event_at(one_post, "sunauli", hours_ago=0.33)
    ctx = passport_ctx(id_number=field("E1009353"))
    s = by_id(layer_f.run(ctx, one_post))["validation.history.impossible_transit"]
    assert s.verdict == "fail"
    assert "Sunauli" in s.evidence and "Raxaul" in s.evidence
    assert "km" in s.evidence


def test_the_same_journey_with_enough_time_is_a_pass(one_post):
    _event_at(one_post, "sunauli", hours_ago=12)
    ctx = passport_ctx(id_number=field("E1009353"))
    s = by_id(layer_f.run(ctx, one_post))["validation.history.impossible_transit"]
    assert s.verdict == "pass"


def test_twice_at_this_post_is_context_not_an_accusation(one_post):
    """A re-capture and a secondary inspection both look like this."""
    _event_at(one_post, "raxaul", hours_ago=0.1)
    ctx = passport_ctx(id_number=field("E1009353"))
    s = by_id(layer_f.run(ctx, one_post))["validation.history.impossible_transit"]
    assert s.verdict == "pass"
    assert "screened at this post" in s.evidence


def test_a_post_outside_the_location_table_is_inconclusive(one_post):
    _event_at(one_post, "some-new-icp", hours_ago=0.2)
    ctx = passport_ctx(id_number=field("E1009353"))
    s = by_id(layer_f.run(ctx, one_post))["validation.history.impossible_transit"]
    assert s.verdict == "inconclusive"
    assert "not in this network's location table" in s.evidence


def test_the_distance_between_two_real_posts_is_about_right():
    posts = load_config("posts")["posts"]
    km = layer_f.haversine_km(posts["raxaul"], posts["sunauli"])
    assert 120 < km < 180        # ~148 km. A wrong formula lands nowhere near.
