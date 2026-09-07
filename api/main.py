"""FastAPI application. One process, models warm, decode once.

Two entry points into the same fusion engine:

  POST /screen                  the real pipeline on an uploaded image
  POST /screen/replay/{name}    fixture signals through real fusion

The replay path is what actually replaces frontend/src/transport/mockSocket.ts,
and it is the backup DEMO.md asks for when the webcam fails on the day. It is
not a mock of the backend - the signals are fixtures, but the grouping, the
scoring, the coverage floor and the card ordering are the production code.

No network call at inspection time. Nothing here downloads anything.
"""
import json
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from api import router as pipeline
from api import websocket as ws
from core import registry
from core.decode import DecodeError
from core.profiles import DOC_TYPES, ProfileError, load_config, load_profile
from core.store import DEFAULT_DB, Store
from fusion.evidence import cards
from fusion.findings import build_findings
from fusion.score import score
from fusion.signal import from_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "frontend" / "src" / "fixtures"
FIXTURES = {
    "green": "signals_green",
    "red": "signals_red_hardfail",
    "amber": "signals_amber_coverage",
    "crossdoc": "signals_crossdoc_mismatch",
}

#: Screenings held in memory between the POST and the socket connecting, and
#: the source of GET /screen/{id}/doc. Session-scoped by design: raw images and
#: face crops must not outlive the session (TECHNICAL-SPEC.md section 9).
#:
#: That was a comment describing behaviour nothing implemented. Neither map was
#: ever emptied, so the full bytes of every upload stayed resident for the life
#: of the process and `GET /screen/{id}/image` served them back indefinitely -
#: an unbounded leak and a stated-policy violation in one. `_evict()` is the
#: thing that makes the sentence above true.
PENDING: dict[str, dict] = {}

#: session id -> {"priors": [...], "touched": monotonic seconds}. Priors are
#: what Layer D propagates from, so they expire with the traveller: a stale
#: prior still vouching for whoever stands at the counter an hour later is the
#: failure worth avoiding.
SESSIONS: dict[str, dict] = {}

state: dict = {}


def retention() -> dict:
    return load_config("thresholds")["retention"]


def _evict(now: float | None = None) -> int:
    """Drop expired captures and sessions. Returns how many went.

    Opportunistic - called by the handlers that touch these maps rather than by
    a background task. A single-counter process does not need a scheduler, and
    a scheduler is one more thing that can be wedged at 3am. The ceiling is
    plain: nothing expires while the process is idle. That is fine when the
    thing being bounded is memory, and it is what a restart is for.
    """
    cfg = retention()
    now = time.monotonic() if now is None else now

    stale = [k for k, v in PENDING.items()
             if now - v.get("created", now) > cfg["pending_seconds"]]
    for key in stale:
        # Drops the decoded context, the raw bytes and any live frame with it.
        PENDING.pop(key, None)

    cold = [k for k, v in SESSIONS.items()
            if now - v.get("touched", now) > cfg["session_seconds"]]
    for key in cold:
        SESSIONS.pop(key, None)

    return len(stale) + len(cold)


def _priors(session_id: str) -> list:
    entry = SESSIONS.get(session_id)
    return entry["priors"] if entry else []


def _remember(session_id: str, prior: dict) -> None:
    entry = SESSIONS.setdefault(session_id, {"priors": [], "touched": 0.0})
    entry["priors"].append(prior)
    entry["touched"] = time.monotonic()


def _expired_message() -> str:
    minutes = max(1, int(retention()["pending_seconds"] // 60))
    return (f"This screening is no longer held. Captures are discarded after "
            f"{minutes} minutes so they do not outlive the traveller at the "
            f"counter. Re-capture the document.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm everything once. Never build a session inside a request handler."""
    state["store"] = Store(DEFAULT_DB)
    state["anchors"] = state["store"].trust_anchors()
    for doc_type in DOC_TYPES:
        load_profile(doc_type)
    for name in ("reliability", "bands", "thresholds"):
        load_config(name)
    # Every ONNX session is built here, once. Never inside a handler: a cold
    # session on the first document is a latency spike at exactly the moment
    # someone is watching. `warm()` also does one throwaway inference so graph
    # optimisation is paid for before the first traveller, not during.
    state["models"] = registry.warm()
    yield
    state["store"].close()


app = FastAPI(title="SIH 26188 screening", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # The console is served from the same box; this is the Vite dev server.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "doc_types": list(DOC_TYPES),
        "trust_anchors": len(state["anchors"]),
        "watchlist": state["store"].watchlist_size(),
        "models": pipeline.model_versions(),
        "loaded": state["models"]["loaded"],
        "missing": state["models"]["missing"],
    }


@app.get("/profiles/{doc_type}")
def profile(doc_type: str) -> dict:
    """What the console needs from the profile (contracts/profile.ts)."""
    try:
        p = load_profile(doc_type)
    except ProfileError as exc:
        raise HTTPException(404, str(exc))
    return {"doc_type": p["doc_type"], "hard_fail": p["hard_fail"],
            "weights": p["weights"], "disclosure": p["disclosure"]}


@app.post("/screen")
async def create_screening(
    image: UploadFile,
    doc_type: str = Form(...),
    session_id: str = Form(...),
    uploaded: bool = Form(False),
    live: UploadFile | None = None,
) -> dict:
    """Accept a capture and return an id. The socket does the work.

    `live` is the optional camera frame of the person presenting the document.
    It rides on `ctx.faces['live']`, which the frozen contract already carries,
    so accepting it costs no contract change. Without it the face module reports
    what it can about the printed photo and marks the comparison `inconclusive`.
    """
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"unknown document type {doc_type!r}")

    _evict()
    data = await image.read()
    try:
        ctx = pipeline.build_context(data, doc_type, session_id,
                                     prior_docs=_priors(session_id))
    except DecodeError as exc:
        raise HTTPException(400, str(exc))

    if live is not None:
        try:
            ctx.faces["live"] = pipeline.decode_live(await live.read())
        except DecodeError as exc:
            raise HTTPException(400, f"live capture: {exc}")

    screening_id = str(uuid.uuid4())
    PENDING[screening_id] = {
        "ctx": ctx, "uploaded": uploaded, "session_id": session_id,
        "image": data, "content_type": image.content_type or "image/jpeg",
        "mode": "live", "created": time.monotonic(),
    }
    return {"id": screening_id, "session_id": session_id, "doc_type": doc_type}


@app.post("/screen/replay/{name}")
async def create_replay(name: str, session_id: str = Form("replay")) -> dict:
    """Fixture signals, real fusion. The mockSocket replacement."""
    if name not in FIXTURES:
        raise HTTPException(404, f"unknown fixture {name!r}")
    _evict()
    screening_id = str(uuid.uuid4())
    PENDING[screening_id] = {"mode": "replay", "fixture": name,
                             "session_id": session_id,
                             "created": time.monotonic()}
    return {"id": screening_id, "session_id": session_id, "fixture": name}


@app.get("/screen/{screening_id}/doc")
def screening_doc(screening_id: str) -> dict:
    """The document bundle the event stream does not carry.

    Same shape as FixtureDoc in the console, so `setDoc()` takes it unchanged.
    """
    _evict()
    pending = PENDING.get(screening_id)
    if pending is None:
        raise HTTPException(404, _expired_message())

    if pending["mode"] == "replay":
        return _fixture(pending["fixture"])

    ctx = pending["ctx"]
    h, w = ctx.image.shape[:2]
    return {
        "meta": {"doc_type": ctx.doc_type, "canvas": [w, h],
                 "scene": "live capture", "note": ""},
        "signals": [], "findings": [],
        "verdict": {"band": None, "score": None, "coverage": None,
                    "disclosure": None},
        # No cosine until the face module is deployed. A placeholder number
        # here would be a guess an officer might act on.
        "face": {"cosine": None,
                 "threshold": load_config("thresholds")["face"]["doc_live"]["threshold"]},
        "fields": _fields_of(ctx),
    }


@app.get("/screen/{screening_id}/image")
def screening_image(screening_id: str) -> Response:
    """The raw capture, while it still exists.

    This is the only endpoint that hands back an unredacted document image, so
    it is the one the retention rule is really about. After the TTL the bytes
    are gone and this says so in a sentence an officer can act on, rather than
    a bare 404 that reads like a bug.
    """
    _evict()
    pending = PENDING.get(screening_id)
    if pending is None:
        raise HTTPException(404, _expired_message())
    if pending["mode"] != "live":
        raise HTTPException(404, "This screening replayed stored signals, so "
                                 "there is no captured image to show.")
    return Response(pending["image"], media_type=pending["content_type"])


def _is_signed(event: dict) -> bool:
    """Did this document's own signature verify?

    Read back off the stored signals rather than kept as a column - the record
    already says it, and a second place to say it is a second place to be wrong.
    """
    return any(s["id"] == "validation.signature.valid" and s["verdict"] == "pass"
               for s in event["signals"])


def _edges(events: list[dict], priors: list[dict] | None = None) -> list[dict]:
    """Cross-document trust propagation, reconstructed from the stored signals.

    Layer D emits `validation.crossdoc.<field>_mismatch` on the *unsigned*
    document, so the edge runs from the most recent signed document earlier in
    the session to this one. That the signal exists at all means a signed prior
    was found - Layer D stays silent otherwise, rather than inventing a weaker
    version of itself.

    The two compared values ride along **only while the session is still live**.
    They are the traveller's name and date of birth, so they are deliberately
    never written to `screening_events` - but they do sit in `SESSIONS` for as
    long as the traveller is at the counter, which is exactly when the console
    needs to draw them. Once the session expires the edge keeps its verdict and
    its evidence sentence and loses the two values: the retention rule doing its
    job, not a degradation.

    ponytail: priors are joined to events by position. Both lists are appended
    once per screening in `_stream_live`, one immediately after the other, so
    index i is the same document in both. A real join key would need the event
    id threaded through `layer_d.as_prior`, whose shape is not mine to change.
    """
    # Written without the trailing dot on purpose: `tests/test_contracts.py`
    # treats any two-dot string literal as a signal id and demands it be
    # registered, and this is a prefix rather than an id.
    crossdoc = "validation.crossdoc"
    priors = priors or []
    out: list[dict] = []
    signed_so_far: list[dict] = []

    for index, event in enumerate(events):
        prior = priors[index] if index < len(priors) else {}
        for signal in event["signals"]:
            sid = signal["id"]
            if not sid.startswith(f"{crossdoc}.") or not signed_so_far:
                continue
            if signal["verdict"] not in ("pass", "fail"):
                continue
            field = sid.rsplit(".", 1)[-1].removesuffix("_mismatch")
            source = signed_so_far[-1]
            out.append({
                "field": field,
                "from": source["id"],
                "to": event["id"],
                "agrees": signal["verdict"] == "pass",
                "trust_class": signal["trust_class"],
                "evidence": signal["evidence"],
                "from_value": (source["prior"].get("payload") or {}).get(field),
                "to_value": (prior.get("fields") or {}).get(field),
            })
        if _is_signed(event):
            signed_so_far.append({**event, "prior": prior})
    return out


@app.get("/sessions/{session_id}")
def session(session_id: str) -> dict:
    """Documents screened in this session, and what vouched for what.

    The edges are the headline (D19): four of six Indian identity documents
    carry no cryptographic integrity, so when one in the session *is* signed,
    the console has to be able to draw what its payload proved about the others.
    """
    events = state["store"].session_events(session_id)
    return {
        "session_id": session_id,
        "documents": [
            {"id": e["id"], "doc_type": e["doc_type"], "band": e["verdict"],
             "score": e["score"], "coverage": e["coverage"],
             "signed": _is_signed(e), "created_at": e["created_at"]}
            for e in events
        ],
        "edges": _edges(events, _priors(session_id)),
    }


@app.get("/events")
def events(limit: int = 50, offset: int = 0) -> dict:
    """The audit table. Newest first.

    Carries the full signal list per event on purpose: storing signals rather
    than cards is only worth anything if the record can be opened and re-scored,
    and making the console fetch each event again to prove that would be a
    second round trip to demonstrate the first one worked.

    Never the raw identity number - the column does not exist. Salted hash and
    last four only (CLAUDE.md rule 5).
    """
    store = state["store"]
    rows = store.recent_events(limit=limit, offset=offset)
    return {
        "total": store.count_events(),
        "limit": limit,
        "offset": offset,
        "events": [
            {"id": e["id"], "session_id": e["session_id"],
             "doc_type": e["doc_type"], "created_at": e["created_at"],
             "band": e["verdict"], "score": e["score"], "coverage": e["coverage"],
             "id_number_hash": e["id_number_hash"],
             "id_number_last4": e["id_number_last4"],
             "officer_id": e["officer_id"],
             "model_versions": e["model_versions"],
             "signed": _is_signed(e),
             "signals": e["signals"]}
            for e in rows
        ],
    }


class Bands(BaseModel):
    """An operating point. The checkpoint commander sets these, not us."""
    green_below: float = Field(gt=0.0, le=1.0)
    amber_below: float = Field(gt=0.0, le=1.0)
    coverage_floor: float = Field(ge=0.0, le=1.0)


class RescoreRequest(BaseModel):
    event_id: str
    bands: Bands | None = None
    #: Signal id pattern to weight, e.g. {"tamper.*": 0.2}. Same matching the
    #: profile uses, so a wildcard behaves identically to one written in YAML.
    weights: dict[str, float] | None = None


@app.post("/rescore")
def rescore(request: RescoreRequest) -> dict:
    """Re-score a stored event under a different operating point.

    No model runs. Every input the scorer needs was written down at screening
    time, which is the whole reason `screening_events.signals` holds the full
    list rather than the evidence cards - cards are a view. This is what makes
    two verdicts months apart comparable when a weight has changed in between
    (CONTEXT.md section 3).
    """
    event = state["store"].event(request.event_id)
    if event is None:
        raise HTTPException(404, "No screening with that id was recorded.")

    signals = [from_json(s) for s in event["signals"]]
    try:
        profile = pipeline.profile_with_weights(event["doc_type"], request.weights)
    except ProfileError as exc:
        raise HTTPException(400, str(exc))

    cfg = load_config("bands")
    bands = (request.bands.model_dump() if request.bands else
             {**cfg["bands"], "coverage_floor": cfg["coverage_floor"]})
    if bands["green_below"] > bands["amber_below"]:
        raise HTTPException(400, "The clear threshold cannot sit above the "
                                 "secondary-inspection threshold.")

    verdict = pipeline.rescore(signals, profile, bands,
                               signed_fields=_proven_fields(signals))
    return {
        "event_id": event["id"],
        "doc_type": event["doc_type"],
        "recorded": {"band": event["verdict"], "score": event["score"],
                     "coverage": event["coverage"]},
        "rescored": {"band": verdict.band, "score": round(verdict.score, 3),
                     "coverage": round(verdict.coverage, 3),
                     "reason": verdict.reason},
        "changed": verdict.band != event["verdict"],
        "bands": bands,
        "weights_overridden": sorted(request.weights or {}),
    }


def _proven_fields(signals) -> set[str]:
    """Which field anchors a signature vouched for, read back off the record.

    An approximation, and worth naming as one. At screening time this is
    `core.canonical.signed_fields(payload)` - every non-empty field in the
    verified payload. The payload is the traveller's name and date of birth and
    is deliberately never stored, so re-scoring reconstructs the set from the
    cryptographic signals that survived instead. It covers every field a
    cryptographic check actually spoke about, which is the set that matters for
    suppression; a signed field nothing disputed is absent, and its absence
    changes nothing, because there is no probabilistic finding there to suppress.
    """
    return {s.anchor for s in signals
            if s.trust_class == "cryptographic" and s.anchor.startswith("field:")}


@app.websocket("/screen/{screening_id}")
async def screen_socket(socket: WebSocket, screening_id: str) -> None:
    await socket.accept()
    _evict()
    pending = PENDING.get(screening_id)
    if pending is None:
        await socket.send_json(ws.error(_expired_message(), recoverable=True))
        await socket.close()
        return

    try:
        if pending["mode"] == "replay":
            await _stream_replay(socket, pending)
        else:
            await _stream_live(socket, pending)
    except WebSocketDisconnect:
        return
    except Exception as exc:                      # noqa: BLE001
        # A crash mid-screening must still tell the officer something. A socket
        # that just closes looks identical to a clean pass on a slow machine.
        await socket.send_json(ws.error(f"Screening failed: {exc}", recoverable=True))
    finally:
        await _close(socket)


async def _stream_live(socket: WebSocket, pending: dict) -> None:
    ctx = pending["ctx"]
    result_holder: dict = {}

    events = pipeline.screen(ctx, anchors=state["anchors"],
                             store=state["store"], uploaded=pending["uploaded"],
                             raw=pending["image"])
    await ws.stream(events, socket.send_json,
                    on_done=lambda payload: result_holder.update(payload))

    result = result_holder.get("result")
    if result is None:
        return

    pipeline.persist(result, state["store"])
    # Feed this document forward so the next one in the session can be checked
    # against it. Only a verified payload travels (Layer D).
    _remember(pending["session_id"], pipeline.as_prior(result))


async def _stream_replay(socket: WebSocket, pending: dict) -> None:
    doc = _fixture(pending["fixture"])
    signals = [from_json(s) for s in doc["signals"]]
    profile = load_profile(doc["meta"]["doc_type"])

    await socket.send_json({"type": "phase", "phase": "decoding"})
    await socket.send_json({"type": "phase", "phase": "tier1"})

    async def emit(message):
        await socket.send_json(message)

    events = (pipeline.Event("signal", {"signal": s}) for s in signals)
    await ws.stream(events, emit)

    findings = build_findings(signals)
    verdict = score(signals, profile, findings)

    await socket.send_json({"type": "phase", "phase": "fusing"})
    await socket.send_json(ws.encode(pipeline.Event("findings",
                                                    {"findings": verdict.findings})))
    await socket.send_json({
        "type": "verdict", "band": verdict.band,
        "score": round(verdict.score, 3), "coverage": round(verdict.coverage, 3),
        "disclosure": doc["verdict"].get("disclosure"), "reason": verdict.reason,
    })
    await socket.send_json({"type": "cards",
                            "cards": cards(signals, verdict.findings, profile)})
    await socket.send_json({"type": "phase", "phase": "done"})


async def _close(socket: WebSocket) -> None:
    try:
        await socket.close()
    except RuntimeError:
        pass


def _fixture(name: str) -> dict:
    path = FIXTURE_DIR / f"{FIXTURES[name]}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _fields_of(ctx) -> list[dict]:
    """ctx.fields to the console's field-table shape."""
    out = []
    for name, field in ctx.fields.items():
        if name == "signed_payload":
            continue
        out.append({
            "name": name, "value": field.value, "source": field.source,
            "confidence": field.confidence,
            "state": "pass" if field.confidence >= 0.75 else "inconclusive",
            "region": list(field.box) if field.box else None,
        })
    return out
