"""Retention. TECHNICAL-SPEC.md section 9, ROADMAP Phase 5.

`api/main.py` carried the comment *"raw images and face crops must not outlive
the session"* above two dicts that were never emptied. The bytes of every
upload stayed resident for the life of the process and `GET /screen/{id}/image`
served them back indefinitely - an unbounded memory leak and a stated-policy
violation in the same four lines.

What these assert is the distinction that matters: the **raw capture** expires,
and the **audit trail** does not. A decision challenged months later has to be
re-scorable from what was recorded, so the signal list and the face embedding
are kept deliberately; it is the document image that must not survive the
traveller leaving the counter.

Expiry is driven by the clock, so the tests age an entry by editing its stored
timestamp rather than by sleeping or by mocking `time`. That exercises the real
eviction path and costs no wall clock.
"""
import time

import pytest
from fastapi.testclient import TestClient

from core.store import Store
from core.trust import Anchor
from issuer.sign import Keypair


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
        yield c


def _replay(client, name: str = "green") -> str:
    return client.post(f"/screen/replay/{name}", data={"session_id": "s"}).json()["id"]


# ------------------------------------------------------------------ the leak

def test_a_capture_is_discarded_once_its_ttl_passes(client):
    from api import main

    screening_id = _replay(client)
    assert screening_id in main.PENDING

    # Age it past the TTL rather than waiting fifteen minutes for one assertion.
    main.PENDING[screening_id]["created"] -= main.retention()["pending_seconds"] + 1
    assert main._evict() == 1
    assert screening_id not in main.PENDING


def test_an_expired_screening_tells_the_officer_what_to_do(client):
    """A bare 404 reads like a broken system. This one names the cause and the
    remedy, because it is the message an officer sees mid-queue."""
    from api import main

    screening_id = _replay(client)
    main.PENDING[screening_id]["created"] -= main.retention()["pending_seconds"] + 1

    response = client.get(f"/screen/{screening_id}/doc")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "Re-capture the document" in detail
    assert "discarded" in detail


def test_the_raw_image_is_really_gone_and_not_merely_hidden(client):
    """The point of the policy is the bytes, not the endpoint. If eviction only
    stopped serving them while they stayed resident, this would still be both a
    leak and a violation."""
    from api import main

    main.PENDING["held"] = {"mode": "live", "session_id": "s",
                            "image": b"\x89PNG" + b"x" * 4096,
                            "content_type": "image/png",
                            "created": time.monotonic()}
    assert client.get("/screen/held/image").status_code == 200

    main.PENDING["held"]["created"] -= main.retention()["pending_seconds"] + 1
    main._evict()

    assert "held" not in main.PENDING
    assert not any("image" in v for v in main.PENDING.values())
    assert client.get("/screen/held/image").status_code == 404


def test_a_fresh_capture_survives_eviction(client):
    """The other half. An eviction that drops everything is not a TTL."""
    from api import main

    screening_id = _replay(client)
    assert main._evict() == 0
    assert screening_id in main.PENDING


def test_stale_sessions_stop_vouching_for_whoever_is_at_the_counter_now(client):
    """Priors are what Layer D propagates from. A signed Aadhaar from an hour
    ago must not become ground truth for a stranger's PAN."""
    from api import main

    main._remember("s", {"doc_type": "aadhaar", "verified": True,
                         "payload": {"dob": "1996-11-02"}, "fields": {}})
    assert len(main._priors("s")) == 1

    main.SESSIONS["s"]["touched"] -= main.retention()["session_seconds"] + 1
    main._evict()
    assert main._priors("s") == []


def test_a_websocket_on_an_expired_screening_says_so_recoverably(client):
    from api import main

    screening_id = _replay(client)
    main.PENDING[screening_id]["created"] -= main.retention()["pending_seconds"] + 1

    with client.websocket_connect(f"/screen/{screening_id}") as socket:
        message = socket.receive_json()
    assert message["type"] == "error"
    assert message["recoverable"] is True
    assert "Re-capture" in message["message"]


# --------------------------------------------------- what must NOT be evicted

def test_the_audit_trail_outlives_the_capture(client):
    """The whole asymmetry, in one test.

    The image goes; the record stays. Storing signals rather than cards is only
    worth something if the record is still there to re-score months later, and
    a retention policy that swept it away would defeat the reason it exists.
    """
    from api import main

    store = main.state["store"]
    event_id = store.record_event(
        session_id="s", doc_type="aadhaar", doc_hash="h",
        verdict="GREEN", score=0.1, coverage=0.9, signals=[],
        model_versions={}, id_number="234567890126")

    main.PENDING["gone"] = {"mode": "live", "session_id": "s", "image": b"x",
                            "content_type": "image/png",
                            "created": time.monotonic() - 10_000}
    main._evict()

    assert "gone" not in main.PENDING
    assert store.event(event_id) is not None
    assert client.get("/events").json()["total"] == 1


def test_no_raw_identity_number_is_ever_returned(client):
    """CLAUDE.md rule 5, checked at the boundary that could leak it."""
    from api import main

    number = "234567890126"
    main.state["store"].record_event(
        session_id="s", doc_type="aadhaar", doc_hash="h", verdict="GREEN",
        score=0.1, coverage=0.9, signals=[], model_versions={}, id_number=number)

    body = client.get("/events").text
    assert number not in body
    assert "0126" in body
