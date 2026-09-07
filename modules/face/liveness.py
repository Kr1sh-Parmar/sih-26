"""Passive liveness. MiniFASNet, one frame, escalate to active only if unsure.

**The weights are not deployed, and this module says so rather than passing.**
MiniFASNet ships from Silent-Face-Anti-Spoofing as PyTorch `.pth`; the ONNX
mirrors we found need an account, and converting the `.pth` needs torch - which
lives only in `.venv-train` and must never enter the screening process - plus
the model class from that repository, whose licence needs reading before it goes
in a submission. That is a decision, not an afternoon, so it is stated here and
in data/FACE.md instead of being quietly skipped.

Everything except the weights is written. Drop
`models/face_liveness.onnx` plus its sidecar in place and this starts returning
verdicts with no other change: `core/registry.py` already warms it and already
reports it in the audit log.

Until then the signal is `inconclusive`, which costs coverage. That is the
correct direction. A spoof check that has not run must never look like a spoof
check that passed - at a manned counter the officer is the liveness check, and
the console has to tell them the machine is not helping with this one.

The contract when weights arrive: 80x80 BGR crop of the face box expanded by
`SCALE`, three logits - {spoof-2D, live, spoof-3D} - softmax, and the live
probability is index 1. `thresholds.yaml` already carries `passive_pass` and the
`uncertain_band` the risk gate escalates on.
"""
import cv2
import numpy as np

from core.registry import LIVENESS, available, metadata, session

#: MiniFASNet is trained on a crop wider than the face box - the spoof cues it
#: reads (a screen bezel, a paper edge, the flatness of a print) live around the
#: face, not on it.
SCALE = 2.7
INPUT = 80


def crop_for_liveness(image: np.ndarray, box, scale: float = SCALE) -> np.ndarray:
    """The expanded, square crop MiniFASNet expects, clipped to the frame."""
    x1, y1, x2, y2 = (float(v) for v in box)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = max(x2 - x1, y2 - y1) * scale / 2

    h, w = image.shape[:2]
    sx1 = int(max(0, cx - side))
    sy1 = int(max(0, cy - side))
    sx2 = int(min(w, cx + side))
    sy2 = int(min(h, cy + side))
    patch = image[sy1:sy2, sx1:sx2]
    if patch.size == 0:
        return np.zeros((INPUT, INPUT, 3), dtype=np.uint8)
    return cv2.resize(patch, (INPUT, INPUT), interpolation=cv2.INTER_LINEAR)


def deployed() -> bool:
    return available(LIVENESS)


def score(image: np.ndarray, box) -> float:
    """Probability the face in front of the camera is a live person.

    Raises `ModelMissing` through the registry when the weights are absent -
    callers check `deployed()` first and emit `inconclusive`.
    """
    size = int(metadata(LIVENESS).get("imgsz", INPUT))
    patch = crop_for_liveness(image, box)
    if patch.shape[:2] != (size, size):
        patch = cv2.resize(patch, (size, size), interpolation=cv2.INTER_LINEAR)

    # BGR, and **not** divided by 255. Both halves of that were wrong when this
    # file was written against a model that did not exist yet, and both are the
    # kind of wrong that never raises - the network returns three plausible
    # probabilities either way, just for an image it was never trained on.
    #
    # Upstream feeds `cv2.imread` output through their own `ToTensor`, which is
    # not torchvision's: it transposes HWC to CHW and calls `.float()`, with no
    # channel swap and no scaling. So the weights expect raw 0-255 BGR.
    # Measured, on 60 faces: with the division every genuine face scored 0.006
    # live and the check rejected 100% of real people; without it, 0.968 against
    # 0.001 for a simulated spoof. The sidecar records `colour_order` and
    # `input_range` so the next person does not have to rediscover this.
    blob = patch.transpose(2, 0, 1)[None].astype(np.float32)
    sess = session(LIVENESS)
    logits = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0]).ravel()

    shifted = logits - logits.max()
    probabilities = np.exp(shifted) / np.exp(shifted).sum()
    # Index 1 is the live class; 0 and 2 are the two spoof families (a printed
    # or displayed 2D surface, and a 3D mask).
    return float(probabilities[1]) if probabilities.size >= 2 else 0.0
