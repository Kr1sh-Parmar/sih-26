import sys; sys.path.insert(0, __file__.rsplit("\\", 1)[0] if "\\" in __file__ else ".")
from _style import *

fig, ax = canvas(11, 4.9, ylo=21)

ax.text(2, 95, "TODAY AT THE COUNTER", fontsize=9, weight="bold", color=DETAIN)
ax.text(54, 95, "WITH THIS SYSTEM", fontsize=9, weight="bold", color=CLEAR)
ax.plot([50, 50], [6, 92], color=IRIS, lw=1.0, ls=(0, (4, 4)))

problems = [
    ("Eyeball inspection under queue pressure",
     "A few seconds per document, thousands a day."),
    ("Verdicts differ between officers",
     "No shared standard; experience is the only check."),
    ("No connectivity, no GPU at the post",
     "Cloud OCR and hosted models are simply unavailable."),
    ("Sophisticated forgery is invisible",
     "Reprinted fields and swapped photos pass a glance."),
    ("Nothing is written down",
     "A decision months later cannot be reconstructed."),
]
y = 84
for title, sub in problems:
    box(ax, 2, y - 9, 45, 9, "", fill="#fbe9ee", edge="#e0a8b8", lw=1.0)
    ax.text(4, y - 3.0, title, fontsize=8, weight="bold", color=DETAIN, va="center")
    ax.text(4, y - 6.6, sub, fontsize=6.8, color=IRIS_INK, va="center")
    y -= 11.5

sols = [
    ("Three levels of certainty, always labelled",
     "Cryptographic · Arithmetic · Probabilistic."),
    ("One second, offline, on an 8-core CPU",
     "Every model ONNX int8. Network cable out."),
    ("Same verdict for every officer",
     "Weights live in a profile, not in a habit."),
    ("Checkable reasons, not a score",
     "\"MRZ DOB 1991-08-04 does not match printed 1998-11-02\"."),
    ("An unreadable document is never cleared",
     "Coverage floor: inconclusive is not a pass."),
]
y = 84
for title, sub in sols:
    box(ax, 53, y - 9, 45, 9, "", fill="#e9f3ef", edge="#8fc0b0", lw=1.0)
    ax.text(55, y - 3.0, title, fontsize=8, weight="bold", color=CLEAR, va="center")
    ax.text(55, y - 6.6, sub, fontsize=6.8, color=IRIS_INK, va="center")
    y -= 11.5

caption(ax, "Figure 1 — The problem at a border check post, and what the system changes.", y=22)
save(fig, "fig1_problem_and_idea.png")
