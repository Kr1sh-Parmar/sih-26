import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(12.6, 10.2, ylo=-17, yhi=104)

X = [1.5, 26.5, 51.5, 75.0]
W = [23.0, 23.0, 22.0, 23.5]
HEAD = ["WHAT GOES IN", "MODEL  /  STEP", "WHAT COMES OUT", "WHERE IT LANDS"]
for x, w, h in zip(X, W, HEAD):
    ax.text(x + 1, 96.5, h, fontsize=6.8, weight="bold", color=IRIS_INK)

ML = "#e9f3ef"; ML_E = "#8fc0b0"      # a learned model
NM = "#fdf6e3"; NM_E = "#d9b95c"      # deterministic, no model

rows = [
    ("ctx.image\nfull page, BGR\nlongest edge ≤ 1000 px",
     "YOLOv11s\nfield detector\n640 px · int8 ONNX", ML, ML_E,
     "22-class boxes\n+ confidence\n(person_photo, mrz,\ndob, id_number, …)",
     "ctx.field_boxes\nDrives every crop below.\nAbsent today — training\non an external GPU."),

    ("crop of one field box",
     "PP-OCRv4 rec\nvia RapidOCR\nint8 ONNX", ML, ML_E,
     "text string\n+ confidence 0-1",
     "extraction.ocr.<field>.confidence\n→ normalise → ctx.fields\nsource = ocr"),

    ("same crop, when the\nLatin pass returns empty\n(aadhaar · voter_id · dl)",
     "PP-OCRv3\nDevanagari rec\n9 MB ONNX", ML, ML_E,
     "Devanagari text\n+ confidence",
     "Same signal id.\nFallback only — never a\nsecond opinion."),

    ("bottom 25 % of the page\n(ICAO fixes the position)\nor the mrz box if located",
     "PP-OCRv4\n+ OCR-B charset gate\n+ geometry gate", ML, ML_E,
     "2 × 44 character strip,\nor nothing at all",
     "extraction.ocr.mrz.confidence\n→ validation.mrz.checkdigit.*\nFive ICAO check digits."),

    ("qr_code region,\nor a scan of the page",
     "QR decode\nno model —\ndeterministic", NM, NM_E,
     "signed envelope\n{payload, sig, issuer}",
     "validation.signature.valid\nvalidation.signature.issuer_trusted\nEd25519 vs trust anchor."),

    ("full page, only when\nnothing was located and\nthe MRZ was not read",
     "Florence-2\n<OCR_WITH_REGION>\n8 s hard ceiling", ML, ML_E,
     "free text +\ngrounded regions",
     "→ checksum ratifier →\nextraction.vlm.ratified\nsource = vlm, never disputes."),

    ("ctx.image",
     "SCRFD detector\nconf ≥ 0.35\nONNX", ML, ML_E,
     "face boxes +\n5 landmarks each",
     "face.doc.detected\nface.doc.quality (blur, size, pose)"),

    ("aligned 112 × 112 BGR crop\nwarped onto the 5 landmarks",
     "ArcFace\nembedding\nONNX", ML, ML_E,
     "512-d vector,\nunit length",
     "face.match.cosine\ncos(doc, live) vs threshold\n+ margin shown to the officer."),

    ("face crop at 2.7 ×\nthe detected box\n(live frame only)",
     "MiniFASNet\npassive liveness\nApache-2.0 ONNX", ML, ML_E,
     "liveness score 0-1",
     "face.liveness.passive\nlive 0.973 · print 0.001 · screen 0.001"),

    ("512-d embedding\n+ the stored gallery",
     "cosine scan\nno model —\ndeterministic", NM, NM_E,
     "hits above 0.45",
     "face.gallery.duplicate  (Tier 2)\nSame face, different document."),
]

y = 94
for a, m, mf, me, o, dest in rows:
    h = 8.4
    box(ax, X[0], y - h, W[0], h, a, fill=WHITE, edge=IRIS, lw=0.9, size=6.1, radius=1.0)
    box(ax, X[1], y - h, W[1], h, m, fill=mf, edge=me, lw=1.2, size=6.3,
        weight="bold", radius=1.0)
    box(ax, X[2], y - h, W[2], h, o, fill=WHITE, edge=IRIS, lw=0.9, size=6.1, radius=1.0)
    ax.text(X[3] + 0.6, y - h / 2, dest, fontsize=5.9, color=IRIS_INK,
            va="center", ha="left", linespacing=1.6)
    for i in (0, 1, 2):
        arrow(ax, X[i] + W[i], y - h / 2, X[i + 1] - 0.4, y - h / 2,
              color=IRIS, lw=0.9)
    y -= h + 1.2

ax.add_patch(FancyBboxPatch((1.5, -11.5), 97, 7.2,
             boxstyle="round,pad=0,rounding_size=1.2", linewidth=0, facecolor="#f0e8f3"))
ax.text(3.5, -6.4, "THE RULE THAT MAKES THIS SAFE", fontsize=6.6, weight="bold", color=IRIS_INK)
ax.text(3.5, -9.3,
        "Every value carries the source that produced it — ocr · mrz · vlm · qr — and only ink counts as printed. "
        "A value lifted from the QR can never corroborate the QR,\nand a fallback read can fill a gap but may never "
        "contradict a signature. That single rule is what stopped a retyped card scoring GREEN twice (D48, D49).",
        fontsize=6.2, color=INTAGLIO, va="center", linespacing=1.6)

ax.add_patch(FancyBboxPatch((26.5, 99.6), 23, 3.4, boxstyle="round,pad=0,rounding_size=0.8",
             linewidth=0, facecolor=ML))
ax.text(28, 101.3, "green = a learned model", fontsize=5.8, color=CLEAR, va="center")
ax.add_patch(FancyBboxPatch((51.5, 99.6), 22, 3.4, boxstyle="round,pad=0,rounding_size=0.8",
             linewidth=0, facecolor=NM))
ax.text(53, 101.3, "gold = deterministic, no model", fontsize=5.8, color=SECONDARY, va="center")

caption(ax, "Figure 7b — Every model in the screening path: what it is fed, what it returns, and which signal carries the result.", y=-15.5)
save(fig, "fig10_model_io.png")
