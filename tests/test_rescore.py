"""Re-scoring a stored event, and the audit list it is driven from.

ROADMAP Phase 4's exit-gate item, and the answer to "decisions get challenged
months later" (CONTEXT.md section 3). The premise is that
`screening_events.signals` holds the **full signal list** rather than the
evidence cards - cards are a view - so a historical case can be re-scored under
a new operating point without a single model running.

The load-bearing test here is
`test_rescoring_with_the_configured_bands_agrees_with_fusion`. `api.router.
rescore()` restates `fusion.score.score()`'s ordering so the bands can be
injected, and two implementations of a safety-critical ordering are exactly the
kind of thing that drifts apart silently. That test is the tie between them.
"""
import pytest
from fastapi.testclient import TestClient

from core.profiles import load_config, load_profile
from core.store import Store
from core.trust import Anchor
from fusion.findings import build_findings
from fusion.score import score
from fusion.signal import Signal, to_json
from issuer.sign import Keypair

CONFIG_BANDS = {**load_config("bands")["bands"],
                "coverage_floor": load_config("bands")["coverage_floor"]}


def sig(sid, verdict="pass", *, module="validation", trust="arithmetic",
        conf=1.0, hard=False, anchor="document", tier=1, evidence=""):
    return Signal(id=sid, module=module, tier=tier, verdict=verdict,
                  confidence=conf, trust_class=trust, hard_fail=hard,
                  anchor=anchor, evidence=evidence or f"{sid} {verdict}")


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


def record(client, signals, *, doc_type="passport", verdict="GREEN",
           score_value=0.05, coverage=0.9, session="s", number=None) -> str:
    from api import main
    return main.state["store"].record_event(
        session_id=session, doc_type=doc_type, doc_hash="h", verdict=verdict,
        score=score_value, coverage=coverage, signals=signals,
        model_versions={"pipeline": "spine-1"}, id_number=number)


# ------------------------------------------------- the anti-drift guarantee

@pytest.mark.parametrize("signals", [
    [sig("validation.signature.valid"), sig("validation.mrz.checkdigit.composite")],
    [sig("validation.mrz.checkdigit.composite", "fail", hard=True)],
    [sig("validation.signature.valid", "inconclusive", trust="unverified"),
     sig("validation.expiry.expired", "inconclusive")],
    [sig("tamper.digital.copy_move", "fail", module="tamper",
         trust="probabilistic", conf=0.8),
     sig("validation.signature.valid")],
])
def test_rescoring_with_the_configured_bands_agrees_with_fusion(signals):
    """`api.router.rescore()` restates score()'s ordering to inject bands.

    Restating a safety-critical ordering is a drift hazard, so this pins the
    two together: handed the bands from config, the re-scorer must produce
    exactly what production fusion produces. If someone changes one and not the
    other, this fails.
    """
    from api import router

    profile = load_profile("passport")
    reference = score(signals, profile, build_findings(signals))
    replayed = router.rescore(signals, profile, CONFIG_BANDS)

    assert replayed.band == reference.band
    assert replayed.score == pytest.approx(reference.score)
    assert replayed.coverage == pytest.approx(reference.coverage)


def test_a_hard_fail_stays_red_under_any_operating_point():
    """No band a commander can set may talk a hard fail out of RED."""
    from api import router

    signals = [sig("validation.watchlist.hit", "fail", hard=True)]
    for bands in ({"green_below": 0.99, "amber_below": 0.999, "coverage_floor": 0.0},
                  {"green_below": 0.01, "amber_below": 0.02, "coverage_floor": 1.0}):
        assert router.rescore(signals, load_profile("passport"), bands).band == "RED"


def test_the_coverage_floor_still_beats_a_good_score():
    """Moving the floor is the operator's call; ignoring it is not (D9)."""
    from api import router

    signals = [sig("validation.signature.valid"),
               sig("validation.mrz.checkdigit.composite", "inconclusive"),
               sig("validation.vizmrz.dob_mismatch", "inconclusive")]
    strict = router.rescore(signals, load_profile("passport"),
                            {**CONFIG_BANDS, "coverage_floor": 0.95})
    assert strict.band == "AMBER"
    assert "re-capture" in strict.reason.lower()


# ------------------------------------------------------------- the endpoint

def test_rescore_returns_recorded_and_rescored_side_by_side(client):
    event_id = record(client, [sig("validation.signature.valid")])
    body = client.post("/rescore", json={"event_id": event_id}).json()

    assert body["event_id"] == event_id
    assert body["recorded"]["band"] == "GREEN"
    assert body["rescored"]["band"] in ("GREEN", "AMBER", "RED")
    assert body["changed"] is (body["rescored"]["band"] != "GREEN")


def test_moving_the_bands_can_change_a_stored_verdict(client):
    """The Phase 4 exit gate: an operating point moves, and history re-scores.

    Uses a weighted probabilistic failure, not a hard fail - a hard fail is RED
    under every band by design, which the test above pins down separately.
    """
    signals = [sig("validation.signature.valid", trust="cryptographic"),
               sig("tamper.digital.copy_move", "fail", module="tamper",
                   trust="probabilistic", conf=0.9, anchor="region:10,10,50,50")]
    event_id = record(client, signals)

    lenient = client.post("/rescore", json={
        "event_id": event_id,
        "bands": {"green_below": 0.9, "amber_below": 0.95, "coverage_floor": 0.1},
    }).json()
    strict = client.post("/rescore", json={
        "event_id": event_id,
        "bands": {"green_below": 0.01, "amber_below": 0.02, "coverage_floor": 0.1},
    }).json()

    assert lenient["rescored"]["band"] == "GREEN"
    assert strict["rescored"]["band"] == "RED"
    assert lenient["rescored"]["score"] == strict["rescored"]["score"], (
        "the score is a property of the evidence; only the bands moved")


def test_a_weight_override_changes_the_score_without_touching_the_cached_profile(client):
    """`load_profile` is lru_cached and its dict is shared process-wide.

    An override that mutated it would silently change the operating point for
    every screening afterwards, with nothing to re-read the file and put it back.
    """
    signals = [sig("tamper.digital.copy_move", "fail", module="tamper",
                   trust="probabilistic", conf=0.9),
               sig("validation.signature.valid")]
    event_id = record(client, signals)

    before = load_profile("passport")["weights"]["tamper.*"]
    heavy = client.post("/rescore", json={
        "event_id": event_id, "weights": {"tamper.*": 0.9}}).json()

    assert heavy["weights_overridden"] == ["tamper.*"]
    assert load_profile("passport")["weights"]["tamper.*"] == before
    assert heavy["rescored"]["score"] > 0


def test_no_model_runs_during_a_rescore(client, monkeypatch):
    """The claim being made is that the stored record is sufficient. If any
    module were reachable from this path, it would not be."""
    from modules import extraction, face, tamper

    for module in (extraction, face, tamper):
        monkeypatch.setattr(module, "run", _explode)

    event_id = record(client, [sig("validation.signature.valid")])
    assert client.post("/rescore", json={"event_id": event_id}).status_code == 200


def _explode(*args, **kwargs):
    raise AssertionError("re-scoring must not run inference")


def test_an_unknown_event_is_a_clear_404(client):
    response = client.post("/rescore", json={"event_id": "no-such-event"})
    assert response.status_code == 404
    assert "recorded" in response.json()["detail"]


def test_inverted_bands_are_rejected_rather_than_silently_reordered(client):
    event_id = record(client, [sig("validation.signature.valid")])
    response = client.post("/rescore", json={
        "event_id": event_id,
        "bands": {"green_below": 0.8, "amber_below": 0.2, "coverage_floor": 0.5}})
    assert response.status_code == 400


# ------------------------------------------------------- the batch endpoint

BATCH_BANDS = {"green_below": 0.2, "amber_below": 0.6, "coverage_floor": 0.7}


def test_a_batch_returns_what_n_single_rescores_would_have(client):
    """The whole point of the endpoint: one round trip, identical answers.

    If this ever diverges there are two scorers, which is the failure the
    endpoint exists to avoid.
    """
    ids = [record(client, [sig("validation.signature.valid")], session=f"b{n}")
           for n in range(3)]

    batch = client.post("/rescore/batch",
                        json={"event_ids": ids, "bands": BATCH_BANDS}).json()
    singles = [client.post("/rescore", json={"event_id": i,
                                             "bands": BATCH_BANDS}).json()
               for i in ids]

    assert [r["event_id"] for r in batch["results"]] == ids
    assert batch["results"] == singles


def test_one_unknown_id_does_not_blank_the_page(client):
    """A stale row in the console must cost that row, not the screen."""
    good = record(client, [sig("validation.signature.valid")])
    body = client.post("/rescore/batch", json={
        "event_ids": ["no-such-event", good, "also-missing"],
        "bands": BATCH_BANDS}).json()

    assert [r["event_id"] for r in body["results"]] == [good]


def test_a_batch_past_the_cap_is_refused(client):
    from api.main import MAX_BATCH

    response = client.post("/rescore/batch", json={
        "event_ids": [f"e{n}" for n in range(MAX_BATCH + 1)],
        "bands": BATCH_BANDS})
    assert response.status_code == 400
    assert str(MAX_BATCH) in response.json()["detail"]


def test_inverted_bands_fail_the_whole_batch_rather_than_every_row(client):
    """Bands are checked once, before any event is read. An operating point
    that makes no sense is a bad request, not 25 quietly dropped rows."""
    record(client, [sig("validation.signature.valid")])
    response = client.post("/rescore/batch", json={
        "event_ids": [], "bands": {"green_below": 0.8, "amber_below": 0.2,
                                   "coverage_floor": 0.5}})
    assert response.status_code == 400


# ------------------------------------------------------------------ /events

def test_events_lists_newest_first_and_pages(client):
    for n in range(5):
        record(client, [sig("validation.signature.valid")], doc_type="pan",
               session=f"s{n}")

    first = client.get("/events", params={"limit": 2}).json()
    assert first["total"] == 5
    assert len(first["events"]) == 2

    second = client.get("/events", params={"limit": 2, "offset": 2}).json()
    assert {e["id"] for e in first["events"]}.isdisjoint(
        {e["id"] for e in second["events"]})


def test_an_event_carries_its_whole_signal_list(client):
    """Cards are a view; signals are the record. The console opens an event to
    show what was stored, and it has to be all of it."""
    signals = [sig("validation.signature.valid"),
               sig("validation.expiry.expired", "fail")]
    record(client, signals)

    body = client.get("/events").json()["events"][0]
    assert len(body["signals"]) == 2
    assert {s["id"] for s in body["signals"]} == {s.id for s in signals}
    assert body["model_versions"]["pipeline"] == "spine-1"


def test_an_event_that_the_console_opens_can_be_rescored_from_that_payload(client):
    """The round trip the audit screen actually performs."""
    record(client, [sig("validation.signature.valid")])
    listed = client.get("/events").json()["events"][0]
    body = client.post("/rescore", json={"event_id": listed["id"]}).json()
    assert body["recorded"]["band"] == listed["band"]


# ---------------------------------------------------- session propagation

def test_a_session_reports_the_edge_a_signed_document_created(client):
    """D19, the headline: a signed Aadhaar vouches for an unsigned PAN, and the
    console has to be able to draw that."""
    aadhaar = record(client, [sig("validation.signature.valid", "pass",
                                  trust="cryptographic")],
                     doc_type="aadhaar", session="scene3")
    pan = record(client, [
        sig("validation.signature.valid", "inconclusive", trust="unverified"),
        sig("validation.crossdoc.dob_mismatch", "fail", trust="cryptographic",
            anchor="field:dob",
            evidence="The signed Aadhaar payload gives date of birth 1996-11-02; "
                     "this PAN prints 1998-11-02"),
    ], doc_type="pan", session="scene3", verdict="RED")

    body = client.get("/sessions/scene3").json()
    assert [d["signed"] for d in body["documents"]] == [True, False]

    edge = body["edges"][0]
    assert edge["field"] == "dob"
    assert (edge["from"], edge["to"]) == (aadhaar, pan)
    assert edge["agrees"] is False
    assert edge["trust_class"] == "cryptographic"
    assert "1996-11-02" in edge["evidence"] and "1998-11-02" in edge["evidence"]


def test_edge_values_are_present_while_the_session_lives_and_gone_after(client):
    """The two compared values are the traveller's date of birth.

    They are never written to `screening_events`, but they sit in `SESSIONS`
    while the traveller is at the counter - which is exactly when the console
    draws them. After the session expires the edge keeps its verdict and its
    evidence sentence and loses the values. That is the retention rule working,
    not the endpoint degrading.
    """
    from api import main

    record(client, [sig("validation.signature.valid", "pass", trust="cryptographic")],
           doc_type="aadhaar", session="live")
    record(client, [sig("validation.crossdoc.dob_mismatch", "fail",
                        trust="cryptographic", anchor="field:dob",
                        evidence="signed 1996-11-02; printed 1998-11-02")],
           doc_type="pan", session="live", verdict="RED")

    main._remember("live", {"doc_type": "aadhaar", "verified": True,
                            "payload": {"dob": "1996-11-02"}, "fields": {}})
    main._remember("live", {"doc_type": "pan", "verified": False, "payload": {},
                            "fields": {"dob": "1998-11-02"}})

    edge = client.get("/sessions/live").json()["edges"][0]
    assert edge["from_value"] == "1996-11-02"
    assert edge["to_value"] == "1998-11-02"

    main.SESSIONS["live"]["touched"] -= main.retention()["session_seconds"] + 1
    main._evict()

    expired = client.get("/sessions/live").json()["edges"][0]
    assert expired["from_value"] is None and expired["to_value"] is None
    assert expired["agrees"] is False, "the verdict outlives the values"
    assert "1996-11-02" in expired["evidence"]


def test_no_edge_without_a_signed_prior(client):
    """Layer D stays silent rather than inventing a weaker version of itself,
    and the session view must not invent one either."""
    record(client, [sig("validation.signature.valid", "inconclusive",
                        trust="unverified")], doc_type="pan", session="lonely")
    assert client.get("/sessions/lonely").json()["edges"] == []
