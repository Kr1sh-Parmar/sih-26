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

# The second half of this is not belt-and-braces, it is load-bearing.
#
# `rapidocr-onnxruntime` declares a dependency on plain `opencv-python`, so pip
# installs it alongside the headless build this project pins. Both ship the same
# `cv2` module, so whichever landed last wins - and the plain build needs
# `libGL.so.1`, which `python:3.11-slim` does not have. The result was an image
# that built cleanly, passed nothing, and could not `import cv2` at all. It was
# only ever caught by running the suite *inside* the image
# (`docker compose --profile verify run --rm verify`), which is what that
# profile is for.
#
# Both are uninstalled and headless reinstalled, rather than removing only the
# plain build: they share files, so uninstalling one leaves the other broken.
#
# The alternative - `apt-get install libgl1` - would also work, and would
# contradict the comment at the top of this stage by dragging an X stack into a
# server image to satisfy a dependency declaration nothing here uses. `rapidocr`
# imports `cv2` and does not care which build provides it.
#
# ---
#
# `--mount=type=cache` and the retry settings are about the connection this is
# built on, not about the dependency list. This layer pulls roughly 400 MB of
# wheels; pip's defaults - 5 retries, a 15 s read timeout, and no cache because
# of `--no-cache-dir` - meant a single dropped read nine minutes in threw the
# whole layer away and started the download again from nothing. Twice.
#
# The cache mount is not part of the image: BuildKit keeps it outside the
# layers, so nothing here inflates what ships, and a failed build now resumes
# from the wheels it already has.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries 20 --timeout 120 -r requirements.txt \
 && pip uninstall --yes opencv-python opencv-python-headless \
 && pip install --retries 20 --timeout 120 \
      "$(grep -i '^opencv-python-headless' requirements.txt | cut -d' ' -f1)" \
 && python -c "import cv2; print('cv2', cv2.__version__, 'imports in the image')"

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
