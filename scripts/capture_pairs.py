"""Capture the live half of the doc-vs-live calibration set. BUILD TIME ONLY.

    python scripts/capture_pairs.py 01 --consent

One run per volunteer. Writes the layout `data/tools/calibrate_face.py` reads:

    var/calibration/
      person_01/
        CONSENT.txt      when consent was taken, and the retention promise
        portrait.jpg     one frame, to be printed onto a generated card
        live_00.jpg      camera frames of the same person
        live_01.jpg
        doc.jpg          <- YOU put this here, from the scanner

**Why a script and not a folder convention.** Not for the typing. A live frame
filed under the wrong person turns a genuine pair into an impostor pair, and
that error does not raise - it silently drags the impostor distribution up,
which moves the chosen threshold *down*. A mis-filed frame therefore makes the
system more willing to accept a stranger, and nothing downstream can tell. The
second reason is the quality gate: a frame too soft or too turned to embed is
worth knowing about while the volunteer is still standing there, not on the
evening the curve is computed, when they have gone home.

The gate here is `modules.face._quality` itself - the same call the screening
path makes on a live capture - so a frame this script accepts is a frame the
pipeline accepts, by construction rather than by a second set of numbers that
drift apart.

**Consent and retention.** These are real faces, the only real biometric
anywhere in this project (CLAUDE.md rule 4). Written consent is taken on paper
before the camera opens; `--consent` is the operator asserting that has
happened. `var/` is gitignored and the script refuses to start if git disagrees.
`context/DATA.md`: stored outside the repo, deleted after the event -

    rm -rf var/calibration

**What this does not do.** It does not produce `doc.jpg`. That half is
portrait -> generated card -> printed -> scanned (D-entry in DECISIONS.md, and
`context/DATA.md`), because a volunteer's real Aadhaar may never be used. The
generator picks its portrait from the SFHQ pool by `face_seed` and cannot yet be
handed an arbitrary face, so rendering `portrait.jpg` onto a card is a small
`data/generator/render.py` change that has to land before the session.
"""
import argparse
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import face                                            # noqa: E402
from modules.face import detect as detector                         # noqa: E402

OUT = ROOT / "var" / "calibration"

CONSENT = """Face images held for face-matching threshold calibration only.

Taken     {when}
Consent   given in writing before capture, on paper, by the person photographed
Held in   var/calibration/{person}/ - outside version control
Used for  computing one number: the document-to-live cosine threshold
Deleted   after the event (context/DATA.md)

No image here is committed, published, or used to train anything.
"""


def gitignored(path: Path) -> bool:
    """Ask git, not .gitignore. The file can be edited; this cannot be wrong."""
    try:
        return subprocess.run(["git", "check-ignore", "-q", str(path)],
                              cwd=ROOT, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def usable(frame):
    """(ok, message). The screening path's own live-capture gate, reused."""
    found = detector.largest(detector.detect(frame))
    if found is None:
        return False, None, "no face found"
    ok, signal = face._quality(frame, found, "live frame", "face.live.quality",
                               "holder", live=True)
    return ok, found, signal.evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("person", help="volunteer number, e.g. 01")
    parser.add_argument("--frames", type=int, default=12,
                        help="live frames to capture; 50 people x 12 clears the "
                             "500-pair floor with room for rejects")
    parser.add_argument("--camera", type=int, default=0,
                        help="THE DEMO WEBCAM. A different camera measures a "
                             "different lens (context/DATA.md)")
    parser.add_argument("--auto", action="store_true",
                        help="capture on a timer instead of on SPACE. The "
                             "volunteer sits still and the operator does not "
                             "have to reach past them to the keyboard.")
    parser.add_argument("--interval", type=float, default=0.45,
                        help="seconds between automatic captures (--auto)")
    parser.add_argument("--countdown", type=int, default=8,
                        help="seconds before --auto starts, to sit down and "
                             "for the previous volunteer to move")
    parser.add_argument("--consent", action="store_true",
                        help="assert written consent was taken before capture")
    args = parser.parse_args()

    if not args.consent:
        print("refusing to open the camera: pass --consent, and only after "
              "written consent has actually been taken on paper.")
        return 1

    person = f"person_{args.person.zfill(2)}"
    directory = OUT / person
    if not gitignored(OUT):
        print(f"{OUT.relative_to(ROOT)} is not gitignored. Real faces must "
              f"never be committable. Fix .gitignore before capturing.")
        return 1
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "CONSENT.txt").write_text(
        CONSENT.format(when=date.today().isoformat(), person=person),
        encoding="utf-8")

    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        print(f"no camera at index {args.camera}")
        return 1

    # Ask for 720p. A laptop camera that defaults to 640x480 puts a face about
    # 200 px wide at counter distance, which clears the embedding quality gate
    # but sits under the 320 px floor the blink check needs (D52). Requesting
    # is all we can do - the driver may refuse, so the actual size is printed.
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    print(f"  camera {args.camera} at "
          f"{int(camera.get(cv2.CAP_PROP_FRAME_WIDTH))}x"
          f"{int(camera.get(cv2.CAP_PROP_FRAME_HEIGHT))}")

    have = len(list(directory.glob("live_*.jpg")))
    portrait = directory / "portrait.jpg"
    print(f"{person}: {have} frames already, portrait "
          f"{'present' if portrait.exists() else 'MISSING'}\n"
          f"  SPACE  capture      P  (re)take the portrait for the card\n"
          f"  Q      done         the window must have focus")

    started = time.time()
    last = 0.0
    rejected = 0
    try:
        while True:
            read, frame = camera.read()
            if not read:
                print("camera read failed")
                return 1
            ok, found, why = usable(frame)

            # --auto: the volunteer sits, the timer fires. Same quality gate as
            # the manual path - a frame the pipeline would refuse is refused
            # here too, it is just not a keypress that decides when to try.
            if args.auto:
                waited = time.time() - started
                if waited < args.countdown:
                    cv2.putText(frame.copy(), "", (0, 0),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 1)
                    shown = frame.copy()
                    cv2.putText(shown,
                                f"{person}  starting in "
                                f"{int(args.countdown - waited) + 1}s",
                                (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 180, 220), 2)
                    cv2.imshow("calibration capture", shown)
                    if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                        break
                    continue

                if have >= args.frames:
                    print("  enough frames for this person")
                    break

                if ok and (time.time() - last) >= args.interval:
                    if not portrait.exists():
                        cv2.imwrite(str(portrait), frame)
                        print(f"  portrait -> {portrait.name}")
                    path = directory / f"live_{have:02d}.jpg"
                    cv2.imwrite(str(path), frame)
                    have += 1
                    last = time.time()
                    print(f"  {path.name}  ({have}/{args.frames})")
                elif not ok:
                    rejected += 1
                    if rejected % 60 == 0:
                        print(f"  waiting: {why}")

                shown = frame.copy()
                if found is not None:
                    x1, y1, x2, y2 = (int(v) for v in found["box"])
                    cv2.rectangle(shown, (x1, y1), (x2, y2),
                                  (0, 200, 0) if ok else (0, 0, 220), 2)
                cv2.putText(shown, f"{person}  {have}/{args.frames}  "
                            f"{'OK' if ok else 'REJECT'}  [auto]", (12, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                            (0, 200, 0) if ok else (0, 0, 220), 2)
                cv2.imshow("calibration capture", shown)
                if (cv2.waitKey(1) & 0xFF) in (ord("q"), 27):
                    break
                continue

            shown = frame.copy()
            if found is not None:
                x1, y1, x2, y2 = (int(v) for v in found["box"])
                cv2.rectangle(shown, (x1, y1), (x2, y2),
                              (0, 200, 0) if ok else (0, 0, 220), 2)
            cv2.putText(shown, f"{person}  {have}/{args.frames}  "
                        f"{'OK' if ok else 'REJECT'}", (12, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 200, 0) if ok else (0, 0, 220), 2)
            cv2.imshow("calibration capture", shown)

            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key not in (ord(" "), ord("p")):
                continue

            if not ok:
                # The volunteer is still here. Say what is wrong, in the same
                # words the officer would see, and let them try again.
                print(f"  rejected: {why}")
                continue

            if key == ord("p"):
                cv2.imwrite(str(portrait), frame)
                print(f"  portrait -> {portrait.name}")
                continue

            path = directory / f"live_{have:02d}.jpg"
            cv2.imwrite(str(path), frame)
            have += 1
            print(f"  {path.name}  ({have}/{args.frames})")
            if have >= args.frames:
                print("  enough frames for this person")
            time.sleep(0.15)          # one keypress is one frame, not five
    finally:
        camera.release()
        cv2.destroyAllWindows()

    missing = []
    if not portrait.exists():
        missing.append("portrait.jpg (the card cannot be printed without it)")
    if have < args.frames:
        missing.append(f"{args.frames - have} more live frames")
    print(f"\n{person}: {have} live frames"
          + ("\n  STILL NEEDED: " + "; ".join(missing) if missing else ""))
    print(f"  scan the printed card into {directory.relative_to(ROOT)}\\doc.jpg")
    return 0


if __name__ == "__main__":
    sys.exit(main())
