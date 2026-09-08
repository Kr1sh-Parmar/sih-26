import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *
from matplotlib.patches import Polygon

fig, ax = canvas(17.0, 11.9, ylo=-10, yhi=103)

L, R = 3.0, 52.0          # column origins
BW = 30.0                 # box width
AX_L, AX_R = 34.5, 83.5   # annotation gutters


def stage(x, y, h, title, body, *, fill=WHITE, edge=INTAGLIO, fg=INTAGLIO,
          lw=1.2, tsize=8.0, bsize=6.2):
    box(ax, x, y - h, BW, h, "", fill=fill, edge=edge, lw=lw, radius=1.3)
    ax.text(x + BW / 2, y - 2.6, title, ha="center", fontsize=tsize,
            weight="bold", color=fg)
    if body:
        ax.text(x + BW / 2, y - h / 2 - 1.0, body, ha="center", va="center",
                fontsize=bsize, color=fg if fill == INTAGLIO else IRIS_INK,
                linespacing=1.55)


def gate(x, y, h, text, size=7.0):
    ax.add_patch(Polygon([[x, y - h / 2], [x + BW / 2, y], [x + BW, y - h / 2],
                          [x + BW / 2, y - h]], closed=True, facecolor=GUILLOCHE,
                         edgecolor=INTAGLIO, lw=1.2, zorder=2))
    ax.text(x + BW / 2, y - h / 2, text, ha="center", va="center", fontsize=size,
            weight="bold", color=INTAGLIO, zorder=3)


def out(gx, y, text, colour=IRIS_INK, size=5.8):
    ax.text(gx, y, text, fontsize=size, color=colour, va="top", ha="left",
            linespacing=1.62)


def down(x, y1, y2):
    arrow(ax, x + BW / 2, y1, x + BW / 2, y2, lw=1.2)


def exitright(x, y, label, tint, edge, fg, text):
    arrow(ax, x + BW, y, x + BW + 5.6, y, lw=1.2)
    ax.text(x + BW + 0.6, y + 1.3, label, fontsize=5.9, color=IRIS_INK)
    box(ax, x + BW + 6.0, y - 3.1, 12.0, 6.2, text, fill=tint, edge=edge, fg=fg,
        size=6.4, weight="bold", radius=1.0)


ARROW = "→"; LEQ = "≤"; GEQ = "≥"; MIDDOT = "·"
SIGMA = "Σ"; PI = "Π"; TIMES = "×"; DIV = "÷"
BIDIR = "↔"; MINUS = "−"; EN = "–"

# ============================ LEFT COLUMN =================================
ax.text(L, 101.5, "READ THE DOCUMENT", fontsize=7.4, weight="bold", color=IRIS_INK)
ax.text(AX_L, 101.5, "STATE  " + MIDDOT + "  OUTPUT", fontsize=6.6, weight="bold", color=IRIS)

y = 98
stage(L, y, 8, "1  CAPTURE",
      "scanner " + MIDDOT + " phone camera " + MIDDOT + " webcam\nofficer selects the document type",
      fill=BLOOM)
out(AX_L, y - 1.5, "raw bytes  +  doc_type\n+ optional live frame\n+ uploaded? flag")
down(L, y - 8, y - 11); y -= 11

stage(L, y, 7, "2  DECODE ONCE",
      "core/decode.py " + MIDDOT + " longest edge " + LEQ + " 1000 px", fill=GUILLOCHE)
out(AX_L, y - 1.5, "ctx.image " + EN + " one BGR array.\nNo module ever re-decodes it.")
down(L, y - 7, y - 10); y -= 10

gate(L, y, 7, "capture usable?")
exitright(L, y - 3.5, "no", "#fdf3d9", SECONDARY, SECONDARY, "AMBER\nre-capture")
out(AX_L, y - 8.2, "blur " + MIDDOT + " resolution " + MIDDOT + " brightness\n" + ARROW + " extraction.quality.*", size=5.6)
down(L, y - 7, y - 15.5); y -= 15.5

stage(L, y, 7, "3  LOAD PROFILE", "profiles/<doc_type>.yaml")
out(AX_L, y - 1.5, "declared fields " + MIDDOT + " check weights\nhard_fail list " + MIDDOT + " thresholds\ndisclosure string")
down(L, y - 7, y - 10); y -= 10

stage(L, y, 14, "4  EXTRACTION",
      "YOLOv11s 22-class detector " + ARROW + " field boxes\n"
      "PP-OCRv4 on crops (en + hi) " + ARROW + " text\n"
      "MRZ read from its ICAO fixed position\n"
      "QR decode " + ARROW + " signed envelope\n"
      "Florence-2 only if nothing was read",
      fill="#e9f3ef", edge="#8fc0b0")
out(AX_L, y - 1.5,
    "ctx.field_boxes\n"
    "ctx.fields = 12 canonical fields,\neach carrying value + SOURCE\n"
    "     ocr " + MIDDOT + " mrz " + MIDDOT + " vlm " + MIDDOT + " qr\n"
    + ARROW + " extraction.* signals")
down(L, y - 14, y - 17); y -= 17

stage(L, y, 12.5, "5  VALIDATION  A" + EN + "F",
      "A  signature " + MIDDOT + " Verhoeff " + MIDDOT + " ICAO check digits\n"
      "B  codes " + MIDDOT + " lengths " + MIDDOT + " charsets " + MIDDOT + " formats\n"
      "C  date order " + MIDDOT + " validity " + MIDDOT + " VIZ" + BIDIR + "MRZ\n"
      "D  print vs its OWN signature, and across docs\n"
      "E  watchlist          F  transit history",
      fill="#e9f3ef", edge="#8fc0b0")
out(AX_L, y - 1.5,
    "validation.* signals\ntrust = cryptographic | arithmetic\n\n"
    "The only checks that can be\nCERTAIN rather than likely.")
down(L, y - 12.5, y - 15.5); y -= 15.5

stage(L, y, 11, "6  TAMPER + FACE   (Tier 1)",
      "ghost portrait " + MIDDOT + " layout " + MIDDOT + " font heights\n"
      "EXIF " + MIDDOT + " ELA " + MIDDOT + " double-JPEG  (uploads only)\n"
      "SCRFD " + ARROW + " ArcFace 512-d " + ARROW + " cosine\n"
      "MiniFASNet passive liveness",
      fill="#e9f3ef", edge="#8fc0b0")
out(AX_L, y - 1.5,
    "tamper.* and face.* signals\ntrust = probabilistic\n\nctx.embeddings['doc' | 'live']")

# Column break. A wire routed round the outside would have to cross the verdict
# box to get back up, so the flow is handed over explicitly instead.
arrow(ax, L + BW / 2, y - 11, L + BW / 2, y - 14.5, lw=1.2)
box(ax, L + 1.5, y - 20.5, BW - 3, 6.0,
    "every check has now emitted a Signal" + chr(10) +
    "continues at the top of the next column  " + ARROW,
    fill=BLOOM, size=6.3, weight="bold", radius=1.0)
arrow(ax, R + BW / 2, 100.6, R + BW / 2, 96.4, lw=1.2)
ax.text(R + BW / 2 - 1.2, 99.0, "continued", fontsize=5.9, color=IRIS_INK,
        ha="right", style="italic")

# ============================ RIGHT COLUMN ================================
ax.text(R, 101.5, "DECIDE WHAT IT MEANS", fontsize=7.4, weight="bold", color=IRIS_INK)
ax.text(AX_R, 101.5, "RULE  " + MIDDOT + "  ARITHMETIC", fontsize=6.6, weight="bold", color=IRIS)

y = 96
stage(R, y, 9.5, "ctx.signals[ ]",
      "id " + MIDDOT + " verdict " + MIDDOT + " trust_class " + MIDDOT + " confidence\n"
      "anchor " + MIDDOT + " evidence " + MIDDOT + " hard_fail " + MIDDOT + " latency",
      fill=INTAGLIO, fg=PAPER)
out(AX_R, y - 1.5,
    "verdict is one of FOUR:\npass " + MIDDOT + " fail " + MIDDOT + " inconclusive " + MIDDOT + " not_applicable\n\n"
    "Collapsing the last two is how\na blurred photo becomes GREEN.", size=5.7)
down(R, y - 9.5, y - 12.5); y -= 12.5

gate(R, y, 7, "any hard fail?")
exitright(R, y - 3.5, "yes", "#fbe9ee", DETAIN, DETAIN, "RED\ndetain")
out(AX_R, y - 8.2, "Bypasses scoring entirely.\nThe profile decides which ids\nare fatal " + EN + " not the module.", size=5.7)
down(R, y - 7, y - 15.5); y -= 15.5

stage(R, y, 7.5, "COVERAGE",
      SIGMA + " weight of checks that ANSWERED\n" + DIV + " " + SIGMA + " weight of checks that APPLIED")
out(AX_R, y - 1.5, "not_applicable leaves the sum.\ninconclusive stays in it, and\ncosts coverage.", size=5.7)
down(R, y - 7.5, y - 10); y -= 10

gate(R, y, 7, "coverage " + GEQ + " 0.70?")
exitright(R, y - 3.5, "no", "#fdf3d9", SECONDARY, SECONDARY, "AMBER\nre-capture")
out(AX_R, y - 8.2, "An unreadable document is\nnever a cleared document.", size=5.7)
down(R, y - 7, y - 15.5); y -= 15.5

gate(R, y, 7, "risk gate escalates?")
exitright(R, y - 3.5, "yes", BLOOM, INTAGLIO, INTAGLIO, "TIER 2\ncopy-move " + MIDDOT + " SRM\n1:N gallery")
out(AX_R, y - 8.2, "~15 % of documents.\ntamper > 0.15, or a face score\ninside its review band.", size=5.7)
down(R, y - 7, y - 15.5); y -= 15.5

arrow(ax, 94.0, 35.9, 82.4, 22.0, rad=-0.35, lw=1.1)

stage(R, y, 14, "FUSION",
      "1  region anchor " + ARROW + " field anchor  (IoU " + GEQ + " 0.30)\n"
      "2  group by anchor " + MIDDOT + " severity = noisy-OR\n"
      "3  suppress probabilistic disputes ONLY on\n"
      "     fields a signature actually confirmed\n"
      "4  score, then band",
      fill=INTAGLIO, fg=PAPER)
out(AX_R, y - 1.5,
    "severity = 1 " + MINUS + " " + PI + "(1 " + MINUS + " conf " + TIMES + " reliability)\n"
    "over the FAILING members only.\n\n"
    "score = " + SIGMA + "(severity " + TIMES + " weight)\n"
    "              " + DIV + " " + SIGMA + " weight of checks that RAN", size=5.7)
down(R, y - 14, y - 17); y -= 17

box(ax, R, y - 7, BW, 7, "", fill=WHITE, edge=IRIS, lw=1.2, radius=1.2)
for i, (lab, col, tint) in enumerate([("GREEN", CLEAR, "#e9f3ef"),
                                      ("AMBER", SECONDARY, "#fdf3d9"),
                                      ("RED", DETAIN, "#fbe9ee")]):
    bx = R + 1.3 + i * 9.5
    box(ax, bx, y - 5.7, 8.4, 4.4, lab, fill=tint, edge=col, fg=col, size=6.8,
        weight="bold", radius=0.9)
out(AX_R, y - 1.5,
    "Band edges are configuration,\nnot code. The commander moves\nthem, and every stored event\ncan be re-scored under the new\n"
    "ones without re-running a model.", size=5.7)

ax.text(50, -5.2,
        "Nothing leaves a module but a list of Signals.  Every value carries the source that produced it, and only ink counts as printed "
        + EN + " which is why a value lifted from the QR can never corroborate the QR.",
        ha="center", fontsize=6.8, color=INTAGLIO, style="italic")
caption(ax, "Figure 0 " + EN + " The whole system in one flow: what is read, what each check emits, and how those become a verdict.", y=-9.0)
save(fig, "fig0_master.png")
