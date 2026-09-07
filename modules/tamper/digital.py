"""Track B - digital file forensics. context/TECHNICAL-SPEC.md section 7.

Five checks, split by what they actually need:

  bytes only    exif_software, double_jpeg      uploads only
  pixels only   ela                             uploads only
  pixels only   copy_move, noise_residual       always, tier 2

The uploads-only rule is D12 and it is not squeamishness. At a live counter the
scanner writes the file: EXIF is clean and the image is single-JPEG *by
construction*, so those three checks would be reporting on the scanner rather
than on the document. A professionally printed forgery passes all three
completely - it is the object that is fake, not the file.

Copy-move and noise residual are the exception and they run on everything. They
are pixel-domain: a photo physically pasted onto a card and then scanned is
still two regions with one origin, and the scan does not hide that. This is why
four profiles list `copy_move` under a *physical* partial track even though the
signal id is namespaced `digital` - the namespace is about method, not input.

**Nothing here re-decodes the input file** (CLAUDE.md rule 6). The byte-domain
checks parse markers; they never call imdecode. ELA decodes a buffer it encoded
itself, which is not the input.
"""
import struct
import time

import cv2
import numpy as np

from core.decode import to_gray
from core.profiles import load_config
from fusion.signal import Signal

#: Software strings that mean a human opened this file in an editor. Absence
#: proves nothing - EXIF is trivially stripped, and most genuine scans carry no
#: Software tag at all - which is why absence is `not_applicable`, not `pass`.
EDITORS = (
    "photoshop", "gimp", "paint", "pixlr", "canva", "snapseed", "lightroom",
    "picsart", "affinity", "imagemagick", "inkscape", "photopea", "krita",
    "coreldraw", "acdsee", "faststone",
)

#: The IJG standard luminance quantisation table at quality 50. Every camera,
#: scanner and libjpeg-based writer scales this one table. Photoshop and most
#: editors ship their own tables instead, and that difference survives EXIF
#: stripping, which is the whole point of checking it.
IJG_LUMA = np.array([
    16, 11, 10, 16, 24, 40, 51, 61,
    12, 12, 14, 19, 26, 58, 60, 55,
    14, 13, 16, 24, 40, 57, 69, 56,
    14, 17, 22, 29, 51, 87, 80, 62,
    18, 22, 37, 56, 68, 109, 103, 77,
    24, 35, 55, 64, 81, 104, 113, 92,
    49, 64, 78, 87, 103, 121, 120, 101,
    72, 92, 95, 98, 112, 100, 103, 99,
], dtype=np.int32)

#: JPEG stores a quantisation table in zig-zag order, not row-major. Comparing
#: a file's table against a row-major reference makes every ordinary JPEG look
#: non-standard - which would accuse every genuine upload of having been edited.
#: A test asserts round-tripping against OpenCV's own output at four qualities,
#: because this is exactly the kind of wrong that looks like it is working.
ZIGZAG = np.array([
    0, 1, 8, 16, 9, 2, 3, 10,
    17, 24, 32, 25, 18, 11, 4, 5,
    12, 19, 26, 33, 40, 48, 41, 34,
    27, 20, 13, 6, 7, 14, 21, 28,
    35, 42, 49, 56, 57, 50, 43, 36,
    29, 22, 15, 23, 30, 37, 44, 51,
    58, 59, 52, 45, 38, 31, 39, 46,
    53, 60, 61, 54, 47, 55, 62, 63,
], dtype=np.int32)

#: SRM high-pass kernel. The residual it leaves is dominated by sensor and
#: print noise rather than by content, so regional statistics over it compare
#: *sources* rather than subjects.
SRM = np.array([
    [-1, 2, -2, 2, -1],
    [2, -6, 8, -6, 2],
    [-2, 8, -12, 8, -2],
    [2, -6, 8, -6, 2],
    [-1, 2, -2, 2, -1],
], dtype=np.float32) / 12.0

BLOCK = 32


# --------------------------------------------------------------------- helpers

def _blocks(plane: np.ndarray, block: int = BLOCK) -> np.ndarray:
    """Block means of a single-channel float image, as a small 2-D array.

    INTER_AREA over a target size is exactly a box mean, and it is one call
    into OpenCV rather than a Python loop over a few thousand tiles.
    """
    h, w = plane.shape[:2]
    gh, gw = max(1, h // block), max(1, w // block)
    return cv2.resize(plane, (gw, gh), interpolation=cv2.INTER_AREA)


def _robust_z(values: np.ndarray) -> np.ndarray:
    """Median absolute deviation z-score. Outliers must not set their own scale."""
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    if mad <= 1e-9:
        return np.zeros_like(values)
    return (values - median) / (1.4826 * mad)


def _grid_box(grid_shape, mask: np.ndarray, image_shape, block: int = BLOCK):
    """Bounding box in image pixels around the True cells of a block mask."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    h, w = image_shape[:2]
    gh, gw = grid_shape
    sy, sx = h / gh, w / gw
    return (float(xs.min() * sx), float(ys.min() * sy),
            float(min(w, (xs.max() + 1) * sx)), float(min(h, (ys.max() + 1) * sy)))


# ------------------------------------------------------------------ byte domain

def exif_software(raw: bytes) -> str | None:
    """The EXIF Software tag (0x0131), or None when there is no EXIF at all.

    Hand-walked rather than pulling in Pillow for one tag. JPEG marker scan to
    APP1, then a TIFF IFD0 walk.
    """
    if not raw or raw[:2] != b"\xff\xd8":
        return None

    i = 2
    n = len(raw)
    while i + 4 <= n and raw[i] == 0xFF:
        marker = raw[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:                       # start of scan; no more headers
            return None
        (length,) = struct.unpack(">H", raw[i + 2:i + 4])
        segment = raw[i + 4:i + 2 + length]
        if marker == 0xE1 and segment[:6] == b"Exif\x00\x00":
            return _tiff_software(segment[6:])
        i += 2 + length
    return None


def _tiff_software(tiff: bytes) -> str | None:
    if len(tiff) < 8:
        return None
    endian = "<" if tiff[:2] == b"II" else ">" if tiff[:2] == b"MM" else None
    if endian is None:
        return None
    try:
        (magic,) = struct.unpack(endian + "H", tiff[2:4])
        if magic != 42:
            return None
        (ifd,) = struct.unpack(endian + "I", tiff[4:8])
        (count,) = struct.unpack(endian + "H", tiff[ifd:ifd + 2])
        for k in range(count):
            entry = ifd + 2 + k * 12
            tag, kind, size = struct.unpack(endian + "HHI", tiff[entry:entry + 8])
            if tag != 0x0131 or kind != 2:       # Software, ASCII
                continue
            if size <= 4:
                value = tiff[entry + 8:entry + 8 + size]
            else:
                (offset,) = struct.unpack(endian + "I", tiff[entry + 8:entry + 12])
                value = tiff[offset:offset + size]
            return value.split(b"\x00")[0].decode("ascii", "replace").strip() or None
    except (struct.error, IndexError, UnicodeDecodeError):
        return None
    return None


def quant_tables(raw: bytes) -> list[np.ndarray]:
    """Every DQT table in the file, in declaration order, zig-zag order kept."""
    tables: list[np.ndarray] = []
    if not raw or raw[:2] != b"\xff\xd8":
        return tables

    i, n = 2, len(raw)
    while i + 4 <= n and raw[i] == 0xFF:
        marker = raw[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xDA:
            break
        (length,) = struct.unpack(">H", raw[i + 2:i + 4])
        if marker == 0xDB:
            body = raw[i + 4:i + 2 + length]
            p = 0
            while p < len(body):
                precision, _tid = body[p] >> 4, body[p] & 0x0F
                p += 1
                width = 2 if precision else 1
                need = 64 * width
                if p + need > len(body):
                    break
                if precision:
                    values = np.frombuffer(body[p:p + need], dtype=">u2")
                else:
                    values = np.frombuffer(body[p:p + need], dtype=np.uint8)
                tables.append(values.astype(np.int32))
                p += need
        i += 2 + length
    return tables


def _ijg_at(quality: int) -> np.ndarray:
    """The IJG luma table at a quality factor, in the zig-zag order a file uses."""
    q = max(1, min(100, quality))
    scale = 5000 // q if q < 50 else 200 - q * 2
    scaled = np.clip((IJG_LUMA * scale + 50) // 100, 1, 255)
    return scaled[ZIGZAG]


def standard_quality(table: np.ndarray) -> tuple[int, bool]:
    """Closest IJG quality, and whether the table matches it exactly.

    An exact match means a libjpeg-family writer produced this file - which is
    every camera, every scanner, and every phone. A non-standard table means the
    writer shipped its own, which is characteristic of editing software.
    """
    best, best_error = 50, None
    for q in range(1, 101):
        error = int(np.abs(_ijg_at(q) - table).sum())
        if best_error is None or error < best_error:
            best, best_error = q, error
    return best, best_error == 0


# ----------------------------------------------------------------- pixel domain

def ela(image: np.ndarray, quality: int = 90) -> tuple[float, tuple | None]:
    """Error Level Analysis. Returns (robust-z of the worst block, region).

    Re-encode, difference, and look for a block whose error level is out of
    keeping with the rest of the page.

    The number is **error normalised by the block's own detail**, not raw error.
    Raw error tracks edges: any block containing sharp text re-compresses badly,
    so a raw-error ELA reports every crisp document as tampered. Dividing by the
    block's Laplacian energy asks the useful question instead - is this region
    compressing worse *than its own amount of detail predicts* - which is what a
    patch pasted in from a differently-compressed source actually does.

    Still fragile, still weighted 0.30 (D15). Global recompression flattens it.
    """
    ok, buf = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        return 0.0, None
    again = cv2.imdecode(buf, cv2.IMREAD_COLOR)
    if again is None or again.shape != image.shape:
        return 0.0, None

    gray = to_gray(image).astype(np.float32)
    error = _blocks(cv2.absdiff(image, again).max(axis=2).astype(np.float32))
    detail = _blocks(np.abs(cv2.Laplacian(gray, cv2.CV_32F)))
    if error.size < 16:
        return 0.0, None

    # Blocks with no detail have no error either; their ratio is noise over
    # noise and would dominate the spread.
    busy = detail > max(1.0, float(np.median(detail)) * 0.25)
    if busy.sum() < 8:
        return 0.0, None

    ratio = error / (detail + 1.0)
    z = np.full(ratio.shape, 0.0, dtype=np.float32)
    z[busy] = _robust_z(ratio[busy])

    peak = float(z.max())
    if peak <= 0:
        return 0.0, None
    hot = z >= max(peak * 0.85, 1e-6)
    return peak, _grid_box(z.shape, hot, image.shape)


def copy_move(image: np.ndarray, cfg: dict) -> tuple[int, tuple | None]:
    """ORB keypoint self-matching. Returns (cluster size, region).

    A region duplicated inside one image leaves many keypoint pairs sharing a
    single translation offset. Two guards separate that from ordinary
    self-similarity, and both are load-bearing:

      * the offset floor drops the trivial self-match and near neighbours;
      * **the cluster must be compact in space.** Printed text and guilloche
        match densely and at consistent offsets too - a periodic pattern is
        periodic everywhere - but their matches are spread across the whole
        page. A real copy-move is one patch appearing in one other place, so
        both ends occupy a small part of the document. Without this guard the
        check reports every security background as a forgery.

    This is the only check that produces a genuinely verifiable region
    highlight, which is why D16 prefers it to Grad-CAM.
    """
    gray = to_gray(image)
    h, w = gray.shape[:2]
    diagonal = float(np.hypot(h, w))
    min_offset = cfg["copy_move_min_offset_frac"] * diagonal
    bucket = float(cfg["copy_move_offset_bucket_px"])
    max_span = float(cfg["copy_move_max_span_frac"])

    orb = cv2.ORB_create(nfeatures=2000)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is None or len(keypoints) < 16:
        return 0, None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    # k=3 so the self-match can be dropped and two real candidates survive.
    neighbours = matcher.knnMatch(descriptors, descriptors, k=3)

    offsets: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for group in neighbours:
        for m in group:
            if m.queryIdx == m.trainIdx or m.distance > 32:
                continue
            a = keypoints[m.queryIdx].pt
            b = keypoints[m.trainIdx].pt
            dx, dy = b[0] - a[0], b[1] - a[1]
            if np.hypot(dx, dy) < min_offset:
                continue
            key = (int(round(dx / bucket)), int(round(dy / bucket)))
            offsets.setdefault(key, []).append((m.queryIdx, m.trainIdx))

    if not offsets:
        return 0, None

    key = max(offsets, key=lambda k: len(offsets[k]))
    pairs = offsets[key]
    if len(pairs) < cfg["copy_move_min_matches"]:
        return len(pairs), None

    source = np.array([keypoints[i].pt for i, _ in pairs], dtype=np.float32)
    dest = np.array([keypoints[j].pt for _, j in pairs], dtype=np.float32)

    # Both ends compact: a pasted patch is one area appearing in one other area.
    max_span = float(cfg["copy_move_max_span_frac"])
    for points in (source, dest):
        span = points.max(axis=0) - points.min(axis=0)
        if span[0] > max_span * w or span[1] > max_span * h:
            return len(pairs), None

    # And the two ends must be separate places. This is the guard that actually
    # works: a repeating security background matches itself at a consistent
    # offset across the whole page, so its "source" and "destination" regions
    # are the same region and overlap almost completely. A genuine duplication
    # has two disjoint areas. Without this the check reports a third of all
    # genuine cards as forged.
    if _iou(_bbox(source), _bbox(dest)) > float(cfg["copy_move_max_overlap"]):
        return len(pairs), None

    # Last: look at the pixels. Keypoints agreeing on an offset is a hypothesis,
    # not evidence - a card with repeated structure can produce a clean, compact,
    # disjoint cluster by coincidence, and one in five genuine cards did. A real
    # duplication means the two regions are the *same picture*, so shift one onto
    # the other and correlate. This is the check that took the false-positive
    # rate from a fifth of all genuine cards to a few percent, and it is also
    # what makes the region highlight worth showing an officer: it has been
    # confirmed against the image, not merely proposed.
    box = _bbox(dest)
    correlation = _region_correlation(gray, box, np.median(dest - source, axis=0))
    if correlation < float(cfg["copy_move_min_correlation"]):
        return len(pairs), None

    # And it has to be big enough to matter. Genuine cards carry repeated design
    # elements - a corner mark, a microtext band, a logo printed twice - and
    # those are real duplications, correctly found, of things that are supposed
    # to be duplicated. They are also small. A forger pastes a photograph or a
    # date field, which is field-sized.
    x1, y1, x2, y2 = box
    if (x2 - x1) * (y2 - y1) < float(cfg["copy_move_min_region_frac"]) * h * w:
        return len(pairs), None
    return len(pairs), (float(x1), float(y1), float(x2), float(y2))


def _region_correlation(gray: np.ndarray, box, offset) -> float:
    """Normalised correlation between a region and the place it was copied from."""
    h, w = gray.shape[:2]
    dx, dy = float(offset[0]), float(offset[1])
    pad = 6                       # the keypoint hull undercuts the pasted patch

    x1 = int(max(0, min(w - 2, box[0] - pad)))
    y1 = int(max(0, min(h - 2, box[1] - pad)))
    x2 = int(max(x1 + 2, min(w, box[2] + pad)))
    y2 = int(max(y1 + 2, min(h, box[3] + pad)))

    sx1, sy1 = int(round(x1 - dx)), int(round(y1 - dy))
    sx2, sy2 = sx1 + (x2 - x1), sy1 + (y2 - y1)
    if sx1 < 0 or sy1 < 0 or sx2 > w or sy2 > h:
        return 0.0

    a = gray[y1:y2, x1:x2].astype(np.float32)
    b = gray[sy1:sy2, sx1:sx2].astype(np.float32)
    if a.shape != b.shape or a.size < 64:
        return 0.0
    if a.std() < 1.0 or b.std() < 1.0:
        # Two blank areas correlate perfectly and mean nothing.
        return 0.0
    return float(cv2.matchTemplate(a, b, cv2.TM_CCOEFF_NORMED)[0, 0])


def _bbox(points: np.ndarray) -> tuple[float, float, float, float]:
    x1, y1 = points.min(axis=0)
    x2, y2 = points.max(axis=0)
    return float(x1), float(y1), float(x2), float(y2)


def _iou(a, b) -> float:
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def noise_residual(image: np.ndarray, cfg: dict) -> tuple[float, tuple | None]:
    """SRM high-pass residual inconsistency. Returns (outlier fraction, region).

    Not PRNU (D13). PRNU fingerprints a *known* sensor from about fifty
    flat-field frames; we have one image and no camera. What this measures is
    whether every region of this page carries the same noise statistic.

    As with ELA, the statistic is residual energy **relative to local detail**.
    Raw residual energy is mostly a map of where the text is - edges leave a
    large high-pass residual - so an un-normalised version flags every printed
    field and clears every blank margin, which is a picture of the layout rather
    than of the sources.
    """
    gray = to_gray(image).astype(np.float32)
    residual = cv2.filter2D(gray, -1, SRM)

    energy = _blocks(residual * residual)
    detail = _blocks(np.abs(cv2.Laplacian(gray, cv2.CV_32F)))
    if energy.size < 16:
        return 0.0, None

    busy = detail > max(1.0, float(np.median(detail)) * 0.25)
    if busy.sum() < 8:
        return 0.0, None

    ratio = energy / (detail * detail + 1.0)
    z = np.zeros(ratio.shape, dtype=np.float32)
    z[busy] = _robust_z(ratio[busy])

    outliers = np.abs(z) > cfg["noise_outlier_mad"]
    fraction = float(outliers.sum()) / float(busy.sum())
    if not outliers.any():
        return 0.0, None
    return fraction, _grid_box(z.shape, outliers, image.shape)


# ------------------------------------------------------------------ the signals

def _signal(sid: str, verdict: str, evidence: str, *, confidence: float,
            tier: int = 1, region=None, trust: str = "probabilistic",
            started: float | None = None) -> Signal:
    return Signal(
        id=sid, module="tamper", tier=tier, verdict=verdict,
        confidence=confidence, trust_class=trust, hard_fail=False,
        anchor="document", evidence=evidence, region=region,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0,
    )


def _scanner_na(sid: str, what: str) -> Signal:
    return _signal(
        sid, "not_applicable",
        f"Scanner input, so {what} does not apply - the scanner wrote this file",
        confidence=1.0, trust="arithmetic",
    )


def run_uploads(image: np.ndarray, raw: bytes | None, cfg: dict) -> list[Signal]:
    """EXIF, quantisation provenance and ELA. Tier 1, uploaded files only."""
    out = [_exif(raw), _double_jpeg(raw)]
    out.append(_ela(image, cfg))
    return out


def _exif(raw: bytes | None) -> Signal:
    started = time.perf_counter()
    sid = "tamper.digital.exif_software"
    if not raw:
        return _signal(sid, "inconclusive",
                       "The original file bytes were not available, so file "
                       "metadata could not be read", confidence=0.0, started=started)

    software = exif_software(raw)
    if software is None:
        # Absence is not innocence: EXIF is one delete away, and plenty of
        # genuine scans carry no Software tag. Calling that a pass would let a
        # forger clear a check by stripping metadata.
        return _signal(sid, "not_applicable",
                       "The file carries no EXIF software tag, which neither "
                       "supports nor disputes it", confidence=1.0,
                       trust="arithmetic", started=started)

    hit = next((e for e in EDITORS if e in software.lower()), None)
    if hit:
        return _signal(sid, "fail",
                       f"The file metadata says it was last written by "
                       f"{software!r}, which is image editing software, not a "
                       f"scanner or a camera", confidence=0.9, started=started)
    return _signal(sid, "pass",
                   f"The file metadata says it was written by {software!r}, "
                   f"which is not known editing software", confidence=0.6,
                   started=started)


def _double_jpeg(raw: bytes | None) -> Signal:
    """Quantisation table provenance.

    ponytail: this is table provenance, not DCT coefficient analysis. True
    double-compression detection reads the quantised coefficients, which needs a
    second decode of the original bytes - and CLAUDE.md rule 6 forbids a module
    re-decoding the input. The upgrade path is for the orchestrator to hand the
    coefficients down beside `ctx.image`; until then the evidence string says
    exactly what was measured and nothing more.
    """
    started = time.perf_counter()
    sid = "tamper.digital.double_jpeg"
    if not raw:
        return _signal(sid, "inconclusive",
                       "The original file bytes were not available, so the "
                       "compression history could not be read", confidence=0.0,
                       started=started)

    tables = quant_tables(raw)
    if not tables:
        return _signal(sid, "not_applicable",
                       "The upload is not a JPEG, so it carries no compression "
                       "history to analyse", confidence=1.0, trust="arithmetic",
                       started=started)

    quality, exact = standard_quality(tables[0])
    if exact:
        return _signal(sid, "pass",
                       f"The compression table is the standard one at quality "
                       f"{quality}, consistent with a camera or scanner writing "
                       f"this file once", confidence=0.7, started=started)
    return _signal(sid, "fail",
                   f"The compression table is not a standard one - closest is "
                   f"quality {quality} - which is characteristic of a file "
                   f"re-saved by editing software", confidence=0.6, started=started)


def _ela(image: np.ndarray, cfg: dict) -> Signal:
    started = time.perf_counter()
    sid = "tamper.digital.ela"
    ratio, region = ela(image)
    if region is None:
        return _signal(sid, "inconclusive",
                       "Error level analysis found no usable variation in this "
                       "image", confidence=0.0, started=started)

    if ratio >= cfg["ela_z"]:
        return _signal(sid, "fail",
                       f"One region re-compresses far differently from the rest "
                       f"of the page. Error level analysis is a visual aid, not "
                       f"a verdict - look at the highlighted area yourself",
                       confidence=min(0.9, 0.3 + ratio / 60.0),
                       region=region, started=started)
    return _signal(sid, "pass",
                   "Error levels are even across the page", confidence=0.5,
                   region=region, started=started)


def run_always(image: np.ndarray, cfg: dict) -> list[Signal]:
    """Copy-move and noise residual. Tier 2, every input, scanned or uploaded."""
    return [_copy_move(image, cfg), _noise(image, cfg)]


def _copy_move(image: np.ndarray, cfg: dict) -> Signal:
    started = time.perf_counter()
    sid = "tamper.digital.copy_move"
    count, region = copy_move(image, cfg)
    if region is not None:
        return _signal(sid, "fail",
                       f"{count} matching features share one displacement, which "
                       f"means this area appears twice on the document. Compare "
                       f"the highlighted region against the rest of the page",
                       confidence=min(0.95, 0.5 + count / 100.0),
                       tier=2, region=region, started=started)
    return _signal(sid, "pass",
                   "No region of this document is duplicated elsewhere on it",
                   confidence=0.7, tier=2, started=started)


def _noise(image: np.ndarray, cfg: dict) -> Signal:
    started = time.perf_counter()
    sid = "tamper.digital.noise_residual"
    fraction, region = noise_residual(image, cfg)
    if region is not None and fraction >= cfg["noise_outlier_frac"]:
        return _signal(sid, "fail",
                       f"{fraction * 100:.1f}% of the page carries a different "
                       f"noise pattern from the rest, which happens when part of "
                       f"an image comes from a different source",
                       confidence=min(0.9, 0.4 + fraction * 10),
                       tier=2, region=region, started=started)
    return _signal(sid, "pass",
                   "The noise pattern is consistent across the whole document",
                   confidence=0.6, tier=2, started=started)
