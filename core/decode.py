"""Decode once. context/TECHNICAL-SPEC.md section 3.

L1 builds `ctx.image`. No module reopens the file, re-reads the bytes or
re-decodes. If a module needs a different resolution it derives one from
`ctx.image`. This is why the inference core is a single process: serialising a
3 MB scan four times costs more wall clock than the inference does (D5).
"""
import cv2
import numpy as np

#: Beyond this the extra pixels buy nothing and cost real milliseconds in every
#: downstream filter. A TD3 page at 300 dpi is about 1500x2100.
MAX_EDGE = 2400


class DecodeError(ValueError):
    """The bytes are not an image we can screen."""


def decode(data: bytes) -> np.ndarray:
    """Image bytes to a BGR array. The only place bytes become pixels."""
    if not data:
        raise DecodeError("no image data was received")
    buf = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if image is None:
        raise DecodeError("the uploaded file is not a readable image")
    return downscale(image)


def downscale(image: np.ndarray, max_edge: int = MAX_EDGE) -> np.ndarray:
    h, w = image.shape[:2]
    longest = max(h, w)
    if longest <= max_edge:
        return image
    scale = max_edge / longest
    # INTER_AREA is the correct filter for shrinking; INTER_LINEAR aliases the
    # fine line-work that the guilloche checks later depend on.
    return cv2.resize(image, (round(w * scale), round(h * scale)),
                      interpolation=cv2.INTER_AREA)


def to_gray(image: np.ndarray) -> np.ndarray:
    """Derived view, not a re-read. Cheap enough to call per module."""
    if image.ndim == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
