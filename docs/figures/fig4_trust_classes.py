import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(11, 3.9, ylo=0)

cols = [
    ("CRYPTOGRAPHIC", "Certain", "#e9f3ef", "#8fc0b0", CLEAR,
     "Ed25519 signature verifies\nagainst a trusted key.",
     "Cannot be wrong.\nSuppresses probabilistic\ndisputes — but only on\nfields it was checked against."),
    ("ARITHMETIC", "Deterministic", "#fdf6e3", "#d9b95c", SECONDARY,
     "A calculation. No model,\nno key, no training data.",
     "MRZ check digits (ICAO 9303)\nVerhoeff · PAN structure\ndate ordering · validity"),
    ("PROBABILISTIC", "Can be wrong", "#f6eef7", "#b39bbe", IRIS_INK,
     "Inference. A model, or a\nheuristic over pixels.",
     "Tamper heuristics · face match\nOCR confidence · liveness\nAlways labelled as such."),
]
x = 3
for title, sub, fill, edge, fg in [(c[0], c[1], c[2], c[3], c[4]) for c in cols]:
    pass
for i, (title, sub, fill, edge, fg, what, egs) in enumerate(cols):
    x = 3 + i * 32.5
    box(ax, x, 12, 30, 76, "", fill=fill, edge=edge, lw=1.4, radius=2.0)
    ax.text(x + 15, 80, title, ha="center", fontsize=9.5, weight="bold", color=fg)
    ax.text(x + 15, 72, sub, ha="center", fontsize=7.2, color=fg, style="italic")
    ax.plot([x + 4, x + 26], [66, 66], color=edge, lw=1.0)
    ax.text(x + 15, 55, what, ha="center", va="center", fontsize=7.4,
            color=INTAGLIO, linespacing=1.6)
    ax.text(x + 15, 30, egs, ha="center", va="center", fontsize=6.9,
            color=IRIS_INK, linespacing=1.7)

caption(ax, "Figure 4 — Three trust classes. Every verdict says which one it came from.", y=2.0)
save(fig, "fig4_trust_classes.png")
