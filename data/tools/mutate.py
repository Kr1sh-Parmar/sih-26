"""Forgery mutations with ground-truth masks. Build-time and test-time only.

Five families, each a different thing a forger actually does, and each producing
a mask of what it touched so a region highlight can be scored rather than
eyeballed:

    copy_move    duplicate a patch of this document somewhere else on it
    splice       paste a patch from a *different* document
    recompress   save the file a second time at a different quality
    photo_swap   replace the portrait with someone else's
    retype       reprint a field at a different size and weight

The families exist to be held apart. CLAUDE.md's testing rule is to tune on one
family and report on a different one, because a threshold tuned and reported on
the same generator measures the generator. `data/tools/eval_tamper.py` enforces
that split; this file only has to make the families genuinely different.

Nothing here touches a real document. `synthetic_card()` draws its own, so tests
need no fixture on disk and no committed image (CLAUDE.md rule 4).
"""
import numpy as np

try:
    import cv2
except ImportError:                                     # pragma: no cover
    raise SystemExit("opencv is required: pip install opencv-python-headless")

FAMILIES = ("copy_move", "splice", "recompress", "photo_swap", "retype")


def synthetic_card(seed: int = 0, w: int = 900, h: int = 600) -> np.ndarray:
    """A card-shaped image with a print screen, a portrait block and text.

    Not a document and not pretending to be one - it exists so the forensics can
    be exercised on something with the *structure* they read: a periodic screen
    across the whole surface, one photographic region, and lines of uniform
    glyphs. Six real templates are a separate, much larger job.
    """
    rng = np.random.default_rng(seed)
    card = np.full((h, w, 3), 236, dtype=np.uint8)

    # The print screen: one periodic pattern across the whole card, which is
    # exactly what the halftone check measures the consistency of.
    ys, xs = np.mgrid[0:h, 0:w]
    screen = (np.sin(xs / 3.0) * np.sin(ys / 3.0) * 9).astype(np.int16)
    card = np.clip(card.astype(np.int16) + screen[:, :, None], 0, 255).astype(np.uint8)

    # A photographic region: smooth, unlike the printed text around it.
    face = rng.integers(90, 170, size=(160, 130, 3), dtype=np.uint8)
    face = cv2.GaussianBlur(face, (0, 0), 6)
    card[80:240, 60:190] = face

    for i, text in enumerate(("REPUBLIC OF EXAMPLE", "PRADEEP KESHAV GHARAT",
                              "1991-08-04", "X1234567")):
        cv2.putText(card, text, (230, 120 + i * 70), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (25, 25, 25), 2, cv2.LINE_AA)

    cv2.rectangle(card, (12, 12), (w - 12, h - 12), (40, 40, 40), 2)
    return card


def _mask_like(image: np.ndarray) -> np.ndarray:
    return np.zeros(image.shape[:2], dtype=np.uint8)


def copy_move(image: np.ndarray, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Duplicate a textured patch of this document elsewhere on it."""
    rng = np.random.default_rng(seed)
    out, mask = image.copy(), _mask_like(image)
    h, w = image.shape[:2]
    ph, pw = h // 5, w // 5

    sy, sx = int(rng.integers(0, h - ph)), int(rng.integers(0, w - pw))
    # Land it far away, or the offset falls under the copy-move floor and the
    # mutation is one the detector is *designed* not to report.
    dy = (sy + h // 2) % (h - ph)
    dx = (sx + w // 2) % (w - pw)
    out[dy:dy + ph, dx:dx + pw] = image[sy:sy + ph, sx:sx + pw]
    # Both ends are ground truth. After a duplication the two areas are the same
    # picture, and a detector highlighting either one has told the officer the
    # true thing - "these two places match". Marking only the destination would
    # score a correct answer as wrong half the time.
    mask[dy:dy + ph, dx:dx + pw] = 255
    mask[sy:sy + ph, sx:sx + pw] = 255
    return out, mask


def splice(image: np.ndarray, donor: np.ndarray | None = None,
           seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Paste a patch from a different document, at a different noise level."""
    rng = np.random.default_rng(seed)
    if donor is None:
        donor = synthetic_card(seed=seed + 1000)
    out, mask = image.copy(), _mask_like(image)
    h, w = image.shape[:2]
    ph, pw = h // 6, w // 4

    dy, dx = int(rng.integers(0, h - ph)), int(rng.integers(0, w - pw))
    patch = cv2.resize(donor, (pw, ph), interpolation=cv2.INTER_LINEAR)
    # A donor from another capture carries its own noise floor. That difference
    # is the thing the SRM residual is looking for.
    noise = rng.normal(0, 6, patch.shape).astype(np.int16)
    out[dy:dy + ph, dx:dx + pw] = np.clip(patch.astype(np.int16) + noise,
                                          0, 255).astype(np.uint8)
    mask[dy:dy + ph, dx:dx + pw] = 255
    return out, mask


def recompress(image: np.ndarray, first: int = 70,
               second: int = 92) -> tuple[np.ndarray, np.ndarray]:
    """Encode, decode, encode again. The whole image is touched, so the mask is full."""
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), first])
    if not ok:
        return image.copy(), _mask_like(image)
    once = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    ok, buf = cv2.imencode(".jpg", once, [int(cv2.IMWRITE_JPEG_QUALITY), second])
    twice = cv2.imdecode(buf, cv2.IMREAD_COLOR) if ok else once
    return twice, np.full(image.shape[:2], 255, dtype=np.uint8)


def _box(image: np.ndarray, fx1: float, fy1: float, fx2: float,
         fy2: float) -> tuple[int, int, int, int]:
    """A box given as fractions of the image, clipped to it.

    Cards in the dataset are every size and aspect ratio, so a box in absolute
    pixels overflows the small ones - which is not a hypothetical, it crashed a
    run. Fractions travel.
    """
    h, w = image.shape[:2]
    x1, y1 = int(fx1 * w), int(fy1 * h)
    x2, y2 = int(fx2 * w), int(fy2 * h)
    x1, y1 = max(0, min(w - 2, x1)), max(0, min(h - 2, y1))
    x2, y2 = max(x1 + 1, min(w, x2)), max(y1 + 1, min(h, y2))
    return x1, y1, x2, y2


def photo_swap(image: np.ndarray, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """Replace the portrait with a different face. The commonest real forgery."""
    rng = np.random.default_rng(seed)
    out, mask = image.copy(), _mask_like(image)
    x1, y1, x2, y2 = _box(image, 0.07, 0.13, 0.21, 0.40)
    face = rng.integers(70, 200, size=(y2 - y1, x2 - x1, 3), dtype=np.uint8)
    out[y1:y2, x1:x2] = cv2.GaussianBlur(face, (0, 0), 4)
    mask[y1:y2, x1:x2] = 255
    return out, mask


def retype(image: np.ndarray, text: str = "1998-11-02") -> tuple[np.ndarray, np.ndarray]:
    """Reprint one field at a different size and weight than the rest of the card."""
    out, mask = image.copy(), _mask_like(image)
    x1, y1, x2, y2 = _box(image, 0.26, 0.32, 0.78, 0.40)
    out[y1:y2, x1:x2] = 236
    # Deliberately a different scale and thickness from synthetic_card's other
    # lines - that mixture of glyph metrics is what print consistency measures.
    scale = max(0.6, (y2 - y1) / 34.0)
    cv2.putText(out, text, (x1 + 4, y2 - max(4, (y2 - y1) // 6)),
                cv2.FONT_HERSHEY_DUPLEX, scale, (20, 20, 20),
                max(2, int(scale * 2)), cv2.LINE_AA)
    mask[y1:y2, x1:x2] = 255
    return out, mask


def apply(family: str, image: np.ndarray, seed: int = 0):
    """Dispatch by family name. Returns (mutated image, ground-truth mask)."""
    if family == "copy_move":
        return copy_move(image, seed)
    if family == "splice":
        return splice(image, seed=seed)
    if family == "recompress":
        return recompress(image)
    if family == "photo_swap":
        return photo_swap(image, seed=seed)
    if family == "retype":
        return retype(image)
    raise ValueError(f"unknown mutation family {family!r}; expected one of {FAMILIES}")


def as_jpeg(image: np.ndarray, quality: int = 92) -> bytes:
    """Encode to JPEG bytes, for the checks that read file structure."""
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise ValueError("could not encode the image")
    return buf.tobytes()


def demo() -> None:
    """Self-check: every family changes the image and reports a truthful mask."""
    card = synthetic_card(seed=7)
    for family in FAMILIES:
        out, mask = apply(family, card, seed=3)
        assert out.shape == card.shape, family
        assert mask.shape == card.shape[:2], family
        assert mask.any(), f"{family} reported an empty mask"
        changed = np.any(out != card, axis=2)
        if family != "recompress":
            # The mask must cover what actually moved, not merely overlap it.
            assert changed[mask > 0].mean() > 0.5, f"{family} mask does not cover its edit"
            assert changed[mask == 0].mean() < 0.05, f"{family} edited outside its mask"
        print(f"{family:12s} ok, {int(changed.sum())} pixels changed")

    assert len(as_jpeg(card)) > 1000
    print("all mutation families ok")


if __name__ == "__main__":
    demo()
