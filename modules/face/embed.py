"""Face embedding. ArcFace, 512-d, cosine.

Alignment is not optional and it is not cosmetic. ArcFace was trained on crops
warped so that the eyes, nose and mouth corners land on five fixed positions in
a 112x112 frame; feeding it a raw bounding-box crop instead moves every face
some distance in embedding space, and it moves *genuine* pairs further apart
than impostor pairs, because a genuine pair is two different captures at two
different angles. Skipping alignment therefore looks like a small shortcut and
behaves like a threshold that rejects real travellers.

The output is a cosine and nothing else. There is no percentage anywhere in this
module, deliberately - see `modules/face/__init__.py` and D10.
"""
import cv2
import numpy as np

from core.registry import FACE_EMBEDDING, ModelMissing, available, metadata, session

#: Where ArcFace expects the five landmarks to land in a 112x112 crop. These are
#: the reference points the model was trained against; they are a property of
#: the model, not a choice.
REFERENCE = np.array([
    [38.2946, 51.6963],     # left eye
    [73.5318, 51.5014],     # right eye
    [56.0252, 71.7366],     # nose tip
    [41.5493, 92.3655],     # left mouth corner
    [70.7299, 92.2041],     # right mouth corner
], dtype=np.float32)

CROP = 112


def align(image: np.ndarray, landmarks: np.ndarray, size: int = CROP) -> np.ndarray:
    """Warp a face onto the reference landmarks. Similarity transform only.

    Similarity - rotate, scale, translate - and never a full affine. An affine
    fit has enough freedom to shear a face into the reference points, which
    makes two different people's crops more alike than they should be, in the
    direction that admits impostors.
    """
    points = np.asarray(landmarks, dtype=np.float32).reshape(5, 2)
    reference = REFERENCE * (size / CROP)
    matrix, _inliers = cv2.estimateAffinePartial2D(
        points, reference, method=cv2.LMEDS)
    if matrix is None:
        raise ValueError("the five landmarks are degenerate; cannot align")
    return cv2.warpAffine(image, matrix, (size, size), flags=cv2.INTER_LINEAR,
                          borderValue=0)


def embed(crop: np.ndarray) -> np.ndarray:
    """An aligned 112x112 BGR crop to a unit-length 512-d vector."""
    if not available(FACE_EMBEDDING):
        raise ModelMissing("the face embedding model is not deployed")

    size = int(metadata(FACE_EMBEDDING).get("imgsz", CROP))
    if crop.shape[:2] != (size, size):
        crop = cv2.resize(crop, (size, size), interpolation=cv2.INTER_LINEAR)

    blob = crop[:, :, ::-1].transpose(2, 0, 1)[None].astype(np.float32)
    blob = (blob - 127.5) / 127.5

    sess = session(FACE_EMBEDDING)
    vector = sess.run(None, {sess.get_inputs()[0].name: blob})[0].reshape(-1)
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("the embedding model returned a zero vector")
    # Unit length, so a dot product is the cosine and the gallery can compare
    # without renormalising every row it reads.
    return (vector / norm).astype(np.float32)


def of(image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """Detect-to-embedding in one step: align, then embed."""
    return embed(align(image, landmarks))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine between two embeddings. Both are already unit length."""
    a = np.asarray(a, dtype=np.float32).ravel()
    b = np.asarray(b, dtype=np.float32).ravel()
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a / na, b / nb))
