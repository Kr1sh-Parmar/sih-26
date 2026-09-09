"""Does passive liveness actually reject a spoof? BUILD TIME ONLY.

    python scripts/eval_liveness.py --limit 120

MODULES.md is blunt: *"Test it against an actual printed photo and an actual
phone screen before demo day. Untested liveness is theatre."*

**There is no camera on this machine, so this is not that test.** What it does
instead is synthesise the physical artefacts a re-capture leaves behind and
check the model responds in the right direction and by how much. That is enough
to catch a model wired up wrong - wrong colour order, wrong crop, wrong output
index - and nowhere near enough to publish a spoof-rejection rate. The number
this prints is a **direction check**, and `data/FACE.md` says so.

The two attacks are simulated where they actually differ from a live face, which
is mostly *around* the face rather than on it. MiniFASNet crops at 2.7x the face
box precisely because the giveaways - a paper edge, a screen bezel, the flatness
of a reprint - live in that margin.

  print    tone compression, halftone dither, paper grain, a soft focus
           plane, a warm cast, and a paper edge in the margin
  screen   an RGB subpixel stripe, moiré against the pixel grid, a specular
           glare gradient, and a dark bezel at the frame edge

Real captures carry all of this plus lens, motion and lighting that no
simulation reproduces. Take the direction, not the decimal.
"""
import argparse
import glob
import random
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.profiles import load_config                              # noqa: E402
from modules.face import detect as detector                        # noqa: E402
from modules.face import liveness                                  # noqa: E402

FACES = ROOT / "data" / "raw" / "face" / "sfhq"


def print_attack(image: np.ndarray, rng: random.Random) -> np.ndarray:
    """A photograph printed on paper and held up to the camera."""
    out = image.astype(np.float32)

    # Ink cannot reach the black or the white of a screen: the tonal range
    # compresses toward the middle. This is the single strongest print cue.
    out = out * 0.74 + 40

    # Halftone. Printing reproduces continuous tone as a dot screen; at capture
    # resolution it survives as a fine periodic modulation.
    h, w = out.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]
    screen = np.sin(xs * 1.9) * np.sin(ys * 1.9) * 7.0
    out += screen[:, :, None]

    # Paper grain, and the fact that a flat sheet is uniformly in focus - a live
    # face has depth, so parts of it are not.
    out += rng.gauss(0, 1) + np.random.default_rng(rng.randint(0, 1 << 30)).normal(
        0, 3.2, out.shape)
    out = cv2.GaussianBlur(out, (0, 0), 0.9)

    # Paper is warmer than a screen and the printer's white point is not D65.
    out[:, :, 0] *= 0.95          # less blue
    out[:, :, 2] *= 1.04          # more red

    out = np.clip(out, 0, 255).astype(np.uint8)

    # The edge of the sheet, in the margin the 2.7x crop will include.
    edge = max(2, min(h, w) // 22)
    cv2.rectangle(out, (edge, edge), (w - edge, h - edge), (238, 236, 232), 3)
    return out


def screen_attack(image: np.ndarray, rng: random.Random) -> np.ndarray:
    """A photograph shown on a phone and held up to the camera."""
    out = image.astype(np.float32)
    h, w = out.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w]

    # An RGB subpixel stripe: each display pixel is three coloured cells, and a
    # camera close enough resolves the pattern.
    stripe = (xs % 3)
    out[:, :, 2] += np.where(stripe == 0, 9.0, -4.0)
    out[:, :, 1] += np.where(stripe == 1, 9.0, -4.0)
    out[:, :, 0] += np.where(stripe == 2, 9.0, -4.0)

    # Moiré - the beat between the display grid and the sensor grid.
    out += (np.sin(xs * 0.62 + ys * 0.21) * 6.5)[:, :, None]

    # Specular glare across the glass, and a display's lower effective contrast.
    glare = ((xs / max(w, 1)) * 0.6 + (ys / max(h, 1)) * 0.4)
    out += (glare * 26)[:, :, None]
    out = out * 0.86 + 26

    out = np.clip(out, 0, 255).astype(np.uint8)

    # The bezel, dark, in the margin.
    bezel = max(2, min(h, w) // 18)
    cv2.rectangle(out, (0, 0), (w - 1, h - 1), (18, 18, 20), bezel)
    return out


ATTACKS = {"print": print_attack, "screen": screen_attack}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=120)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    if not liveness.deployed():
        print("no models/face_liveness.onnx. Run:\n"
              "  .venv-train/Scripts/python scripts/convert_liveness.py")
        return 1

    files = sorted(glob.glob(str(FACES / "**" / "*.jpg"), recursive=True))
    if not files:
        print(f"no faces in {FACES}")
        return 1
    random.seed(args.seed)
    files = random.sample(files, min(args.limit, len(files)))

    cfg = load_config("thresholds")["face"]["liveness"]
    cut = float(cfg["passive_pass"])
    scores: dict[str, list[float]] = {"live": [], "print": [], "screen": []}

    print(f"scoring {len(files)} faces x 3 conditions, threshold {cut}")
    for n, path in enumerate(files, 1):
        image = cv2.imread(path)
        if image is None:
            continue
        face = detector.largest(detector.detect(image))
        if face is None:
            continue
        rng = random.Random(args.seed + n)

        scores["live"].append(liveness.score(image, face["box"]))
        for name, attack in ATTACKS.items():
            # Same box: the attack changes the pixels, not where the face is.
            scores[name].append(liveness.score(attack(image, rng), face["box"]))
        if n % 30 == 0:
            print(f"  {n}/{len(files)}")

    print(f"\n{'condition':10s} {'n':>4s} {'median':>8s} {'p10':>8s} {'p90':>8s} "
          f"{'passes as live':>15s}")
    print("-" * 60)
    for name in ("live", "print", "screen"):
        values = np.array(scores[name], dtype=float)
        if not values.size:
            continue
        rate = float((values >= cut).mean())
        print(f"{name:10s} {values.size:4d} {np.median(values):8.3f} "
              f"{np.quantile(values, 0.10):8.3f} {np.quantile(values, 0.90):8.3f} "
              f"{rate:14.1%}")

    live = np.array(scores["live"], dtype=float)
    spoof = np.array(scores["print"] + scores["screen"], dtype=float)
    if live.size and spoof.size:
        print(f"\nseparation: live median {np.median(live):.3f} vs "
              f"spoof median {np.median(spoof):.3f}")
        print(f"genuine rejected (FRR): {float((live < cut).mean()):.1%}")
        print(f"spoof accepted  (FAR):  {float((spoof >= cut).mean()):.1%}")

    print("\nThese are SIMULATED attacks. A synthesised halftone is not a print\n"
          "and a synthesised moire is not a phone screen. This checks the model\n"
          "is wired up correctly and responds in the right direction; it is not\n"
          "a spoof-rejection rate and must not be quoted as one. The real test\n"
          "needs a printer, a phone and the demo camera (MODULES.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
