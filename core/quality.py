"""Capture quality gate. Real checks, no model.

This runs before anything expensive, and it is the reason a soft capture ends
as AMBER "re-capture required" instead of GREEN. A blurred document that
produced no readable evidence must not score well simply because nothing
disagreed (D9).

The document threshold is deliberately looser than the live one. Printed photos
are naturally softer than a camera capture, and the correct response differs
too: a bad document image needs a higher-resolution capture of the *document* -
the printed photo cannot be retaken.
"""
import time

import cv2
import numpy as np

from core.decode import to_gray
from core.profiles import load_config
from fusion.signal import Signal


def sharpness(image: np.ndarray) -> float:
    """Variance of the Laplacian. Higher is sharper."""
    return float(cv2.Laplacian(to_gray(image), cv2.CV_64F).var())


def brightness(image: np.ndarray) -> float:
    return float(to_gray(image).mean())


def check(image: np.ndarray, *, live: bool = False) -> list[Signal]:
    """Quality signals for one capture. Tier 1, runs on everything.

    Three checks, three ids. Brightness used to be filed under the blur id -
    `extraction.quality.blur` on the document path and `face.live.quality` on
    the live one - which broke three things at once. The audit log could not
    tell a washed-out capture from a soft one; `reliability()` scored brightness
    at blur's 0.80; and on the live path it collided with the id the *face crop*
    quality gate emits, so two unrelated checks reported under one name. The
    signal id is what a re-scoring reads years later, so two checks sharing one
    is not a tidiness problem.
    """
    started = time.perf_counter()
    cfg = load_config("thresholds")["quality"]
    kind = "live camera frame" if live else "document capture"
    prefix = "face.live" if live else "extraction"
    module = "face" if live else "extraction"
    signals: list[Signal] = []

    h, w = image.shape[:2]
    floor = cfg["min_short_edge_px"]
    ok_res = min(h, w) >= floor
    signals.append(Signal(
        id=f"{prefix}.quality.resolution", module=module, tier=1,
        verdict="pass" if ok_res else "fail", confidence=1.0,
        trust_class="arithmetic", hard_fail=False, anchor="document",
        evidence=(f"{w} by {h} pixels" if ok_res else
                  f"{w} by {h} pixels, below the {floor} pixel minimum for a {kind}"),
        latency_ms=int((time.perf_counter() - started) * 1000),
    ))

    t = time.perf_counter()
    value = sharpness(image)
    threshold = cfg["live_blur_min"] if live else cfg["doc_blur_min"]
    sharp = value >= threshold
    signals.append(Signal(
        id=f"{prefix}.quality.blur", module=module, tier=1,
        verdict="pass" if sharp else "fail",
        # How confident we are that the reading is right, not how sharp it is.
        confidence=1.0 if sharp else min(1.0, 0.5 + (threshold - value) / threshold),
        trust_class="probabilistic", hard_fail=False, anchor="document",
        evidence=(f"Image sharpness {value:.0f}, above the {threshold:.0f} threshold"
                  if sharp else
                  f"Image sharpness {value:.0f}, below the {threshold:.0f} threshold "
                  f"for a {kind}. " + (
                      "Ask the traveller to hold still and re-capture."
                      if live else
                      "Ask for a higher-resolution capture of the document.")),
        latency_ms=int((time.perf_counter() - t) * 1000),
    ))

    lo, hi = cfg["brightness_min"], cfg["brightness_max"]
    mean = brightness(image)
    ok_light = lo <= mean <= hi
    signals.append(Signal(
        id=f"{prefix}.quality.brightness", module=module, tier=1,
        verdict="pass" if ok_light else "fail", confidence=1.0 if ok_light else 0.7,
        trust_class="probabilistic", hard_fail=False, anchor="document",
        evidence=(f"Exposure is even (brightness {mean:.0f})" if ok_light else
                  (f"Capture is too dark to read reliably (brightness {mean:.0f}, "
                   f"below {lo})" if mean < lo else
                   f"Capture is washed out (brightness {mean:.0f}, above {hi})")
                  + ". " + ("Ask the traveller to move out of the glare and "
                            "re-capture." if live else
                            "Re-capture the document under even light.")),
    ))

    return signals


def is_usable(signals: list[Signal]) -> bool:
    """True when the capture is good enough to spend model time on.

    Any failing quality check, not only blur. A washed-out capture reaches OCR
    with no glyph contrast left, and the reason to check before spending model
    time is the same either way.
    """
    return not any(".quality." in s.id and s.verdict == "fail" for s in signals)


def sharpest(frames: list[np.ndarray]) -> np.ndarray:
    """Pick the sharpest of N frames.

    Webcam autofocus hunting produces blur, and a blurred live frame makes the
    face check inconclusive, which is a demo-breaker (DEMO.md).
    """
    if not frames:
        raise ValueError("no frames were captured")
    return max(frames, key=sharpness)
