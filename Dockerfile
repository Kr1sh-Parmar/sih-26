# The screening image. CPU only, offline at run time.
#
# Two properties this file exists to make true rather than to claim:
#
#   * **Every model is baked in.** Nothing is fetched on first use. The build
#     copies whatever `models/` holds; the fetchers that fill it
#     (`scripts/fetch_face_models.py`, `scripts/fetch_ocr_models.py`,
#     `scripts/fetch_vlm_model.py`, `data/tools/train_fields.py`) run
#     BEFORE the build, never inside it and never at run time. A model that
#     downloads itself surfaces on exactly the day the cable comes out
#     (CLAUDE.md rule 3, DEMO.md closing).
#   * **No CUDA anywhere.** `requirements.txt` is the CPU set. Training lives in
#     `.venv-train` and build tooling in `requirements-build.txt`; neither is
#     installed here, and `.dockerignore` keeps both out of the context.
#
# If `models/` is empty the image still builds and still runs - every module
# degrades to `inconclusive` signals and says which weights are missing. That is
# a supported state, not a broken one, and `GET /health` reports it.

FROM python:3.11-slim AS runtime

# libzbar0 is pyzbar's shared library (requirements.txt says so on its line).
# opencv-python-headless needs no libGL, which is the whole reason it is the
# headless build - a plain opencv-python would drag in an X stack.
RUN apt-get update \
 && apt-get install --no-install-recommends -y libzbar0 curl \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    # More threads is not faster on models this small and the box is also
    # serving a websocket. core/registry.py reads this.
    SCREENING_ORT_THREADS=4

WORKDIR /app

# Requirements first, so a code change does not re-resolve the dependency tree.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# `var/` holds the SQLite store, the reference issuer keys and the ID salt.
# It is a volume in compose; created here so the image runs standalone too.
RUN mkdir -p var \
 && useradd --create-home --uid 10001 screening \
 && chown -R screening:screening /app
USER screening

EXPOSE 8000

# Reports which models actually loaded, so a container that came up without its
# weights is visible immediately rather than three documents later.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
