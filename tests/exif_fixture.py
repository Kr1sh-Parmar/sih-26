"""Build a JPEG carrying a chosen EXIF Software tag.

The parser in `modules/tamper/digital.py` is hand-written, so the test that
exercises it needs EXIF that was *not* produced by the same code - otherwise the
two agree with each other and neither is checked against the format. This writes
the APP1 segment from the TIFF spec directly: little-endian, magic 42, one IFD
entry, tag 0x0131, ASCII.

Not a fixture on disk and not a real photograph - it is a few dozen bytes
prepended to whatever the caller already encoded (CLAUDE.md rule 4).
"""
import struct


def app1(software: str) -> bytes:
    """One APP1 segment declaring exactly one tag: Software."""
    value = software.encode("ascii") + b"\x00"

    # TIFF header (8) + entry count (2) + one 12-byte entry + next-IFD (4).
    # The string does not fit in the four inline bytes, so it follows at an
    # offset counted from the start of the TIFF header.
    offset = 8 + 2 + 12 + 4
    tiff = (
        b"II" + struct.pack("<HI", 42, 8)
        + struct.pack("<H", 1)
        + struct.pack("<HHII", 0x0131, 2, len(value), offset)
        + struct.pack("<I", 0)
        + value
    )
    body = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def with_software(jpeg: bytes, software: str) -> bytes:
    """Insert the segment straight after SOI, where a writer would put it."""
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    return jpeg[:2] + app1(software) + jpeg[2:]
