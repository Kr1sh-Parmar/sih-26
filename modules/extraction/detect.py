"""Field detection. One YOLOv11 ONNX model, 22 classes, six document types.

Not six detectors (D17). Shared classes - name, dob, photo, signature appear on
all six - generalise better from pooled data than six small models each seeing
200 images, and it is one warm session instead of six.

Output here is `ctx.field_boxes`, which three other things already consume:
OCR crops from it, Layer B turns a forbidden class appearing in it into a
signal, and fusion resolves region anchors to field anchors by IoU against it.
So this module locates; it does not read and it does not judge.
"""
import time

import cv2
import numpy as np

from core.profiles import field_label
from core.registry import FIELD_DETECTOR, ModelMissing, metadata, session
from fusion.context import ScreeningContext
from fusion.signal import Signal

#: Below this a box is noise. Deliberately low - a missed field costs coverage
#: and an officer a re-capture, while a spurious box costs one OCR crop that
#: then fails to normalise and is discarded anyway.
CONF_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45

#: Fallback only. The real list comes from the exported metadata, because the
#: class order is the dataset's and a mismatch silently mislabels every field.
DEFAULT_IMGSZ = 640


def letterbox(image: np.ndarray, size: int) -> tuple[np.ndarray, float, int, int]:
    """Resize preserving aspect, pad to square. Returns (padded, scale, dx, dy).

    Squashing to a square instead would distort glyph aspect ratio, and the
    crops this produces are what OCR then has to read.
    """
    h, w = image.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = round(w * scale), round(h * scale)
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((size, size, 3), 114, dtype=np.uint8)
    dx, dy = (size - nw) // 2, (size - nh) // 2
    canvas[dy:dy + nh, dx:dx + nw] = resized
    return canvas, scale, dx, dy


def _decode(raw: np.ndarray, n_classes: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """YOLOv11 head to (boxes_xywh, scores, class_ids).

    The export is (1, 4+nc, anchors): four box terms then one score per class,
    no objectness. A test asserts this against the real file rather than
    trusting it - a transposed head would produce plausible boxes with wrong
    labels, which is the worst kind of wrong here.
    """
    pred = raw[0]
    if pred.shape[0] != 4 + n_classes and pred.shape[1] == 4 + n_classes:
        pred = pred.T          # some exporters emit (anchors, 4+nc)
    pred = pred.T              # -> (anchors, 4+nc)

    boxes = pred[:, :4]
    scores_all = pred[:, 4:]
    class_ids = scores_all.argmax(axis=1)
    scores = scores_all[np.arange(len(scores_all)), class_ids]
    return boxes, scores, class_ids


def detect(image: np.ndarray, conf: float = CONF_THRESHOLD) -> list[dict]:
    """Run the detector. Returns [{class, confidence, box}] in image pixels."""
    meta = metadata(FIELD_DETECTOR)
    names = meta.get("classes")
    if not names:
        raise ModelMissing(
            f"{FIELD_DETECTOR}.json has no class list; re-export with "
            f"data/tools/train_fields.py so the label order is recorded"
        )
    size = int(meta.get("imgsz", DEFAULT_IMGSZ))

    padded, scale, dx, dy = letterbox(image, size)
    blob = padded[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32) / 255.0

    sess = session(FIELD_DETECTOR)
    raw = sess.run(None, {sess.get_inputs()[0].name: blob})[0]
    boxes, scores, class_ids = _decode(raw, len(names))

    keep = scores >= conf
    boxes, scores, class_ids = boxes[keep], scores[keep], class_ids[keep]
    if len(boxes) == 0:
        return []

    # xywh (letterboxed pixels) -> xyxy (original image pixels)
    xy = boxes[:, :2] - boxes[:, 2:4] / 2
    wh = boxes[:, 2:4]
    rects = np.column_stack([xy, wh])

    indices = cv2.dnn.NMSBoxes(rects.tolist(), scores.tolist(), conf, IOU_THRESHOLD)
    if len(indices) == 0:
        return []

    h, w = image.shape[:2]
    found = []
    for i in np.array(indices).ravel():
        x, y, bw, bh = rects[i]
        x1, y1 = (x - dx) / scale, (y - dy) / scale
        x2, y2 = (x + bw - dx) / scale, (y + bh - dy) / scale
        found.append({
            "class": names[int(class_ids[i])],
            "confidence": float(scores[i]),
            "box": (
                max(0.0, min(x1, w)), max(0.0, min(y1, h)),
                max(0.0, min(x2, w)), max(0.0, min(y2, h)),
            ),
        })
    return found


def best_per_class(found: list[dict]) -> dict:
    """One box per class - the most confident.

    `ctx.field_boxes` is a mapping, and a document has one date of birth. Two
    boxes for one field means the detector is unsure, and the officer is better
    served by the confident one plus a lower confidence score than by an
    arbitrary pick between them.
    """
    best: dict[str, dict] = {}
    for item in found:
        current = best.get(item["class"])
        if current is None or item["confidence"] > current["confidence"]:
            best[item["class"]] = item
    return best


def run(ctx: ScreeningContext) -> list[Signal]:
    """Populate ctx.field_boxes. Returns detection signals only.

    Per-field read confidence is OCR's business; what this reports is whether
    the field was *located*, which is a different failure the officer can act
    on differently - a field that was never found means a bad crop or the wrong
    document type, not a smudged value.
    """
    started = time.perf_counter()
    source = ctx.warped if ctx.warped is not None else ctx.image

    try:
        found = detect(source)
    except ModelMissing:
        return []                # extraction.run falls back to inconclusive
    except Exception as exc:     # noqa: BLE001
        return [Signal(
            id="extraction.doctype.confidence", module="extraction", tier=1,
            verdict="inconclusive", confidence=0.0, trust_class="probabilistic",
            hard_fail=False, anchor="document",
            evidence=f"The field detector could not run on this capture: {exc}",
            latency_ms=int((time.perf_counter() - started) * 1000),
        )]

    best = best_per_class(found)
    ctx.field_boxes.update({k: v["box"] for k, v in best.items()})

    ms = int((time.perf_counter() - started) * 1000)
    declared = ctx.profile["extract"]["detector_classes"]

    signals = []
    for name in declared:
        item = best.get(name)
        if item is None:
            continue     # not located; extraction.run reports it as unread
        signals.append(Signal(
            id=f"extraction.field.{name}.confidence", module="extraction", tier=1,
            verdict="pass", confidence=item["confidence"],
            trust_class="probabilistic", hard_fail=False,
            anchor=f"field:{name}",
            evidence=f"Located the {field_label(name)} on the document, "
                     f"confidence {item['confidence'] * 100:.0f}%",
            region=item["box"], latency_ms=ms,
        ))
    return signals
