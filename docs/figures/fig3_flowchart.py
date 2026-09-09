import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *
from matplotlib.patches import Polygon

fig, ax = canvas(8.6, 10.4, ylo=-6)

def diamond(x, y, w, h, text, size=6.8):
    ax.add_patch(Polygon([[x, y + h/2], [x + w/2, y + h], [x + w, y + h/2],
                          [x + w/2, y]], closed=True, facecolor=GUILLOCHE,
                         edgecolor=INTAGLIO, lw=1.2, zorder=2))
    ax.text(x + w/2, y + h/2, text, ha="center", va="center", fontsize=size,
            color=INTAGLIO, weight="bold", zorder=3, linespacing=1.4)

AMBER_F, AMBER_E = "#fdf3d9", SECONDARY
RED_F, RED_E = "#fbe9ee", DETAIN

box(ax, 28, 93, 44, 5.5, "Document placed · type selected", fill=BLOOM, size=7.5, weight="bold")
arrow(ax, 50, 93, 50, 90.5)
box(ax, 28, 85, 44, 5.5, "Decode once → quality gate", size=7.5)
arrow(ax, 50, 85, 50, 81.5)

diamond(33, 74, 34, 7, "Capture usable?")
arrow(ax, 67, 77.5, 75.6, 77.5); ax.text(68.5, 78.8, "no", fontsize=6.5, color=IRIS_INK)
box(ax, 76, 74.75, 22, 5.5, "AMBER\nre-capture", fill=AMBER_F, edge=AMBER_E, fg=AMBER_E, size=7, weight="bold")
arrow(ax, 50, 74, 50, 70.5); ax.text(51.5, 72, "yes", fontsize=6.5, color=IRIS_INK)

box(ax, 20, 62, 60, 8, "TIER 1  ·  four modules in parallel\nextraction · validation · tampering · face", size=7.2)
arrow(ax, 50, 62, 50, 58.5)
box(ax, 28, 52, 44, 6, "Every check emits a Signal\nid · verdict · trust class · evidence", fill="#f0e8f3", size=7)
arrow(ax, 50, 52, 50, 48.5)

diamond(33, 41, 34, 7, "Any hard fail?")
arrow(ax, 67, 44.5, 75.6, 44.5); ax.text(68.5, 45.8, "yes", fontsize=6.5, color=IRIS_INK)
box(ax, 76, 41.75, 22, 5.5, "RED\ndetain", fill=RED_F, edge=RED_E, fg=RED_E, size=7, weight="bold")
arrow(ax, 50, 41, 50, 37.5); ax.text(51.5, 39, "no", fontsize=6.5, color=IRIS_INK)

diamond(31, 29, 38, 7, "Coverage ≥ 0.70?")
arrow(ax, 31, 32.5, 24.4, 32.5); ax.text(25.5, 33.8, "no", fontsize=6.5, color=IRIS_INK)
box(ax, 2, 29.75, 22, 5.5, "AMBER\nre-capture", fill=AMBER_F, edge=AMBER_E, fg=AMBER_E, size=7, weight="bold")
arrow(ax, 50, 29, 50, 25.5); ax.text(51.5, 27, "yes", fontsize=6.5, color=IRIS_INK)

diamond(31, 17, 38, 7, "Risk gate escalates?")
arrow(ax, 69, 20.5, 75.6, 20.5); ax.text(70.2, 21.8, "yes", fontsize=6.5, color=IRIS_INK)
box(ax, 76, 17.75, 22, 5.5, "TIER 2\nforensics · 1:N", fill=BLOOM, size=6.8, weight="bold")
arrow(ax, 87, 17.75, 66, 13.6, rad=-0.3)
arrow(ax, 50, 17, 50, 13.6); ax.text(51.5, 15, "no", fontsize=6.5, color=IRIS_INK)

box(ax, 18, 6.5, 64, 7,
    "FUSION  ·  correlated signals grouped into findings\na cryptographic pass suppresses disputes only on CONFIRMED fields",
    fill=INTAGLIO, fg=PAPER, size=6.8, weight="bold")
arrow(ax, 50, 6.5, 50, 3.5)
box(ax, 20, -3, 60, 6.5,
    "GREEN  clear        ·        AMBER  secondary        ·        RED  detain",
    fill=WHITE, size=7.4, weight="bold")

caption(ax, "Figure 3 — Decision flow. The order is fixed: hard fail, then coverage, then score.", y=-5.6)
save(fig, "fig3_flowchart.png")
