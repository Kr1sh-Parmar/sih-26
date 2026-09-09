"""ONNX session registry. Sessions are created once, at startup.

Never construct an InferenceSession inside a request handler (CLAUDE.md). A
cold session on the first document of the demo is a latency spike at exactly
the wrong moment, and `warm()` exists so that spike happens before anyone is
watching.

Everything here is CPU. No torch, no CUDA, no provider but CPUExecutionProvider
- training lives in .venv-train and never touches this process.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"

FIELD_DETECTOR = "field_detector_22cls"

#: Face models, fetched by scripts/fetch_face_models.py at build time. Absent is
#: a normal state and every caller degrades to `inconclusive`, same as the field
#: detector.
FACE_DETECTOR = "face_detector"
FACE_EMBEDDING = "face_embedding"
LIVENESS = "face_liveness"

#: Florence-2, the VLM fallback. Deliberately absent from `warm()`: it is four
#: graphs and 275 MB, it takes the warm footprint from about 450 MB to 910 MB,
#: and 85% of documents never reach it (TECHNICAL-SPEC.md section 4). It loads
#: on the first document that actually needs it, which is the one place in this
#: system where a cold session on the critical path is the right trade.
FLORENCE = "florence2"

#: Devanagari recognition. RapidOCR bundles `ch_PP-OCRv4_rec_infer.onnx`, whose
#: dictionary is Chinese and Latin - fed Devanagari it returns an empty string
#: at confidence 0.00 (measured; see data/EXTRACTION.md). Empty is the *safe*
#: failure - it becomes `inconclusive` rather than a wrong value - but it means
#: the `ocr_lang: [en, hi]` that `aadhaar`, `voter_id` and `dl` declare is only
#: half true, which is the debt D24 records.
#:
#: Two files, not one: a PP-OCR recogniser is a graph plus its character
#: dictionary, and the graph alone decodes to nonsense. Fetch both with
#: `scripts/fetch_ocr_models.py`.
DEVANAGARI_REC = "rec_devanagari"

#: More threads is not faster on models this small - the split costs more than
#: it saves, and the box is also serving a websocket. Override per deployment.
THREADS = int(os.environ.get("SCREENING_ORT_THREADS", "4"))


class ModelMissing(FileNotFoundError):
    """Weights are not baked into this image. Callers degrade, never crash."""


def model_path(name: str) -> Path | None:
    """Preferred int8, fp32 fallback, None when neither is present.

    Absence is a normal state: the deterministic spine screens documents
    without a detector, and says so through `inconclusive` signals.
    """
    for candidate in (MODELS / f"{name}.int8.onnx", MODELS / f"{name}.onnx"):
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=None)
def metadata(name: str) -> dict:
    """Sidecar written by the export step. Carries the class list and imgsz.

    Read these rather than hardcoding: the class order is the dataset's, and a
    detector re-exported at a different size must not silently be fed 640.
    """
    path = MODELS / f"{name}.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def session(name: str):
    """The one InferenceSession for this model. Cached for process lifetime."""
    import onnxruntime as ort

    path = model_path(name)
    if path is None:
        raise ModelMissing(
            f"no weights for {name} in {MODELS}. Train and export with "
            f"data/tools/train_fields.py, or run without it - the "
            f"deterministic checks do not need it."
        )

    options = ort.SessionOptions()
    options.intra_op_num_threads = THREADS
    options.inter_op_num_threads = 1
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    # Errors only. SCRFD is traced at a fixed input size and run at another, so
    # every detection prints nine harmless shape warnings - which would bury a
    # real message in the demo console.
    options.log_severity_level = 3
    return ort.InferenceSession(str(path), options,
                                providers=["CPUExecutionProvider"])


def available(name: str) -> bool:
    return model_path(name) is not None


def devanagari_rec() -> tuple[Path, Path] | None:
    """The Devanagari recogniser and its dictionary, or None if not deployed."""
    graph = MODELS / f"{DEVANAGARI_REC}.onnx"
    keys = MODELS / f"{DEVANAGARI_REC}.txt"
    return (graph, keys) if graph.exists() and keys.exists() else None


@lru_cache(maxsize=4)
def ocr_engine(lang: str = "en"):
    """RapidOCR: PP-OCRv4 detection, classification and recognition on ONNX.

    The default models ship inside the wheel (16 MB, three files), so nothing is
    fetched at runtime and the offline claim survives the cable being pulled.

    `lang="hi"` swaps only the *recogniser* - detection and angle classification
    are script-agnostic, and rebuilding them would cost two more sessions to do
    the same job. Falls back to the bundled recogniser when the Devanagari model
    is not deployed, which is the current state; the caller is expected to have
    checked `devanagari_rec()` and to say so in its evidence rather than
    silently reading Hindi with a Latin dictionary.
    """
    from rapidocr_onnxruntime import RapidOCR

    if lang == "hi":
        deployed = devanagari_rec()
        if deployed:
            graph, keys = deployed
            return RapidOCR(intra_op_num_threads=THREADS,
                            rec_model_path=str(graph), rec_keys_path=str(keys))
    return RapidOCR(intra_op_num_threads=THREADS)


def _version(name: str) -> str | None:
    """`<source>@<hash>` for the audit log, or None when genuinely not deployed."""
    meta = metadata(name)
    if not meta:
        return None
    # Florence-2 is four graphs behind one sidecar, so `available()` - which
    # looks for `<name>.onnx` - is the wrong question for it.
    graphs = meta.get("graphs")
    if graphs:
        if not all(available(g) for g in graphs):
            return None
    elif not available(name):
        return None
    label = meta.get("source") or meta.get("name", name)
    return f"{label}@{meta.get('sha256', '')[:12]}"


def versions() -> dict:
    """What actually ran, for the audit log.

    A screening event has to say which models produced it or it cannot be
    honestly re-scored later. `None` means the model is genuinely not deployed -
    these were hardcoded `None` while the face module was a stub, which would
    have kept claiming no face model was deployed long after one was.
    """
    detector = metadata(FIELD_DETECTOR)
    return {
        "field_detector": (
            f"{detector.get('name', FIELD_DETECTOR)}"
            f"@{detector.get('sha256', '')[:12]}" if detector else None
        ),
        "ocr": _ocr_version(),
        "ocr_devanagari": (
            f"{DEVANAGARI_REC}@{devanagari_rec()[0].stat().st_size}"
            if devanagari_rec() else None
        ),
        "face_detector": _version(FACE_DETECTOR),
        "face_embedding": _version(FACE_EMBEDDING),
        "liveness": _version(LIVENESS),
        "vlm": _version(FLORENCE),
        "pipeline": "spine-1",
    }


def _ocr_version() -> str | None:
    try:
        import rapidocr_onnxruntime as r
        return f"rapidocr-{getattr(r, '__version__', 'unknown')}/PP-OCRv4"
    except ImportError:
        return None


def warm() -> dict:
    """Build every session now. Called from the API lifespan, never per request.

    Returns what loaded and what did not, so startup logs say plainly which
    checks this process is capable of running.
    """
    loaded, missing = [], []

    for name in (FIELD_DETECTOR, FACE_DETECTOR, FACE_EMBEDDING, LIVENESS):
        if available(name):
            session(name)
            loaded.append(name)
        else:
            missing.append(name)

    try:
        engine = ocr_engine()
        # One throwaway inference so the first real document does not pay for
        # graph optimisation (DEMO.md: latency spike from a cold session).
        import numpy as np
        engine(np.full((48, 160, 3), 255, dtype=np.uint8))
        loaded.append("ocr")
    except Exception:                                       # noqa: BLE001
        missing.append("ocr")

    return {"loaded": loaded, "missing": missing, "versions": versions()}
