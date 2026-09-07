"""1:N duplicate identity. Escalated tier only.

The question is not "have we seen this face" - at a border post the answer is
often yes, and legitimately so. It is **"has this face been presented under a
different document number"**, which is one person holding two identities and is
the thing worth an officer's time.

Two consequences follow and both are in the code:

  * The threshold is stricter than 1:1 (`face.gallery.threshold`, 0.45 against
    0.32). A 1:1 comparison is one test; a gallery search is one test per row,
    so the same per-comparison error rate produces far more false alarms. This
    is a multiple-comparisons problem, not a modelling one.
  * A match against a row carrying the *same* document number is the same person
    returning, and is silent.

Storage is embeddings, never crops (TECHNICAL-SPEC.md section 9). A 512-float
vector cannot be turned back into a face, and raw face images do not outlive the
session.
"""
import numpy as np

from core.profiles import load_config


def threshold() -> float:
    return float(load_config("thresholds")["face"]["gallery"]["threshold"])


def search(store, embedding: np.ndarray, doc_hash: str | None = None,
           limit: int = 5) -> list[dict]:
    """Prior screenings whose face matches this one above the gallery threshold.

    Rows belonging to the same document are dropped: the same traveller
    presenting the same passport twice is a re-capture, not a duplicate
    identity, and reporting it would train an officer to dismiss the signal.
    """
    if store is None or embedding is None:
        return []

    hits = []
    for face_id, event_id, cosine in store.search_faces(embedding, threshold(),
                                                        limit=limit + 5):
        event = store.event(event_id) if event_id else None
        if event is None:
            continue
        if doc_hash is not None and event.get("doc_hash") == doc_hash:
            continue
        hits.append({
            "face_id": face_id,
            "event_id": event_id,
            "cosine": float(cosine),
            "doc_type": event.get("doc_type"),
            "created_at": event.get("created_at"),
        })
        if len(hits) >= limit:
            break
    return hits


def describe(hits: list[dict]) -> str:
    """One line an officer can act on, naming when and on what document."""
    first = hits[0]
    when = str(first.get("created_at") or "an earlier screening")[:16]
    others = f", and {len(hits) - 1} more" if len(hits) > 1 else ""
    return (f"This face was already screened on {when} against a different "
            f"{first.get('doc_type') or 'document'} "
            f"(match {first['cosine']:.2f}){others}")
