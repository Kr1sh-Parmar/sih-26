"""The offline claim, enforced rather than asserted.

CLAUDE.md rule 3: zero network calls in the screening path. DEMO.md closes by
pulling the cable and running Scene 1 again, and ROADMAP.md Phase 5 makes that
an exit gate.

The reason this is a test and not a paragraph: the ways a screening path reaches
the network are all *libraries doing it for you on first use*. PaddleOCR
downloads its models on first call. `insightface.FaceAnalysis` downloads its
pack into a home directory. `huggingface_hub` resolves a repo id. None of those
appear in a diff as "network call" - they appear as an import and a constructor,
and they surface on the one day the cable is out.

So: forbid sockets, then run a real screening end to end, warming every model
first. Anything that tries to open a connection fails here rather than in front
of a panel.

Build-time downloaders are exempt by construction - `scripts/fetch_face_models.py`
and `data/tools/` are not importable from the screening path and are never
called by it.
"""
import socket

import numpy as np
import pytest

from api import router as pipeline
from core import registry
from core.store import Store
from data.tools import mutate


class NetworkAttempted(AssertionError):
    """Raised in place of opening a socket, so the traceback names the caller."""


@pytest.fixture
def no_network(monkeypatch):
    """Every route to a socket raises. The screening path must not notice."""
    def forbidden(*args, **kwargs):
        raise NetworkAttempted(
            "the screening path tried to open a network connection; "
            "everything it needs must be baked into the image")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    return forbidden


def test_warming_every_model_touches_no_network(no_network):
    """Models load from models/ and from inside the RapidOCR wheel.

    `warm()` is called once from the API lifespan and builds every session. If a
    model is going to fetch itself, this is where it happens.
    """
    registry.session.cache_clear()
    registry.ocr_engine.cache_clear()
    registry.metadata.cache_clear()

    state = registry.warm()
    assert state["loaded"], "nothing loaded at all; the test proved nothing"
    assert "ocr" in state["loaded"], (
        "OCR did not load offline - if it downloads its models on first use, "
        "the whole offline claim goes with it")


def test_a_full_screening_runs_with_the_cable_out(no_network):
    """Scene 1, offline. Decode, extract, validate, tamper, face, fuse."""
    card = mutate.synthetic_card(seed=11)
    raw = mutate.as_jpeg(card)
    store = Store(":memory:")

    ctx = pipeline.build_context(raw, "passport", "offline-session")
    ctx.faces["live"] = np.full((400, 400, 3), 180, np.uint8)

    verdict = None
    for event in pipeline.screen(ctx, store=store, uploaded=True, raw=raw):
        if event.type == "verdict":
            verdict = event.payload

    assert verdict is not None, "the pipeline produced no verdict"
    assert verdict["band"] in ("GREEN", "AMBER", "RED")
    assert ctx.signals, "no signals were emitted"


def test_an_escalated_screening_runs_offline_too(no_network):
    """Tier 2 loads nothing Tier 1 did not, but that is worth proving rather
    than assuming - deep forensics and the gallery are where a lazily-imported
    dependency would hide."""
    card = mutate.synthetic_card(seed=12)
    store = Store(":memory:")
    ctx = pipeline.build_context(mutate.as_jpeg(card), "aadhaar", "offline-2")

    from modules import face, tamper
    assert tamper.run(ctx, tier=2, uploaded=False)
    assert face.run(ctx, tier=2, store=store)


def test_the_screening_path_does_not_import_a_downloader():
    """A grep, deliberately. The socket block above catches a call at runtime;
    this catches the import that makes one possible on a path a test happens
    not to take."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    banned = {"requests", "urllib", "urllib3", "httpx", "huggingface_hub",
              "insightface", "roboflow", "torch"}
    offenders = []

    for folder in ("api", "core", "fusion", "modules"):
        for path in (root / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                else:
                    continue
                for name in names:
                    if name in banned:
                        offenders.append(f"{path.relative_to(root)}: {name}")

    assert not offenders, (
        "the screening path imports something that can reach the network or "
        "wants a GPU: " + "; ".join(offenders))
