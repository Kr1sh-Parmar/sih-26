"""QR encoding for the signed payload. Issuer side only.

Decoding at inspection time lives in modules/extraction/qr.py, which shares no
code with this file - the screening path must be able to read a code it did not
produce.
"""
from pathlib import Path

import segno


def encode(blob: str, path: Path, scale: int = 6, border: int = 4) -> Path:
    """Write the payload as a PNG QR code.

    Error correction M: the code has to survive being printed, laminated and
    then scanned under a counter light, but H would push an Ed25519 envelope
    into a version large enough that cheap scanners start missing modules.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    segno.make(blob, error="m").save(path, scale=scale, border=border)
    return path


def encode_bytes(blob: str, scale: int = 6, border: int = 4) -> bytes:
    import io
    buf = io.BytesIO()
    segno.make(blob, error="m").save(buf, kind="png", scale=scale, border=border)
    return buf.getvalue()
