# Fonts

Fetched by `scripts/fetch_fonts.py`. Build time only - the screening
image never reads these.

| File | Used for | Licence |
|---|---|---|
| `NotoSans-Regular.ttf` | Latin body text on every document | OFL-1.1 |
| `NotoSans-Bold.ttf` | headings, document titles, field labels | OFL-1.1 |
| `NotoSansDevanagari-Regular.ttf` | Hindi text on Aadhaar, Voter ID and DL | OFL-1.1 |
| `NotoSansMono-Regular.ttf` | the MRZ strip, standing in for OCR-B | OFL-1.1 |

All four are from the Noto project, SIL Open Font License 1.1,
redistributable with the software.

The MRZ is rendered in Noto Sans Mono, **not** in OCR-B, which is a
licensed typeface. `tamper.physical.ocrb_conformance` measures glyph
height uniformity within a printed line, which a monospace face
satisfies exactly as OCR-B does; typeface identity is not tested and
could not be without the licensed original.
