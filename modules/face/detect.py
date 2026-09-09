"""Face detection. SCRFD, one ONNX session, one pass.

**One detection pass.** `MODULES.md` lists running a detector twice per face as
a pitfall for a reason: the usual way to get here is calling RetinaFace to find
the face and then an analysis pipeline that detects again internally, which is
two detections per image and four per comparison, on the CPU, inside a 320 ms
budget.

SCRFD emits three strides, and each stride emits a score, a distance-form box
and five landmarks per anchor. The landmarks are the reason this detector is
worth its bytes: ArcFace wants an aligned 112x112 crop, and alignment needs the
eyes, nose and mouth corners. A detector that returned only a box would force a
second landmark model.

The fallback chain is `MODULES.md`'s and it ends in a statement, never silence:

    detect -> denoised retry -> the known photo region -> `face not found`

The denoised retry exists because of two real document surfaces: the Aadhaar
background pattern and passport laminate reflection both defeat a first pass on
captures a human reads without trouble.
"""
import cv2
import numpy as np

from core.decode import to_gray
from core.registry import FACE_DETECTOR, ModelMissing, available, metadata, session

#: SCRFD's three feature strides, each with two anchors per cell. Fixed by the
#: architecture, not a tunable.
STRIDES = (8, 16, 32)
ANCHORS = 2

#: Below this a detection is noise. Faces on documents are small, printed and
#: soft, so this is looser than a webcam default would be - and a wrong box is
#: cheap here because the quality gate and the embedding both then disagree.
CONF_THRESHOLD = 0.35
IOU_THRESHOLD = 0.4

DEFAULT_IMGSZ = 320


def _anchor_centres(height: int, width: int, stride: int) -> np.ndarray:
    """(x, y) centres for every anchor at this stride, in network pixels."""
    ys, xs = np.mgrid[0:height, 0:width]
    centres = np.stack([xs, ys], axis=-1).astype(np.float32) * stride
    return np.repeat(centres.reshape(-1, 2), ANCHORS, axis=0)


def _distance_to_box(centres: np.ndarray, distances: np.ndarray) -> np.ndarray:
    """SCRFD predicts left/top/right/bottom distances from the anchor centre."""
    x1 = centres[:, 0] - distances[:, 0]
    y1 = centres[:, 1] - distances[:, 1]
    x2 = centres[:, 0] + distances[:, 2]
    y2 = centres[:, 1] + distances[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance_to_points(centres: np.ndarray, distances: np.ndarray) -> np.ndarray:
    """Five landmarks, each an (dx, dy) offset from the anchor centre."""
    points = distances.reshape(-1, 5, 2).copy()
    points[:, :, 0] += centres[:, None, 0]
    points[:, :, 1] += centres[:, None, 1]
    return points


def _letterbox_square(image: np.ndarray, size: int):
    """Resize into a square canvas, top-left anchored, as SCRFD expects."""
    h, w = image.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    canvas = np.zeros((size, size, 3), dtype=np.uint8)
    canvas[:nh, :nw] = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, scale


def detect(image: np.ndarray, conf: float = CONF_THRESHOLD) -> list[dict]:
    """Every face in the image, most confident first.

    Each entry is {'box': (x1,y1,x2,y2), 'score': float, 'landmarks': 5x2},
    all in original-image pixels.
    """
    meta = metadata(FACE_DETECTOR)
    size = int(meta.get("imgsz", DEFAULT_IMGSZ))
    canvas, scale = _letterbox_square(image, size)

    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32)
    blob = (blob - 127.5) / 128.0

    sess = session(FACE_DETECTOR)
    outputs = sess.run(None, {sess.get_inputs()[0].name: blob})

    # The nine outputs arrive as three groups of three, in stride order:
    # scores for all strides, then boxes, then landmarks.
    n = len(STRIDES)
    scores, boxes, points = outputs[:n], outputs[n:2 * n], outputs[2 * n:3 * n]

    all_boxes, all_scores, all_points = [], [], []
    for index, stride in enumerate(STRIDES):
        side = size // stride
        centres = _anchor_centres(side, side, stride)
        score = scores[index].reshape(-1)
        keep = score >= conf
        if not keep.any():
            continue
        centres_kept = centres[keep]
        all_scores.append(score[keep])
        all_boxes.append(_distance_to_box(
            centres_kept, boxes[index].reshape(-1, 4)[keep] * stride))
        all_points.append(_distance_to_points(
            centres_kept, points[index].reshape(-1, 10)[keep] * stride))

    if not all_boxes:
        return []

    boxes_xyxy = np.concatenate(all_boxes) / scale
    scores_flat = np.concatenate(all_scores)
    points_all = np.concatenate(all_points) / scale

    rects = np.column_stack([boxes_xyxy[:, 0], boxes_xyxy[:, 1],
                             boxes_xyxy[:, 2] - boxes_xyxy[:, 0],
                             boxes_xyxy[:, 3] - boxes_xyxy[:, 1]])
    indices = cv2.dnn.NMSBoxes(rects.tolist(), scores_flat.tolist(),
                               conf, IOU_THRESHOLD)
    if len(indices) == 0:
        return []

    h, w = image.shape[:2]
    found = []
    for i in np.array(indices).ravel():
        x1, y1, x2, y2 = boxes_xyxy[i]
        found.append({
            "box": (float(max(0, x1)), float(max(0, y1)),
                    float(min(w, x2)), float(min(h, y2))),
            "score": float(scores_flat[i]),
            "landmarks": points_all[i].astype(np.float32),
        })
    return sorted(found, key=lambda f: -f["score"])


def largest(faces: list[dict]) -> dict | None:
    """The face the officer means.

    A document capture can catch a bystander, and a live frame usually catches
    whoever is behind the traveller in the queue. Both times the subject is the
    biggest face in frame, not the most confident one - a sharp small face
    behind the counter scores higher than the soft large one being screened.
    """
    if not faces:
        return None
    return max(faces, key=lambda f: (f["box"][2] - f["box"][0]) *
                                    (f["box"][3] - f["box"][1]))


def find(image: np.ndarray, known_region=None) -> tuple[dict | None, str]:
    """The fallback chain. Returns (face, how it was found).

    `how` is one of 'direct', 'denoised', 'region', or 'none', and it reaches
    the officer - a face located only by falling back to the printed photo box
    is a weaker result than one the detector found outright, and the evidence
    string says so rather than presenting them as the same thing.
    """
    if not available(FACE_DETECTOR):
        raise ModelMissing("the face detector is not deployed")

    face = largest(detect(image))
    if face is not None:
        return face, "direct"

    # Aadhaar's background pattern and passport laminate both defeat a first
    # pass on captures a person reads without difficulty.
    denoised = cv2.fastNlMeansDenoisingColored(image, None, 5, 5, 7, 15)
    face = largest(detect(denoised, conf=CONF_THRESHOLD * 0.8))
    if face is not None:
        return face, "denoised"

    if known_region is not None:
        x1, y1, x2, y2 = (int(v) for v in known_region)
        patch = image[max(0, y1):y2, max(0, x1):x2]
        if patch.size:
            inside = largest(detect(patch, conf=CONF_THRESHOLD * 0.6))
            if inside is not None:
                bx1, by1, bx2, by2 = inside["box"]
                inside["box"] = (bx1 + x1, by1 + y1, bx2 + x1, by2 + y1)
                inside["landmarks"] = inside["landmarks"] + np.array(
                    [x1, y1], dtype=np.float32)
                return inside, "region"

    return None, "none"


#: Face crops are measured for blur at this size, whatever size they arrived.
#: Laplacian variance is scale dependent - the same face photographed closer
#: scores *lower*, because the same edges are spread across more pixels. An
#: absolute threshold on the raw crop therefore penalises the best captures and
#: rewards the small distant ones, which is exactly backwards. Normalising to
#: the size the embedder will see makes the number comparable.
SHARPNESS_REFERENCE = 112


def sharpness_of(image: np.ndarray, box) -> float:
    """Blur of the face crop at a fixed scale, not of the whole page.

    A crisp document with a soft portrait must not read as a sharp face - that
    is the capture whose embedding is a guess.
    """
    x1, y1, x2, y2 = (int(v) for v in box)
    patch = image[max(0, y1):y2, max(0, x1):x2]
    if patch.size == 0 or min(patch.shape[:2]) < 4:
        return 0.0
    reference = cv2.resize(to_gray(patch), (SHARPNESS_REFERENCE,
                                            SHARPNESS_REFERENCE),
                           interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(reference, cv2.CV_64F).var())
