import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(11, 6.6, ylo=2)

def band(y, h, label, colour):
    ax.add_patch(FancyBboxPatch((1.5, y), 97, h,
        boxstyle="round,pad=0,rounding_size=1.4", linewidth=0,
        facecolor=colour, zorder=0))
    ax.text(3.5, y + h - 2.6, label, fontsize=6.6, weight="bold",
            color=IRIS_INK, va="center")

band(83, 14, "L1 · CAPTURE", "#f6eef7")
box(ax, 8,  84.5, 22, 7.5, "Flatbed scanner\nor phone camera", size=7.4)
box(ax, 39, 84.5, 22, 7.5, "Live webcam frame\n(the person)", size=7.4)
box(ax, 70, 84.5, 22, 7.5, "Officer selects\ndocument type", size=7.4)

band(67, 13, "L2 · ORCHESTRATION", "#f0e8f3")
box(ax, 8, 68.5, 40, 7.5, "Decode ONCE  →  ctx.image\nno module re-reads bytes",
    fill=GUILLOCHE, size=7.4, weight="bold")
box(ax, 54, 68.5, 38, 7.5, "Route by document profile\n(6 YAML profiles)", size=7.4)

band(41, 23, "L3–L6 · TIER 1 — every document, target < 1 s", "#eae2f0")
mods = [("Extraction\n\nfields · MRZ · QR\nOCR · VLM fallback", 5),
        ("Validation\n\nLayers A–F\nchecksums · dates\nsignature · watchlist", 29),
        ("Tampering\n\ncopy-move · ELA\nnoise · fonts\nguilloche · ghost", 53),
        ("Face\n\ndetect · quality\n1:1 match\npassive liveness", 77)]
for text, x in mods:
    box(ax, x, 42.5, 20, 15.5, text, size=6.8)

box(ax, 30, 33, 40, 6, "RISK GATE  —  escalate ~15 % of documents", fill=BLOOM,
    size=7.4, weight="bold")

band(18, 13, "L7 · TIER 2 — only when escalated", "#eae2f0")
box(ax, 8,  19.5, 26, 7.5, "Deep forensics\n(SRM · double-JPEG)", size=6.9)
box(ax, 37, 19.5, 26, 7.5, "Active liveness\n(deferred — cut list)", fill="#f4f0f6",
    fg=IRIS_INK, size=6.9)
box(ax, 66, 19.5, 26, 7.5, "1:N gallery search\n(duplicate identity)", size=6.9)

box(ax, 8, 8, 40, 7.5, "FUSION\nsignals → findings → score", fill=INTAGLIO, fg=PAPER,
    size=7.6, weight="bold")
box(ax, 54, 8, 38, 7.5, "OFFICER CONSOLE\nverdict + evidence cards", fill=INTAGLIO,
    fg=PAPER, size=7.6, weight="bold")

for x in (19, 50, 81):
    arrow(ax, x, 84.5, x, 80.3)
arrow(ax, 28, 68.5, 28, 64.3)
for _, x in mods:
    arrow(ax, x + 10, 42.5, x + 10, 39.3)
arrow(ax, 50, 33, 50, 31.3)
arrow(ax, 50, 18, 28, 15.8)
arrow(ax, 48, 11.75, 54, 11.75)

ax.text(50, 4.6, "Every check emits a Signal.  Nothing leaves a module but a list of Signals.",
        ha="center", fontsize=7, color=IRIS_INK, style="italic")
caption(ax, "Figure 2 — System block diagram. Nine layers, one process, no network.", y=2.2)
save(fig, "fig2_block_architecture.png")
