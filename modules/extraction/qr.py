"""QR decoding at inspection time. Shares no code with issuer/qr.py.

The screening path has to be able to read a code it did not produce, so the
decoder is deliberately independent of the encoder.

Why pyzbar and not OpenCV's built-in QRCodeDetector
---------------------------------------------------
Measured, not assumed. A signed Ed25519 envelope is about 250 bytes, which is a
version-12 QR. Over 120 freshly signed codes:

    cv2.QRCodeDetector, single pass       ~90%
    cv2.QRCodeDetector, five variants     ~92%
    pyzbar                                 100%

A one-in-ten failure on the only path that carries the document fields is a
demo-breaker, and it fails in the worst way: the document comes back with no
cryptographic anchor, which reads as a finding rather than as a decoder that
gave up. pyzbar bundles libzbar in the wheel, so there is no model file to
fetch and nothing touches the network. OpenCV stays as a fallback so the
pipeline still runs where libzbar is missing.

On Debian-based images libzbar needs `apt-get install -y libzbar0`.
"""
import time

import cv2
import numpy as np

from core.decode import to_gray
from core.profiles import describe_start
from fusion.signal import Signal

try:
    from pyzbar.pyzbar import ZBarSymbol
    from pyzbar.pyzbar import decode as _zbar_decode
    HAVE_ZBAR = True
except Exception:                                   # noqa: BLE001
    HAVE_ZBAR = False


def _bbox(points) -> tuple | None:
    if points is None or len(points) == 0:
        return None
    pts = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    return (float(pts[:, 0].min()), float(pts[:, 1].min()),
            float(pts[:, 0].max()), float(pts[:, 1].max()))


def _variants(image: np.ndarray):
    """Progressively harder attempts. A laminated card under a counter light is
    frequently readable only once the contrast is forced."""
    gray = to_gray(image)
    yield image
    yield gray
    yield cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    yield cv2.equalizeHist(gray)
    h, w = gray.shape[:2]
    if max(h, w) < 1400:
        yield cv2.resize(gray, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)


def decode(image: np.ndarray) -> tuple[str | None, tuple | None]:
    """Return (payload, region) for the first QR found, or (None, None)."""
    if HAVE_ZBAR:
        for candidate in _variants(image):
            for symbol in _zbar_decode(candidate, symbols=[ZBarSymbol.QRCODE]):
                r = symbol.rect
                return (symbol.data.decode("utf-8", "replace"),
                        (float(r.left), float(r.top),
                         float(r.left + r.width), float(r.top + r.height)))

    detector = cv2.QRCodeDetector()
    for candidate in _variants(image):
        try:
            payload, points, _ = detector.detectAndDecode(candidate)
        except cv2.error:
            continue
        if payload:
            return payload, _bbox(points)
    return None, None


def scan(image: np.ndarray, profile: dict) -> tuple[str | None, list[Signal]]:
    """Decode the document QR and report whether one was found.

    Absence is not failure. Most of these documents carry no code at all, which
    is `not_applicable`; a code that is present but unreadable is
    `inconclusive` and rightly costs coverage.
    """
    started = time.perf_counter()
    expected = "qr_code" in profile["extract"]["detector_classes"]
    payload, region = decode(image)
    ms = int((time.perf_counter() - started) * 1000)

    if payload:
        return payload, []
    if not expected:
        return None, [Signal(
            id="validation.signature.valid", module="validation", tier=1,
            verdict="not_applicable", confidence=1.0, trust_class="unverified",
            hard_fail=False, anchor="document",
            evidence=f"{describe_start(profile['doc_type'])} carries no signed "
                     f"payload, so it has no cryptographic anchor of its own",
            latency_ms=ms,
        )]
    return None, [Signal(
        id="validation.signature.valid", module="validation", tier=1,
        verdict="inconclusive", confidence=0.0, trust_class="unverified",
        hard_fail=False, anchor="document",
        evidence="No readable signed payload was found on this document",
        region=region, latency_ms=ms,
    )]
