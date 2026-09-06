"""FROZEN CONTRACT. See context/CONTRACTS.md §2.

Changes require agreement from the integration owner and must update
context/CONTRACTS.md and every implementation in the same commit.

Decode once: the orchestrator builds `image`. Nothing else opens a file.
Never put a model object on the context — models live in core/registry.py.
"""
from dataclasses import dataclass, field

import numpy as np


@dataclass
class NormalizedField:
    raw: str            # exactly what OCR returned
    value: str          # normalized (dates ISO-8601, names uppercase transliterated)
    source: str         # "ocr" | "mrz" | "qr" | "vlm"
    confidence: float
    box: tuple | None = None


@dataclass
class ScreeningContext:
    session_id: str
    image: np.ndarray                  # decoded ONCE. Never re-read from disk.
    doc_type: str                      # from the type classifier
    profile: dict                      # loaded YAML for this doc_type
    quad: np.ndarray | None = None     # 4x2 document corners
    warped: np.ndarray | None = None   # perspective-corrected image
    field_boxes: dict = field(default_factory=dict)   # {class_name: (x1,y1,x2,y2)}
    fields: dict = field(default_factory=dict)        # {field_name: NormalizedField}
    faces: dict = field(default_factory=dict)         # {'doc': ndarray, 'live': ndarray}
    embeddings: dict = field(default_factory=dict)    # {'doc': 512d, 'live': 512d}
    signals: list = field(default_factory=list)       # list[Signal]
    prior_docs: list = field(default_factory=list)    # other docs in this session
