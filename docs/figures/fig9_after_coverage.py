import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *
from matplotlib.patches import Polygon

fig, ax = canvas(11.4, 10.6, ylo=-22)

def diamond(x, y, w, h, text, size=7.2):
    ax.add_patch(Polygon([[x, y+h/2], [x+w/2, y+h], [x+w, y+h/2], [x+w/2, y]],
                         closed=True, facecolor=GUILLOCHE, edgecolor=INTAGLIO,
                         lw=1.2, zorder=2))
    ax.text(x+w/2, y+h/2, text, ha="center", va="center", fontsize=size,
            color=INTAGLIO, weight="bold", zorder=3)

def note(x, y, lines, colour=IRIS_INK, size=6.3, ha="left"):
    ax.text(x, y, lines, fontsize=size, color=colour, va="top", ha=ha,
            linespacing=1.55, family="DejaVu Sans")

ax.text(2, 99, "CONTINUES FROM FIGURE 3", fontsize=6.8, weight="bold", color=IRIS_INK)
box(ax, 26, 92, 34, 5, "Coverage ≥ 0.70  —  passed", fill="#e9f3ef",
    edge="#8fc0b0", fg=CLEAR, size=7.4, weight="bold")
arrow(ax, 43, 92, 43, 89.4)

# ---- risk gate -----------------------------------------------------------
box(ax, 24, 79, 38, 10, "RISK GATE\nfusion/gate.py · decide()", fill=BLOOM,
    size=8, weight="bold")
note(64, 89,
     "INPUTS IT READS\n"
     "• any signal with hard_fail, or the profile says so\n"
     "• tamper_score = max confidence of failing tamper.*\n"
     "• ESCALATE_ON_FAIL: validation.vizmrz.* · tamper.stamp.duplicate\n"
     "• face.match.cosine  certainty < 1.0 (inside review band)\n"
     "• face.liveness.passive  certainty < 1.0\n"
     "• tamper_score > 0.15  (one threshold, every document — D50)")

arrow(ax, 33, 79, 33, 74.5); ax.text(24.5, 76.2, "clear  ~85 %", fontsize=6.4, color=IRIS_INK)
arrow(ax, 53, 79, 53, 74.5); ax.text(54.5, 76.2, "escalate  ~15 %", fontsize=6.4, color=IRIS_INK)

# ---- tier 2 --------------------------------------------------------------
ax.add_patch(FancyBboxPatch((40, 55), 58, 19, boxstyle="round,pad=0,rounding_size=1.4",
                            linewidth=0, facecolor="#eae2f0", zorder=0))
ax.text(42, 71.6, "TIER 2 — runs only on escalation", fontsize=6.8,
        weight="bold", color=IRIS_INK)
box(ax, 42, 57, 17, 12.5, "copy-move\nORB features\nsharing one\ndisplacement", size=6.4)
box(ax, 61, 57, 17, 12.5, "noise residual\nSRM filter\nover local\ndetail", size=6.4)
box(ax, 80, 57, 16, 12.5, "1:N gallery\ncosine scan\nover stored\nembeddings", size=6.4)
note(42, 56.2, "tamper.digital.copy_move          tamper.digital.noise_residual          face.gallery.duplicate (≥ 0.45)",
     size=5.9)

arrow(ax, 53, 57, 53, 51.5)
arrow(ax, 33, 74.5, 33, 51.5)

# ---- fusion --------------------------------------------------------------
box(ax, 8, 44, 88, 7, "FUSION  —  fusion/findings.py  then  fusion/score.py",
    fill=INTAGLIO, fg=PAPER, size=8.4, weight="bold")
arrow(ax, 52, 44, 52, 41.5)

steps = [
    ("1", "resolve_anchor()",
     "A region anchor becomes a field anchor when it overlaps a known\n"
     "field box by IoU ≥ 0.30. Without it, a tamper mask over the date of\n"
     "birth and the VIZ/MRZ mismatch on that date become two problems."),
    ("2", "build_findings()  —  group by anchor",
     "Severity = noisy-OR over the FAILING members only: 1 − Π(1 − conf × reliability).\n"
     "Two 60 %-reliable checks both failing give 0.84, never 1.2.\n"
     "Trust class comes from the failing members too, so a heuristic cannot\n"
     "wear a signature's authority (D49)."),
    ("3", "apply_crypto_precedence()",
     "Drops probabilistic findings ONLY on fields where a signature was\n"
     "actually checked against the ink and agreed — confirmed_fields().\n"
     "Skipped entirely if any cryptographic finding is itself failing."),
    ("4", "score_findings()  →  band_for()",
     "score = Σ (severity × profile weight) ÷ Σ weight of signals that RAN.\n"
     "Renormalised over what ran, so a document that could not execute its\n"
     "checks is caught by the coverage floor rather than flattered by them."),
]
y = 39
for num, title, body in steps:
    h = 3.4 + 2.0 * (len(body.splitlines()))
    box(ax, 8, y - h, 88, h, "", fill=WHITE, edge=IRIS, lw=1.0, radius=1.2)
    ax.text(10.5, y - 2.4, num, fontsize=9.5, weight="bold", color=IRIS_INK, va="center")
    ax.text(14.5, y - 2.4, title, fontsize=7.4, weight="bold", color=INTAGLIO, va="center")
    note(14.5, y - 4.0, body, colour=IRIS_INK, size=6.2)
    arrow(ax, 52, y - h, 52, y - h - 1.3, lw=1.0)
    y -= h + 1.3

# ---- output --------------------------------------------------------------
box(ax, 8, y - 7.0, 41, 7.0, "Verdict" + chr(10) + "band · score · coverage · reason",
    fill="#e9f3ef", edge="#8fc0b0", fg=CLEAR, size=7.2, weight="bold")
box(ax, 55, y - 7.0, 41, 7.0,
    "Evidence cards" + chr(10) + "hard fails → findings → gaps → crypto passes → count",
    fill=BLOOM, size=7.2, weight="bold")

caption(ax, "Figure 3b — What happens after the coverage floor: the risk gate, Tier 2, and the four steps of fusion.", y=y - 11.5)
save(fig, "fig9_after_coverage.png")
