"""API and WebSocket, against the exact protocol the console already speaks.

The point of these tests is that frontend/src/store/screening.ts must be able
to consume what comes out of this socket without a single change, because that
reducer was written against the fixtures in week 0 and four people build
against it.
"""
import json

import pytest
from fastapi.testclient import TestClient

from core.store import Store
from core.trust import Anchor
from issuer.qr import encode_bytes
from issuer.sign import Keypair, sign
from modules.validation.checksums import verhoeff_digit

#: Every ScreeningEvent variant in frontend/src/contracts/events.ts.
PHASES = {"idle", "decoding", "tier1", "gate", "tier2", "fusing", "done"}
SIGNAL_KEYS = {"id", "module", "tier", "verdict", "confidence", "trust_class",
               "hard_fail", "anchor", "evidence", "region", "latency_ms"}


def aadhaar(payload_11="23456789012"):
    return payload_11 + verhoeff_digit(payload_11)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from api import main

    keypair = Keypair.generate("SIH-REF-01")
    store = Store(tmp_path / "test.db")
    store.put_anchor(Anchor("SIH-REF-01", keypair.public_key, "ed25519", True))

    monkeypatch.setattr(main, "DEFAULT_DB", tmp_path / "test.db")
    main.PENDING.clear()
    main.SESSIONS.clear()

    with TestClient(main.app) as c:
        c.keypair = keypair
        yield c


def signed_qr(keypair, **over) -> bytes:
    payload = {"doc_type": "aadhaar", "id_number": aadhaar(),
               "name": "PRADEEP KESHAV GHARAT", "dob": "1996-11-02", "gender": "M"}
    payload.update(over)
    return encode_bytes(sign(payload, keypair), scale=8)


def drain(socket) -> list[dict]:
    messages = []
    while True:
        message = socket.receive_json()
        messages.append(message)
        if message.get("type") == "phase" and message["phase"] == "done":
            return messages
        if message.get("type") == "error":
            raise AssertionError(f"screening errored: {message['message']}")


# ------------------------------------------------------------------- basics

def test_health_reports_what_is_actually_deployed(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["trust_anchors"] == 1
    # No learned model is deployed yet and the API says so rather than
    # implying otherwise.
    assert body["models"]["field_detector"] is None


def test_profile_endpoint_matches_the_console_contract(client):
    body = client.get("/profiles/pan").json()
    assert set(body) == {"doc_type", "hard_fail", "weights", "disclosure"}
    assert body["disclosure"]


def test_unknown_document_type_is_rejected(client):
    r = client.post("/screen", files={"image": ("a.png", b"x", "image/png")},
                    data={"doc_type": "library_card", "session_id": "s"})
    assert r.status_code == 400


def test_undecodable_upload_is_a_clear_error_not_a_crash(client):
    r = client.post("/screen", files={"image": ("a.png", b"not an image", "image/png")},
                    data={"doc_type": "aadhaar", "session_id": "s"})
    assert r.status_code == 400
    assert "image" in r.json()["detail"]


# ---------------------------------------------------------------- streaming

def test_replay_streams_the_protocol_the_console_expects(client):
    screening = client.post("/screen/replay/green", data={"session_id": "s"}).json()
    with client.websocket_connect(f"/screen/{screening['id']}") as socket:
        messages = drain(socket)

    kinds = {m["type"] for m in messages}
    assert {"phase", "signal", "findings", "verdict"} <= kinds

    for m in messages:
        if m["type"] == "phase":
            assert m["phase"] in PHASES
        if m["type"] == "signal":
            assert set(m["signal"]) == SIGNAL_KEYS
            assert m["signal"]["tier"] in (1, 2)
            assert m["signal"]["verdict"] in (
                "pass", "fail", "inconclusive", "not_applicable")


def test_replay_verdict_comes_from_real_fusion_not_the_fixture(client):
    # The signals are fixtures; the band is computed. That is the whole point
    # of routing the replay through production scoring.
    for name, band in (("green", "GREEN"), ("red", "RED"),
                       ("amber", "AMBER"), ("crossdoc", "RED")):
        screening = client.post(f"/screen/replay/{name}",
                                data={"session_id": "s"}).json()
        with client.websocket_connect(f"/screen/{screening['id']}") as socket:
            verdict = next(m for m in drain(socket) if m["type"] == "verdict")
        assert verdict["band"] == band, name
        assert 0.0 <= verdict["score"] <= 1.0
        assert 0.0 <= verdict["coverage"] <= 1.0


def test_amber_replay_says_why(client):
    screening = client.post("/screen/replay/amber", data={"session_id": "s"}).json()
    with client.websocket_connect(f"/screen/{screening['id']}") as socket:
        verdict = next(m for m in drain(socket) if m["type"] == "verdict")
    assert "re-capture" in verdict["reason"]


def test_an_expired_screening_id_is_a_recoverable_error(client):
    with client.websocket_connect("/screen/does-not-exist") as socket:
        message = socket.receive_json()
    assert message["type"] == "error"
    assert message["recoverable"] is True


# --------------------------------------------------------- the live pipeline

def test_a_signed_document_verifies_end_to_end(client):
    r = client.post("/screen",
                    files={"image": ("a.png", signed_qr(client.keypair), "image/png")},
                    data={"doc_type": "aadhaar", "session_id": "s1"})
    screening = r.json()

    with client.websocket_connect(f"/screen/{screening['id']}") as socket:
        messages = drain(socket)

    signals = {m["signal"]["id"]: m["signal"]
               for m in messages if m["type"] == "signal"}
    assert signals["validation.signature.valid"]["verdict"] == "pass"
    assert signals["validation.signature.valid"]["trust_class"] == "cryptographic"
    assert signals["validation.verhoeff.aadhaar"]["verdict"] == "pass"

    verdict = next(m for m in messages if m["type"] == "verdict")
    # The reference-issuer disclosure must render. A demonstration signature
    # must never look like a government one.
    assert verdict["disclosure"] and "reference issuer" in verdict["disclosure"]


def test_an_unsigned_document_is_amber_on_coverage_not_green(client):
    # Nothing was read, so nothing disagreed. That must not be a pass.
    import numpy as np, cv2
    blank = cv2.imencode(".png", np.full((800, 1200, 3), 220, np.uint8))[1].tobytes()
    screening = client.post("/screen",
                            files={"image": ("a.png", blank, "image/png")},
                            data={"doc_type": "pan", "session_id": "s2"}).json()
    with client.websocket_connect(f"/screen/{screening['id']}") as socket:
        verdict = next(m for m in drain(socket) if m["type"] == "verdict")
    assert verdict["band"] == "AMBER"
    assert verdict["coverage"] < 0.70
    assert verdict["disclosure"] is None


def test_the_headline_scene_over_the_real_socket(client):
    # Scene 3. A signed Aadhaar then a PAN that contradicts it, one session.
    qr = signed_qr(client.keypair, dob="1996-11-02")
    first = client.post("/screen", files={"image": ("a.png", qr, "image/png")},
                        data={"doc_type": "aadhaar", "session_id": "scene3"}).json()
    with client.websocket_connect(f"/screen/{first['id']}") as socket:
        drain(socket)

    # The PAN carries its own signed payload printing a different date of birth.
    pan_qr = signed_qr(client.keypair, doc_type="pan", id_number="ABLPG7040F",
                       dob="1998-11-02")
    second = client.post("/screen", files={"image": ("b.png", pan_qr, "image/png")},
                         data={"doc_type": "pan", "session_id": "scene3"}).json()
    with client.websocket_connect(f"/screen/{second['id']}") as socket:
        messages = drain(socket)

    signals = {m["signal"]["id"]: m["signal"]
               for m in messages if m["type"] == "signal"}
    mismatch = signals["validation.crossdoc.dob_mismatch"]
    assert mismatch["verdict"] == "fail"
    assert mismatch["trust_class"] == "cryptographic"
    assert "1996-11-02" in mismatch["evidence"] and "1998-11-02" in mismatch["evidence"]

    verdict = next(m for m in messages if m["type"] == "verdict")
    assert verdict["band"] == "RED"


def test_screening_is_persisted_without_the_raw_identity_number(client, tmp_path):
    from api import main
    number = aadhaar()
    screening = client.post(
        "/screen", files={"image": ("a.png", signed_qr(client.keypair), "image/png")},
        data={"doc_type": "aadhaar", "session_id": "audit"}).json()
    with client.websocket_connect(f"/screen/{screening['id']}") as socket:
        drain(socket)

    events = main.state["store"].session_events("audit")
    assert len(events) == 1
    event = events[0]
    assert event["id_number_last4"] == number[-4:]
    assert number not in json.dumps(event)          # the raw number never lands
    assert len(event["signals"]) > 10               # full list, not just cards


def test_doc_bundle_matches_the_console_shape(client):
    screening = client.post(
        "/screen", files={"image": ("a.png", signed_qr(client.keypair), "image/png")},
        data={"doc_type": "aadhaar", "session_id": "s3"}).json()
    with client.websocket_connect(f"/screen/{screening['id']}") as socket:
        drain(socket)

    doc = client.get(f"/screen/{screening['id']}/doc").json()
    assert set(doc) >= {"meta", "fields", "face", "verdict"}
    assert doc["meta"]["doc_type"] == "aadhaar"
    assert len(doc["meta"]["canvas"]) == 2
    # No cosine until the face module exists. A placeholder here is a number an
    # officer might act on.
    assert doc["face"]["cosine"] is None
    assert {f["name"] for f in doc["fields"]} >= {"name", "dob", "id_number"}


def test_session_endpoint_lists_what_was_screened(client):
    for _ in range(2):
        screening = client.post(
            "/screen", files={"image": ("a.png", signed_qr(client.keypair), "image/png")},
            data={"doc_type": "aadhaar", "session_id": "multi"}).json()
        with client.websocket_connect(f"/screen/{screening['id']}") as socket:
            drain(socket)

    body = client.get("/sessions/multi").json()
    assert len(body["documents"]) == 2
