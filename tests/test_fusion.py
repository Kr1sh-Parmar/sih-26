"""Fusion property tests, then the four shared fixtures end to end.

The properties come from context/GETTING-STARTED.md section 4. They are the
safety net: every one of them is a way the system could clear someone it
should not.
"""
import pytest

from core.profiles import load_profile
from fusion.findings import build_findings, group_severity, resolve_anchor
from fusion.finding import Finding
from fusion.score import (apply_crypto_precedence, confirmed_fields,
                          coverage, score)
from fusion.signal import Signal, from_json


def sig(sid, verdict="pass", *, module="validation", trust="arithmetic",
        conf=1.0, hard=False, anchor="document", tier=1, evidence="", region=None):
    return Signal(id=sid, module=module, tier=tier, verdict=verdict, confidence=conf,
                  trust_class=trust, hard_fail=hard, anchor=anchor,
                  evidence=evidence or f"{sid} {verdict}", region=region)


PASSPORT = load_profile("passport")


# --------------------------------------------------------------- properties

def test_hard_fail_always_red_regardless_of_score():
    signals = [
        sig("validation.signature.valid", "pass", trust="cryptographic"),
        sig("validation.mrz.checkdigit.composite", "pass"),
        sig("validation.expiry.expired", "fail", hard=True),
    ]
    v = score(signals, PASSPORT, build_findings(signals))
    assert v.band == "RED"
    assert v.score == 1.0


def test_hard_fail_wins_even_when_profile_flag_missing_on_the_signal():
    # A module that forgot hard_fail=True must not be able to downgrade a RED.
    signals = [sig("validation.expiry.expired", "fail", hard=False)]
    assert score(signals, PASSPORT, build_findings(signals)).band == "RED"


def test_coverage_below_floor_never_returns_green():
    # Everything that could have answered is inconclusive except one cheap check.
    signals = [
        sig("extraction.quality.resolution", "pass"),
        sig("validation.signature.valid", "inconclusive", conf=0.0, trust="unverified"),
        sig("validation.mrz.checkdigit.composite", "inconclusive", conf=0.0),
        sig("validation.vizmrz.dob_mismatch", "inconclusive", conf=0.0),
        sig("face.match.cosine", "inconclusive", conf=0.0, module="face", trust="probabilistic"),
    ]
    v = score(signals, PASSPORT, build_findings(signals))
    assert v.band == "AMBER"
    assert v.coverage < 0.70
    assert "re-capture" in v.reason


def test_not_applicable_is_not_a_coverage_gap():
    # Aadhaar genuinely has no MRZ. That is not a gap, and treating it as one
    # would make every Aadhaar AMBER.
    aadhaar = load_profile("aadhaar")
    signals = [
        sig("validation.verhoeff.aadhaar", "pass"),
        sig("validation.signature.valid", "pass", trust="cryptographic"),
        sig("validation.mrz.checkdigit.composite", "not_applicable"),
    ]
    assert coverage(signals, aadhaar) == pytest.approx(1.0)
    assert score(signals, aadhaar, build_findings(signals)).band == "GREEN"


def test_inconclusive_is_not_pass():
    applicable = [sig("validation.signature.valid", "inconclusive", conf=0.0),
                  sig("validation.mrz.checkdigit.composite", "pass")]
    assert coverage(applicable, PASSPORT) < 1.0


def test_crypto_pass_suppresses_probabilistic_dispute_on_a_signed_field():
    signals = [
        sig("validation.signature.valid", "pass", trust="cryptographic"),
        sig("tamper.digital.ela", "fail", module="tamper", trust="probabilistic",
            conf=0.9, anchor="field:dob"),
        sig("validation.mrz.checkdigit.composite", "pass"),
    ]
    findings = build_findings(signals)
    assert any(f.anchor == "field:dob" for f in findings)

    v = score(signals, PASSPORT, findings, signed_fields={"field:dob"})
    assert not any(f.anchor == "field:dob" for f in v.findings)
    assert v.band == "GREEN"


def test_crypto_precedence_does_not_fire_when_the_signature_failed():
    # A broken signature is exactly when probabilistic evidence matters most.
    signals = [
        sig("validation.signature.issuer_trusted", "fail", trust="cryptographic", conf=1.0),
        sig("tamper.digital.ela", "fail", module="tamper", trust="probabilistic",
            conf=0.9, anchor="field:dob"),
    ]
    v = score(signals, PASSPORT, build_findings(signals), signed_fields={"field:dob"})
    assert any(f.anchor == "field:dob" for f in v.findings)


def test_four_correlated_signals_on_one_anchor_produce_one_finding():
    # The whole point of D8: one altered date of birth, one bullet.
    signals = [
        sig("validation.vizmrz.dob_mismatch", "fail", anchor="field:dob", conf=1.0),
        sig("tamper.physical.ocrb_conformance", "fail", anchor="field:dob",
            module="tamper", trust="probabilistic", conf=0.74),
        sig("tamper.physical.halftone", "fail", anchor="field:dob",
            module="tamper", trust="probabilistic", conf=0.66),
        sig("tamper.digital.copy_move", "fail", anchor="field:dob", tier=2,
            module="tamper", trust="probabilistic", conf=0.58),
    ]
    findings = build_findings(signals)
    assert len(findings) == 1
    assert len(findings[0].supporting) == 4
    # Strongest class present wins the group.
    assert findings[0].trust_class == "arithmetic"


def test_noisy_or_does_not_stack_past_certainty():
    one = [sig("tamper.digital.ela", "fail", conf=1.0, module="tamper",
               trust="probabilistic")]
    four = one * 4
    assert group_severity(four) < 1.0        # a sum would have been 1.2
    assert group_severity(four) > group_severity(one)


def test_passing_signals_do_not_create_severity():
    signals = [sig("validation.mrz.checkdigit.composite", "pass", conf=1.0)]
    assert group_severity(signals) == 0.0


def test_region_anchor_resolves_to_the_field_it_overlaps():
    boxes = {"dob": (600, 470, 950, 525), "name": (600, 360, 1250, 415)}
    assert resolve_anchor("region:605,472,945,523", boxes) == "field:dob"
    assert resolve_anchor("region:10,10,20,20", boxes) == "region:10,10,20,20"
    assert resolve_anchor("document", boxes) == "document"


# ------------------------------------------------------- the shared fixtures

BANDS = {"green": "GREEN", "red": "RED", "amber": "AMBER", "crossdoc": "RED"}


@pytest.mark.parametrize("name", sorted(BANDS))
def test_shared_fixture_scores_to_its_declared_band(fixtures, name):
    doc = fixtures[name]
    signals = [from_json(s) for s in doc["signals"]]
    profile = load_profile(doc["meta"]["doc_type"])
    v = score(signals, profile, build_findings(signals))
    assert v.band == BANDS[name] == doc["verdict"]["band"]


def test_amber_fixture_fails_the_coverage_floor_and_the_others_clear_it(fixtures):
    # The AMBER scene exists to prove the floor fires. If its coverage ever
    # creeps above 0.70 the scene stops proving anything.
    def cov(name):
        doc = fixtures[name]
        return coverage([from_json(s) for s in doc["signals"]],
                        load_profile(doc["meta"]["doc_type"]))

    assert cov("amber") < 0.70
    assert cov("green") >= 0.70
    assert cov("red") >= 0.70
    assert cov("crossdoc") >= 0.70


def test_crossdoc_red_is_cryptographically_backed(fixtures):
    # Scene 3, the headline. The verdict has to come from the signed payload,
    # not from a texture heuristic that happened to agree.
    doc = fixtures["crossdoc"]
    signals = [from_json(s) for s in doc["signals"]]
    v = score(signals, load_profile("pan"), build_findings(signals))
    culprit = next(s for s in signals if s.id == "validation.crossdoc.dob_mismatch")
    assert v.band == "RED"
    assert culprit.trust_class == "cryptographic"
    assert v.reason == culprit.evidence


# ------------------------- what a signature is allowed to suppress, and when


def test_a_signature_only_suppresses_a_field_it_was_checked_against():
    """The suppression that hid the evidence for a retyped card.

    `apply_crypto_precedence` drops probabilistic findings on signed fields:
    an ELA hotspot over a signed date of birth is recompression noise. The old
    rule fed it *every field the payload mentions*, which is the same mistake
    the VIZ/MRZ check made - a signature proves the payload, and says nothing
    about the ink until somebody compares the two.

    So a genuine signed card with its printed DOB altered had its
    `tamper.physical.font_consistency` finding - the check that exists to catch
    reprinting - suppressed as noise, because `field:dob` was in the payload.
    """
    tamper = Finding(anchor="field:dob", trust_class="probabilistic", severity=0.9,
                     headline="Character heights vary across the date of birth",
                     supporting=[sig("tamper.physical.font_consistency", "fail",
                                     module="tamper", trust="probabilistic",
                                     anchor="field:dob")])
    clean_sig = Finding(anchor="document", trust_class="cryptographic", severity=0.0,
                        headline="Signature verifies",
                        supporting=[sig("validation.signature.valid", "pass",
                                        trust="cryptographic")])
    findings = [clean_sig, tamper]

    # A verifying signature, but nothing compared the print against it.
    nothing_checked = confirmed_fields([
        sig("validation.signature.valid", "pass", trust="cryptographic"),
    ])
    assert nothing_checked == set()
    assert tamper in apply_crypto_precedence(findings, nothing_checked), (
        "tamper evidence over an unconfirmed field was suppressed"
    )

    # Print read and found to agree: now the hotspot really is noise.
    checked = confirmed_fields([
        sig("validation.signed.dob_mismatch", "pass", trust="cryptographic",
            anchor="field:dob"),
    ])
    assert checked == {"field:dob"}
    assert tamper not in apply_crypto_precedence(findings, checked)


def test_a_failing_comparison_confirms_nothing():
    """Only a *passing* check corroborates. A mismatch is the opposite."""
    assert confirmed_fields([
        sig("validation.signed.dob_mismatch", "fail", trust="cryptographic",
            anchor="field:dob"),
        sig("validation.crossdoc.name_mismatch", "inconclusive",
            trust="cryptographic", anchor="field:name"),
    ]) == set()


def test_the_cross_document_check_also_corroborates():
    """Scene 3's path: a signed Aadhaar vouching for a PAN's printed DOB."""
    assert confirmed_fields([
        sig("validation.crossdoc.dob_mismatch", "pass", trust="cryptographic",
            anchor="field:dob"),
    ]) == {"field:dob"}


# ------------------- a finding is labelled by the evidence for its own claim


def _mixed_anchor(signature="pass"):
    """A clean signature, a confirmed print, and one noisy heuristic on top."""
    return [
        sig("validation.signature.valid", signature, trust="cryptographic", conf=1.0),
        sig("validation.signed.dob_mismatch", "pass", trust="cryptographic",
            anchor="field:dob", conf=1.0),
        sig("tamper.digital.ela", "fail", module="tamper", trust="probabilistic",
            anchor="field:dob", conf=0.9),
    ]


def test_a_heuristic_does_not_inherit_a_signatures_trust_class():
    """A guess must never wear the authority of a signature.

    The finding's class used to be the strongest class present in the group. A
    clean cryptographic pass sharing an anchor with a failing tamper heuristic
    therefore produced a finding labelled `cryptographic` whose headline was
    the heuristic - which is the precise confusion this system exists to
    prevent, rendered in the officer's evidence list.
    """
    dob = next(f for f in build_findings(_mixed_anchor()) if f.anchor == "field:dob")
    assert dob.trust_class == "probabilistic"
    assert "tamper.digital.ela" in dob.headline
    # The signature is still in the group; it just does not lend it its class.
    assert any(s.trust_class == "cryptographic" for s in dob.supporting)


def test_crypto_precedence_can_actually_fire():
    """The bug the mislabel was hiding.

    That mislabelled finding landed in the cryptographic set carrying severity,
    so `any(f.severity > 0 for f in crypto)` was true and precedence returned
    everything untouched. The documented behaviour - a cryptographic pass
    suppresses probabilistic disputes about a field it confirmed - could not
    fire in the one situation it was written for.
    """
    signals = _mixed_anchor()
    findings = build_findings(signals)
    kept = apply_crypto_precedence(findings, confirmed_fields(signals))
    assert not any(f.anchor == "field:dob" for f in kept), (
        "an ELA hotspot over a field the signature confirmed was not suppressed"
    )


def test_a_failing_signature_still_suppresses_nothing():
    """One bad signature and the probabilistic evidence is what the officer needs."""
    signals = _mixed_anchor(signature="fail")
    kept = apply_crypto_precedence(build_findings(signals), confirmed_fields(signals))
    assert any(f.anchor == "field:dob" for f in kept)


def test_a_passing_group_still_reports_its_strongest_class():
    """With nothing failing, the finding is a pass and the strongest class is right."""
    signals = [
        sig("validation.signed.dob_mismatch", "pass", trust="cryptographic",
            anchor="field:dob", conf=1.0),
        sig("extraction.ocr.dob.confidence", "pass", module="extraction",
            trust="probabilistic", anchor="field:dob", conf=0.8),
    ]
    dob = next(f for f in build_findings(signals) if f.anchor == "field:dob")
    assert dob.trust_class == "cryptographic"
    assert dob.severity == 0.0


# ------------------------------------------------------- the risk gate


def test_a_verified_signature_does_not_buy_less_forensic_scrutiny():
    """The branch this replaces was dead, and the obvious repair is wrong.

    gate.py used to escalate un-signed documents above a *higher* threshold
    (0.25) than the general rule (0.15), so it never changed a decision - only
    the reason string. The tempting fix is to invert it and let a signature buy
    benefit of the doubt in a grey zone.

    D48 is why that is refused: a signature proves the payload and says nothing
    about the ink. Buying less scrutiny of the printing with a verified
    signature is the assumption that let a retyped card pass twice.
    """
    from fusion.gate import decide

    def tamper_at(level, *, signed):
        sigs = [sig("tamper.digital.ela", "fail", module="tamper",
                    trust="probabilistic", conf=level)]
        if signed:
            sigs.append(sig("validation.signature.valid", "pass",
                            trust="cryptographic", conf=1.0))
        return decide(sigs, PASSPORT)[0]

    for level in (0.05, 0.14, 0.16, 0.26, 0.40):
        assert tamper_at(level, signed=True) == tamper_at(level, signed=False), (
            f"a verified signature changed the escalation decision at {level}"
        )

    # And the threshold itself still bites in both directions.
    assert tamper_at(0.14, signed=True) == "clear"
    assert tamper_at(0.16, signed=True) == "escalate"
