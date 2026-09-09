import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(11, 5.0, ylo=14)

box(ax, 34, 90, 32, 8, "WHO IT REACHES", fill=INTAGLIO, fg=PAPER, size=9.5, weight="bold")

groups = [
    ("Border officer\nat the counter", "#e9f3ef", "#8fc0b0", CLEAR,
     ["Verdict in ~1 s with reasons",
      "Decides, is not decided for",
      "Sees margin from threshold",
      "Blur says re-capture, not clear"]),
    ("Checkpoint\ncommander", "#fdf6e3", "#d9b95c", SECONDARY,
     ["Sets the operating point",
      "FAR/FRR is a policy dial",
      "Queue load is predictable",
      "Consistency across shifts"]),
    ("Investigation &\naudit officer", "#f6eef7", "#b39bbe", IRIS_INK,
     ["Full signal list per event",
      "Re-score under new weights",
      "Model version on every verdict",
      "Defensible months later"]),
    ("The traveller", "#eef2f8", "#9fb0cc", "#3c5580",
     ["Faster genuine clearance",
      "Fewer arbitrary secondaries",
      "No ID number retained",
      "Face crops expire"]),
]
for i, (name, fill, edge, fg, bullets) in enumerate(groups):
    x = 2 + i * 24.5
    box(ax, x, 62, 22, 18, name, fill=fill, edge=edge, fg=fg, lw=1.4, size=8.4,
        weight="bold", radius=1.8)
    arrow(ax, 50, 90, x + 11, 80.6, color=IRIS, lw=1.0,
          rad=0.12 if x + 11 < 50 else -0.12)
    box(ax, x, 22, 22, 36, "", fill=WHITE, edge=edge, lw=1.0, radius=1.6)
    ax.plot([x + 11, x + 11], [62, 58.8], color=edge, lw=1.0)
    for j, b in enumerate(bullets):
        ax.text(x + 1.6, 52 - j * 8.6, "▪", fontsize=6, color=edge, va="center")
        ax.text(x + 4.0, 52 - j * 8.6, b, fontsize=6.7, color=INTAGLIO,
                va="center", linespacing=1.4)

caption(ax, "Figure 6 — Target audiences and the concrete change each one sees.", y=15)
save(fig, "fig6_impact.png")
