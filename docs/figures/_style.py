"""Shared drawing helpers for the SIH submission figures.

Palette is the console's own (frontend/src/styles/tokens.css), so the document
and the screen an officer uses are recognisably the same system.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

PAPER      = "#fff2cf"
GUILLOCHE  = "#f8de7e"
BLOOM      = "#e7c9e8"
IRIS       = "#b39bbe"
IRIS_INK   = "#6e5c7a"
INTAGLIO   = "#3a2e45"
CLEAR      = "#1f5d4c"
DETAIN     = "#a3123a"
SECONDARY  = "#8a6a0f"
WHITE      = "#ffffff"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "figure.facecolor": WHITE,
    "savefig.facecolor": WHITE,
})


def canvas(w, h, ylo=0, yhi=100, xlo=0, xhi=100):
    fig, ax = plt.subplots(figsize=(w, h), dpi=200)
    ax.set_xlim(xlo, xhi); ax.set_ylim(ylo, yhi)
    ax.axis("off")
    return fig, ax


def box(ax, x, y, w, h, text, *, fill=WHITE, edge=INTAGLIO, fg=INTAGLIO,
        size=8, weight="normal", lw=1.2, radius=1.6, style="round"):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=f"{style},pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=edge, facecolor=fill, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=size, color=fg, weight=weight, zorder=3,
            linespacing=1.45)


def arrow(ax, x1, y1, x2, y2, *, color=IRIS_INK, lw=1.3, style="-|>", rad=0.0):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2), arrowstyle=style, mutation_scale=11,
        linewidth=lw, color=color, zorder=1,
        connectionstyle=f"arc3,rad={rad}"))


def caption(ax, text, y=1.5, size=7):
    ax.text(50, y, text, ha="center", va="bottom", fontsize=size,
            color=IRIS_INK, style="italic")


def save(fig, name):
    from pathlib import Path
    out = Path(__file__).resolve().parent / name
    fig.savefig(out, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    print("  wrote", out.name)
