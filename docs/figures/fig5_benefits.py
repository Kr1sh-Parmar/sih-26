import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(11, 4.6, ylo=26)

box(ax, 32, 89, 36, 8, "SOLUTION BENEFITS", fill=INTAGLIO, fg=PAPER, size=10, weight="bold")
ax.plot([50, 50], [89, 85], color=IRIS, lw=1.2)
ax.plot([18, 82], [85, 85], color=IRIS, lw=1.2)
for cx in (18, 50, 82):
    arrow(ax, cx, 85, cx, 80.6, color=IRIS, lw=1.2)

items = [
    ("Runs where the problem is", "Offline, CPU-only, 154 MB idle.\nNo GPU, no connectivity, no cloud.", "#e9f3ef", "#8fc0b0", CLEAR),
    ("Explains itself", "Evidence an officer re-checks by eye,\nnot a score they must trust.", "#fdf6e3", "#d9b95c", SECONDARY),
    ("Refuses to guess", "Coverage floor: an unreadable document\nis AMBER, never GREEN.", "#f6eef7", "#b39bbe", IRIS_INK),
    ("Consistent across officers", "Weights live in a versioned profile,\nnot in individual experience.", "#e9f3ef", "#8fc0b0", CLEAR),
    ("Auditable months later", "Full signal list stored; re-score a past\nevent under new weights, no model re-run.", "#fdf6e3", "#d9b95c", SECONDARY),
    ("Privacy by construction", "Salted hash + last four digits.\nNo raw ID number is ever stored.", "#f6eef7", "#b39bbe", IRIS_INK),
]
for i, (title, sub, fill, edge, fg) in enumerate(items):
    col, row = i % 3, i // 3
    x, y = 3 + col * 32.5, 58 - row * 24
    box(ax, x, y, 30, 21, "", fill=fill, edge=edge, lw=1.3, radius=1.8)
    ax.text(x + 15, y + 15.2, title, ha="center", fontsize=8.2, weight="bold", color=fg)
    ax.text(x + 15, y + 7.5, sub, ha="center", va="center", fontsize=6.8,
            color=INTAGLIO, linespacing=1.65)
    if row == 0:
        ax.plot([x + 15, x + 15], [y, y - 3], color=IRIS, lw=1.0)

caption(ax, "Figure 5 — What the system gives back, and why each one holds at a real check post.", y=27)
save(fig, "fig5_benefits.png")
