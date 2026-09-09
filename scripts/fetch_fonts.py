"""Fetch the typefaces the document generator renders with. BUILD TIME ONLY.

    python scripts/fetch_fonts.py

Nothing in the screening path reads these - they exist so `data/generator/`
can draw a document that looks printed rather than plotted.

**Why not a system font.** Windows ships Nirmala UI, which would render
Devanagari perfectly well and cost nothing. It also has no licence line for the
provenance slide, is not on the demo machine by construction, and makes the
generator produce different output on different boxes. Noto is SIL Open Font
License 1.1, redistributable, and identical everywhere.

**Why not OpenCV.** `cv2.putText` has Hershey stroke fonts only - single-weight
vector strokes that look nothing like print - and no Indic shaping at all. The
`aadhaar`, `voter_id` and `dl` profiles declare `ocr_lang: [en, hi]`, and a
generator that cannot draw Devanagari cannot produce a card for any of them.

**The MRZ.** Real OCR-B is a licensed typeface. We render the machine-readable
zone in a free monospace face instead, and that is a stated limitation rather
than a hidden one: `tamper.physical.ocrb_conformance` measures glyph *height
uniformity within a line*, which a monospace face satisfies exactly as OCR-B
does, so the check is exercised honestly. What it does not test is typeface
identity, which we could not test anyway without the licensed original.
"""
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "data" / "templates" / "fonts"

NOTO = "https://github.com/notofonts/notofonts.github.io/raw/main/fonts/"

#: filename -> (url, what it is used for, licence)
WANTED = {
    "NotoSans-Regular.ttf": (
        NOTO + "NotoSans/hinted/ttf/NotoSans-Regular.ttf",
        "Latin body text on every document", "OFL-1.1"),
    "NotoSans-Bold.ttf": (
        NOTO + "NotoSans/hinted/ttf/NotoSans-Bold.ttf",
        "headings, document titles, field labels", "OFL-1.1"),
    "NotoSansDevanagari-Regular.ttf": (
        NOTO + "NotoSansDevanagari/hinted/ttf/NotoSansDevanagari-Regular.ttf",
        "Hindi text on Aadhaar, Voter ID and DL", "OFL-1.1"),
    "NotoSansMono-Regular.ttf": (
        NOTO + "NotoSansMono/hinted/ttf/NotoSansMono-Regular.ttf",
        "the MRZ strip, standing in for OCR-B", "OFL-1.1"),
}


def fetch(url: str, target: Path, tries: int = 4) -> bool:
    """Download with retries. DNS on this network drops often enough to matter."""
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
            if len(data) < 10_000:
                raise ValueError(f"only {len(data)} bytes; not a font")
            target.write_bytes(data)
            return True
        except Exception as exc:                                # noqa: BLE001
            print(f"    attempt {attempt}/{tries}: {type(exc).__name__}")
            if attempt < tries:
                time.sleep(3)
    return False


def main() -> int:
    FONTS.mkdir(parents=True, exist_ok=True)
    missing = []

    for name, (url, purpose, licence) in WANTED.items():
        target = FONTS / name
        if target.exists() and target.stat().st_size > 10_000:
            print(f"  {name:34s} already here ({target.stat().st_size / 1e3:.0f} kB)")
            continue
        print(f"  {name:34s} {purpose}")
        if fetch(url, target):
            print(f"  {'':34s} -> {target.stat().st_size / 1e3:.0f} kB, {licence}")
        else:
            missing.append(name)

    (FONTS / "PROVENANCE.md").write_text(
        "# Fonts\n\n"
        "Fetched by `scripts/fetch_fonts.py`. Build time only - the screening\n"
        "image never reads these.\n\n"
        "| File | Used for | Licence |\n|---|---|---|\n"
        + "".join(f"| `{n}` | {p} | {lic} |\n"
                 for n, (_u, p, lic) in WANTED.items())
        + "\nAll four are from the Noto project, SIL Open Font License 1.1,\n"
          "redistributable with the software.\n\n"
          "The MRZ is rendered in Noto Sans Mono, **not** in OCR-B, which is a\n"
          "licensed typeface. `tamper.physical.ocrb_conformance` measures glyph\n"
          "height uniformity within a printed line, which a monospace face\n"
          "satisfies exactly as OCR-B does; typeface identity is not tested and\n"
          "could not be without the licensed original.\n",
        encoding="utf-8")

    if missing:
        print(f"\ncould not fetch: {', '.join(missing)}")
        print("the generator needs all four. Re-run when the network is back.")
        return 1
    print(f"\nall fonts in {FONTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
