"""Face verification. STUB - InsightFace is not wired yet.

Every signal is `inconclusive`, which costs coverage and is correct: without a
threshold calibrated on our own document-to-live pairs, any number this module
produced would be a guess. With a live camera in the demo a guessed threshold
either rejects a teammate or accepts an impostor, in front of judges (D11).

Two things are deliberately encoded here before any model exists, because they
are decisions rather than code:

  * There is no 0-100 score. `((cos + 1) / 2) * 100` maps a total stranger to
    50 and a confident impostor to 58, and an officer reads 58 as "probably
    him". The scale is wrong in the direction that admits fraudsters (D10).
    When the real module lands it reports a cosine, the threshold, and the
    margin between them.
  * A bad document photo does not mean "retake your selfie". The printed photo
    cannot be retaken - the officer needs a higher-resolution capture of the
    document.
"""
import time

from core.profiles import load_config
from fusion.context import ScreeningContext
from fusion.signal import Signal

TIER1 = (
    ("face.doc.detected", "the face detector is not yet deployed"),
    ("face.live.detected", "the face detector is not yet deployed"),
    ("face.liveness.passive", "the passive liveness model is not yet deployed"),
    ("face.match.cosine", "the face embedding model is not yet deployed"),
)

TIER2 = (
    ("face.liveness.active", "active liveness is not yet deployed"),
    ("face.gallery.duplicate", "the duplicate-identity gallery is not yet populated"),
)


def threshold(name: str = "doc_live") -> tuple[float, bool]:
    """The operating point and whether it has actually been calibrated."""
    cfg = load_config("thresholds")["face"][name]
    return float(cfg["threshold"]), bool(cfg.get("calibrated", False))


def margin_text(cosine: float, name: str = "doc_live") -> str:
    """Three bands plus margin, never a percentage."""
    t, _ = threshold(name)
    direction = "above" if cosine >= t else "below"
    return (f"Document and live face match at cosine {cosine:.2f}, against a "
            f"{t:.2f} threshold, {abs(cosine - t):.2f} {direction} it")


def run(ctx: ScreeningContext, *, tier: int = 1) -> list[Signal]:
    started = time.perf_counter()
    source = ctx.profile["face"]["source_class"]
    region = ctx.field_boxes.get(source)
    checks = list(TIER1) + (list(TIER2) if tier >= 2 else [])

    out = []
    for sid, why in checks:
        anchor = f"field:{source}" if sid.startswith("face.doc") or sid == "face.match.cosine" else "document"
        out.append(Signal(
            id=sid, module="face", tier=2 if (sid, why) in TIER2 else 1,
            verdict="inconclusive", confidence=0.0, trust_class="probabilistic",
            hard_fail=False, anchor=anchor,
            evidence=f"Face verification has not run - {why}",
            region=tuple(region) if region else None,
            latency_ms=int((time.perf_counter() - started) * 1000),
        ))
    return out
