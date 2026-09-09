import sys, os; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _style import *

fig, ax = canvas(11, 6.2, ylo=2)

groups = [
    ("OFFICER CONSOLE", "#f6eef7", "#b39bbe", IRIS_INK,
     ["React 19  ·  TypeScript", "Vite 8  ·  Tailwind CSS 4",
      "Zustand  ·  React Router", "Vitest  ·  oxlint",
      "Fonts self-hosted (offline)"]),
    ("API & TRANSPORT", "#fdf6e3", "#d9b95c", SECONDARY,
     ["FastAPI  ·  Uvicorn", "WebSocket signal stream",
      "Pydantic contracts", "SQLite (core/store.py)",
      "No Postgres, no MinIO"]),
    ("INFERENCE  ·  CPU ONLY", "#e9f3ef", "#8fc0b0", CLEAR,
     ["ONNX Runtime (CPU, int8)", "YOLOv11s — 22-class fields",
      "PP-OCRv4 via RapidOCR", "SCRFD + ArcFace (buffalo_sc)",
      "MiniFASNet  ·  Florence-2"]),
    ("CRYPTO & DATA", "#eef2f8", "#9fb0cc", "#3c5580",
     ["Ed25519 (cryptography)", "Reference issuer + anchors",
      "OpenCV  ·  NumPy", "Faker en_IN  ·  Pillow",
      "OFAC SDN + UN lists"]),
]
for i, (name, fill, edge, fg, rows) in enumerate(groups):
    x = 2 + i * 24.5
    box(ax, x, 20, 22, 72, "", fill=fill, edge=edge, lw=1.5, radius=2.0)
    ax.text(x + 11, 86, name, ha="center", fontsize=8.0, weight="bold", color=fg)
    ax.plot([x + 3, x + 19], [82, 82], color=edge, lw=1.0)
    for j, r in enumerate(rows):
        ax.text(x + 11, 75 - j * 11, r, ha="center", va="center", fontsize=6.9,
                color=INTAGLIO)

box(ax, 2, 8, 96, 8, "PACKAGING   ·   Docker + docker-compose   ·   models baked into the image   ·   "
                     "zero network calls at inference",
    fill=INTAGLIO, fg=PAPER, size=7.6, weight="bold")

caption(ax, "Figure 8 — Technology stack. Every runtime dependency installs offline from a locked file.", y=2.6)
save(fig, "fig8_techstack.png")
