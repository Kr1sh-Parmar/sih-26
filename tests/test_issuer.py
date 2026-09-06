"""Reference issuer: canonicalisation, signing, verification, and the boundary.

No real identity number appears here.
"""
import base64
import json

import pytest

from core.canonical import canonicalise, doc_hash, normalise, signed_fields
from core.trust import Anchor, TrustAnchorStore, verify_payload
from issuer.sign import Keypair, sign

PAYLOAD = {
    "doc_type": "aadhaar",
    "id_number": "234567890123",
    "name": "PRADEEP KESHAV GHARAT",
    "father_name": "KESHAV NARAYAN GHARAT",
    "dob": "1996-11-02",
    "gender": "M",
    "address": "Raxaul, Bihar",
    "issuing_authority": "SIH reference issuer",
}


@pytest.fixture(scope="module")
def keypair():
    return Keypair.generate("SIH-REF-01")


@pytest.fixture(scope="module")
def store(keypair):
    return TrustAnchorStore([
        Anchor("SIH-REF-01", keypair.public_key, "ed25519", is_reference=True)
    ])


# ------------------------------------------------------- canonicalisation

def test_canonical_bytes_are_deterministic():
    assert canonicalise(PAYLOAD) == canonicalise(dict(PAYLOAD))


def test_key_order_cannot_change_the_bytes():
    reordered = {k: PAYLOAD[k] for k in reversed(list(PAYLOAD))}
    assert canonicalise(reordered) == canonicalise(PAYLOAD)


def test_absent_and_null_fields_canonicalise_identically():
    # Otherwise a document with no father's name signs differently depending on
    # whether the producer omitted the key or set it to None.
    a = {k: v for k, v in PAYLOAD.items() if k != "father_name"}
    b = {**PAYLOAD, "father_name": None}
    assert canonicalise(a) == canonicalise(b)


def test_whitespace_is_collapsed_not_preserved():
    assert normalise("ANNA   MARIA") == "ANNA MARIA"
    assert canonicalise({**PAYLOAD, "name": " PRADEEP  KESHAV GHARAT "}) \
        == canonicalise(PAYLOAD)


def test_a_changed_value_changes_the_bytes():
    assert canonicalise({**PAYLOAD, "dob": "1998-11-02"}) != canonicalise(PAYLOAD)


def test_unknown_fields_are_refused_rather_than_silently_dropped():
    with pytest.raises(ValueError):
        canonicalise({**PAYLOAD, "favourite_colour": "blue"})


def test_signed_fields_only_covers_fields_that_carry_a_value():
    fields = signed_fields(PAYLOAD)
    assert "field:dob" in fields
    assert "field:expiry_date" not in fields   # empty, so it proves nothing


def test_doc_hash_is_stable_hex():
    assert doc_hash(PAYLOAD) == doc_hash(dict(PAYLOAD))
    assert len(doc_hash(PAYLOAD)) == 64


# ------------------------------------------------------- sign and verify

def test_round_trip_verifies(keypair, store):
    v = verify_payload(sign(PAYLOAD, keypair), store)
    assert v.state == "AUTHENTIC"
    assert v.ok
    assert v.is_reference
    assert v.payload["dob"] == "1996-11-02"
    assert "SIH-REF-01" in v.detail


def test_editing_a_field_after_signing_is_caught(keypair, store):
    envelope = json.loads(sign(PAYLOAD, keypair))
    envelope["payload"]["dob"] = "1998-11-02"
    v = verify_payload(json.dumps(envelope), store)
    assert v.state == "TAMPERED"
    assert not v.ok


def test_a_forger_supplying_their_own_key_gets_unknown_issuer(store):
    # Never trust a key carried inside the thing it authenticates.
    theirs = Keypair.generate("TOTALLY-LEGIT-AUTHORITY")
    v = verify_payload(sign(PAYLOAD, theirs), store)
    assert v.state == "UNKNOWN_ISSUER"
    assert not v.ok


def test_a_signature_from_another_key_under_a_trusted_issuer_id_fails(store):
    impostor = Keypair.generate("SIH-REF-01")
    v = verify_payload(sign(PAYLOAD, impostor), store)
    assert v.state == "TAMPERED"


def test_revoked_key_is_not_authentic(keypair):
    store = TrustAnchorStore([
        Anchor("SIH-REF-01", keypair.public_key, "ed25519", True,
               valid_until="2020-01-01")
    ])
    assert verify_payload(sign(PAYLOAD, keypair), store, now="2026-09-06").state == "REVOKED"


@pytest.mark.parametrize("blob", [
    "not json at all",
    '{"issuer_id":"SIH-REF-01"}',
    '["a","list"]',
    '{"issuer_id":"SIH-REF-01","payload":"not an object","signature":"AA=="}',
])
def test_malformed_payloads_are_reported_not_raised(blob, store):
    assert verify_payload(blob, store).state == "MALFORMED_PAYLOAD"


def test_non_base64_signature_is_malformed_not_a_crash(keypair, store):
    envelope = json.loads(sign(PAYLOAD, keypair))
    envelope["signature"] = "!!!not base64!!!"
    assert verify_payload(json.dumps(envelope), store).state == "MALFORMED_PAYLOAD"


def test_truncated_signature_does_not_verify(keypair, store):
    envelope = json.loads(sign(PAYLOAD, keypair))
    raw = base64.b64decode(envelope["signature"])
    envelope["signature"] = base64.b64encode(raw[:-1]).decode()
    assert verify_payload(json.dumps(envelope), store).state != "AUTHENTIC"


def test_issuer_refuses_to_sign_fields_it_does_not_know(keypair):
    with pytest.raises(ValueError):
        sign({**PAYLOAD, "clearance_level": "top secret"}, keypair)


def test_signature_survives_a_qr_round_trip(keypair, store, tmp_path):
    # The envelope has to fit in a code a counter scanner can actually read.
    from issuer.qr import encode
    envelope = sign(PAYLOAD, keypair)
    path = encode(envelope, tmp_path / "code.png")
    assert path.exists() and path.stat().st_size > 0
    assert verify_payload(envelope, store).ok
