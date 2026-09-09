import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(11, 7.0, ylo=-8)

stages = [
    ("1  CAPTURE", "scanner · camera · webcam", "JPEG/PNG bytes + doc_type", GUILLOCHE),
    ("2  DECODE ONCE", "core/decode.py — max edge 1000 px", "ctx.image  (one ndarray, forever)", BLOOM),
    ("3  PROFILE ROUTE", "profiles/<type>.yaml", "fields · weights · hard_fail · thresholds", BLOOM),
    ("4  EXTRACTION", "YOLOv11s 22-class · PP-OCRv4 · QR · MRZ\nFlorence-2 fallback (8 s ceiling)", "ctx.fields  {name: NormalizedField}", "#e9f3ef"),
    ("5  VALIDATION  A–F", "Ed25519 · Verhoeff · ICAO check digits\nVIZ↔MRZ · trust propagation · watchlist", "list[Signal]  trust: crypto / arithmetic", "#e9f3ef"),
    ("6  TAMPERING", "copy-move (ORB) · ELA · SRM · double-JPEG\nfont CV · guilloche · ghost portrait", "list[Signal]  trust: probabilistic", "#e9f3ef"),
    ("7  FACE", "SCRFD detect · ArcFace 512-d · MiniFASNet", "list[Signal] + embedding", "#e9f3ef"),
    ("8  RISK GATE", "escalation policy — ~15 % of documents", "tier-2 signals, or nothing", BLOOM),
    ("9  FUSION", "anchor grouping · noisy-OR · trust precedence\ncoverage floor 0.70 · weighted sum", "Verdict + evidence cards", INTAGLIO),
]
y = 92
for i, (name, how, out, colour) in enumerate(stages):
    fg = PAPER if colour == INTAGLIO else INTAGLIO
    box(ax, 2, y - 8.4, 40, 8.4, "", fill=colour, edge=INTAGLIO if colour != INTAGLIO else INTAGLIO,
        lw=1.1, radius=1.4)
    ax.text(4, y - 2.9, name, fontsize=7.6, weight="bold", color=fg, va="center")
    ax.text(4, y - 6.2, how, fontsize=6.2, color=fg if colour == INTAGLIO else IRIS_INK,
            va="center", linespacing=1.35)
    arrow(ax, 42, y - 4.2, 50, y - 4.2, color=IRIS_INK, lw=1.0)
    ax.text(51, y - 4.2, out, fontsize=6.6, color=INTAGLIO, va="center", family="DejaVu Sans")
    if i < len(stages) - 1:
        arrow(ax, 22, y - 8.4, 22, y - 10.2)
    y -= 10.2

ax.plot([48.6, 48.6], [8, 92], color=IRIS, lw=0.8, ls=(0, (3, 3)))
ax.text(49.5, 95, "WHAT COMES OUT", fontsize=7, weight="bold", color=IRIS_INK)
ax.text(3, 95, "STAGE  ·  HOW", fontsize=7, weight="bold", color=IRIS_INK)

caption(ax, "Figure 7 — Technical pipeline. Each stage's only output is a list of Signals.", y=-6.5)
save(fig, "fig7_pipeline.png")
