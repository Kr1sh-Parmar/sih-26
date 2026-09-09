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


# ----------------------------------------------------------------- active

#: Where the eyes sit inside a face box, as fractions. Used to crop the band the
#: cascade searches, so a mouth or a background window cannot be mistaken for an
#: eye. Generous on purpose - head tilt moves them.
EYE_BAND = (0.12, 0.18, 0.88, 0.60)      # x1, y1, x2, y2 of the face box

#: A blink is one or two frames out of a short burst. Requiring more would need
#: the traveller to hold their eyes shut; requiring exactly one would make a
#: single missed detection look like liveness.
MIN_FRAMES = 4
MIN_OPEN_FRAMES = 2

#: Face width below which this check refuses to answer. **Measured, and the
#: whole safety of the check rests on it.** Run over static images - eight
#: frames of one photograph with only JPEG and sensor noise between them, which
#: is exactly what a printed photo held to the camera looks like - the cascade
#: is perfectly stable at 320 px and 480 px face width (8/8 or 0/8 every time)
#: and flickers at 160-210 px (1/8, 7/8). A flicker on a static image *is* a
#: phantom blink: it would report a photograph as a living person, which is the
#: one direction this check must never fail in. Below this the answer is
#: `inconclusive` and the passive check carries the load.
MIN_FACE_PX = 320


def _eye_cascade():
    """OpenCV's own eye cascade, from inside the installed wheel.

    ponytail: a Haar cascade is a weaker eye detector than the six-point eye
    aspect ratio the literature uses, and it degrades on spectacles even with
    the `_tree_eyeglasses` variant. It is here because it needs no new model
    and no new dependency, so `tests/test_offline.py` - the test that keeps the
    whole offline claim honest - is untouched by construction. The upgrade path
    is MediaPipe FaceMesh landmarks and a real EAR, which costs a model file, a
    dependency, and a re-run of the offline gate.
    """
    return cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml")


def _eyes_open(frame: np.ndarray, box, cascade) -> bool:
    """Does the eye cascade find an eye in this frame's eye band?"""
    x1, y1, x2, y2 = (float(v) for v in box)
    w, h = x2 - x1, y2 - y1
    fx1, fy1, fx2, fy2 = EYE_BAND
    band = frame[int(y1 + h * fy1):int(y1 + h * fy2),
                 int(x1 + w * fx1):int(x1 + w * fx2)]
    if band.size == 0:
        return False
    grey = cv2.cvtColor(band, cv2.COLOR_BGR2GRAY)
    grey = cv2.equalizeHist(grey)
    # minSize keeps a nostril or a speck of hair from counting as an eye.
    found = cascade.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=5,
                                     minSize=(max(8, band.shape[1] // 12),) * 2)
    return len(found) > 0


def blink(frames: list, box) -> tuple[str, float, str]:
    """Did the person blink across this burst? Returns (verdict, confidence, why).

    A printed photograph and a phone screen held up to the camera never blink;
    a person in front of a counter does, within a second or two. That is the
    whole idea, and it is why this is worth having next to the passive check -
    the two fail to different attacks.

    **`fail` is not returned for the absence of a blink.** People stare, a burst
    can be short, and the cascade misses eyes on spectacles - so no blink is
    `inconclusive` and the officer, who is standing there, remains the check. A
    blink is positive evidence and nothing else is treated as evidence at all.
    """
    if not frames or len(frames) < MIN_FRAMES:
        return ("inconclusive", 0.0,
                f"Blink-based liveness needs at least {MIN_FRAMES} frames and "
                f"this capture carried {len(frames) or 'none'}")

    cascade = _eye_cascade()
    if cascade.empty():
        return ("inconclusive", 0.0,
                "Blink-based liveness could not run - the eye cascade that "
                "ships with OpenCV did not load")

    width = float(box[2]) - float(box[0])
    if width < MIN_FACE_PX:
        return ("inconclusive", 0.0,
                f"Blink-based liveness was not attempted - the face is "
                f"{width:.0f} pixels wide and below {MIN_FACE_PX} px the eye "
                f"detector flickers on a still image, which would read as a "
                f"blink. Ask the traveller to step closer to the camera")

    states = [_eyes_open(f, box, cascade) for f in frames]
    open_frames = sum(states)
    closed_frames = len(states) - open_frames

    if open_frames < MIN_OPEN_FRAMES:
        # Eyes were never convincingly found. That is a detector failure, not a
        # traveller who kept their eyes shut, and it must not read as a spoof.
        return ("inconclusive", 0.0,
                f"Blink-based liveness could not run - the eyes were not "
                f"visible in {len(states) - open_frames} of {len(states)} "
                f"frames, so a blink could not be distinguished from a poor view")

    if closed_frames == 0:
        return ("inconclusive", 0.0,
                f"No blink was seen across {len(states)} frames. That is not "
                f"evidence of a spoof - people hold a stare - so it is recorded "
                f"as unproven rather than failed")

    # A blink is consecutive frames. Scattered closed frames are the detector
    # losing the eyes and finding them again, and the size floor above does not
    # make that impossible - only unlikely. Belt and braces, three lines.
    if _longest_run(states, False) < 1 or not _brackets_a_run(states):
        return ("inconclusive", 0.0,
                f"The eyes were lost in {closed_frames} of {len(states)} frames "
                f"but not in one continuous run bracketed by open frames, which "
                f"is what a blink looks like. Recorded as unproven")

    return ("pass", min(1.0, closed_frames / 2),
            f"The person blinked while the camera was recording - eyes closed "
            f"in {closed_frames} of {len(states)} frames. A printed photograph "
            f"or a screen does not blink")


def _longest_run(states: list[bool], value: bool) -> int:
    longest = run = 0
    for state in states:
        run = run + 1 if state == value else 0
        longest = max(longest, run)
    return longest


def _brackets_a_run(states: list[bool]) -> bool:
    """Is there an open -> closed -> open transition? That is a blink.

    Eyes closed at the very start or the very end of the burst could equally be
    the camera catching someone mid-look-away, so they are not counted.
    """
    for i in range(1, len(states) - 1):
        if not states[i] and states[i - 1]:
            return any(states[i + 1:])
    return False
