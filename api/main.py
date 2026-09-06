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
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from api import router as pipeline
from api import websocket as ws
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
PENDING: dict[str, dict] = {}
SESSIONS: dict[str, list] = {}

state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm everything once. Never build a session inside a request handler."""
    state["store"] = Store(DEFAULT_DB)
    state["anchors"] = state["store"].trust_anchors()
    for doc_type in DOC_TYPES:
        load_profile(doc_type)
    for name in ("reliability", "bands", "thresholds"):
        load_config(name)
    # ONNX sessions would be created here. core/registry.py owns that when the
    # models land; nothing is loaded lazily inside a handler.
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
        "models": pipeline.MODEL_VERSIONS,
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
) -> dict:
    """Accept a capture and return an id. The socket does the work."""
    if doc_type not in DOC_TYPES:
        raise HTTPException(400, f"unknown document type {doc_type!r}")

    data = await image.read()
    try:
        ctx = pipeline.build_context(data, doc_type, session_id,
                                     prior_docs=SESSIONS.get(session_id, []))
    except DecodeError as exc:
        raise HTTPException(400, str(exc))

    screening_id = str(uuid.uuid4())
    PENDING[screening_id] = {
        "ctx": ctx, "uploaded": uploaded, "session_id": session_id,
        "image": data, "content_type": image.content_type or "image/jpeg",
        "mode": "live",
    }
    return {"id": screening_id, "session_id": session_id, "doc_type": doc_type}


@app.post("/screen/replay/{name}")
async def create_replay(name: str, session_id: str = Form("replay")) -> dict:
    """Fixture signals, real fusion. The mockSocket replacement."""
    if name not in FIXTURES:
        raise HTTPException(404, f"unknown fixture {name!r}")
    screening_id = str(uuid.uuid4())
    PENDING[screening_id] = {"mode": "replay", "fixture": name,
                             "session_id": session_id}
    return {"id": screening_id, "session_id": session_id, "fixture": name}


@app.get("/screen/{screening_id}/doc")
def screening_doc(screening_id: str) -> dict:
    """The document bundle the event stream does not carry.

    Same shape as FixtureDoc in the console, so `setDoc()` takes it unchanged.
    """
    pending = PENDING.get(screening_id)
    if pending is None:
        raise HTTPException(404, "unknown screening")

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
    pending = PENDING.get(screening_id)
    if pending is None or pending["mode"] != "live":
        raise HTTPException(404, "no image for this screening")
    return Response(pending["image"], media_type=pending["content_type"])


@app.get("/sessions/{session_id}")
def session(session_id: str) -> dict:
    """Documents screened in this session, for the multi-document view."""
    events = state["store"].session_events(session_id)
    return {
        "session_id": session_id,
        "documents": [
            {"id": e["id"], "doc_type": e["doc_type"], "band": e["verdict"],
             "score": e["score"], "coverage": e["coverage"],
             "created_at": e["created_at"]}
            for e in events
        ],
    }


@app.websocket("/screen/{screening_id}")
async def screen_socket(socket: WebSocket, screening_id: str) -> None:
    await socket.accept()
    pending = PENDING.get(screening_id)
    if pending is None:
        await socket.send_json(ws.error("This screening has expired. Re-capture "
                                        "the document.", recoverable=True))
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
                             store=state["store"], uploaded=pending["uploaded"])
    await ws.stream(events, socket.send_json,
                    on_done=lambda payload: result_holder.update(payload))

    result = result_holder.get("result")
    if result is None:
        return

    pipeline.persist(result, state["store"])
    # Feed this document forward so the next one in the session can be checked
    # against it. Only a verified payload travels (Layer D).
    SESSIONS.setdefault(pending["session_id"], []).append(pipeline.as_prior(result))


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
