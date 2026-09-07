# Model training

Everything needed to train the field detector somewhere else and bring the
result back. Rationale for the configuration lives in `data/TRAINING.md`; this
file is the operational handoff — paths, commands, and what has to come back.

**Only one model is trained in this project: the 22-class field detector.**
Everything else is either pre-trained and fetched at build time (OCR, face
detection, face embedding) or needs no training at all (the classical tampering
track). See the table at the end.

---

## Status, 2026-09-07

| | |
|---|---|
| State | **stopped at epoch 2 of 100.** No process running. |
| Cause | run died / was killed on 2026-09-06 ~22:05. Last output is in `var/training.log`. |
| Best so far | `runs/fields/weights/best.pt`, epoch 1 — mAP50 0.448, mAP50-95 0.263 |
| Last | `runs/fields/weights/last.pt`, epoch 2 — mAP50 0.470, mAP50-95 0.257 |
| Speed on this box | ~1400 s/epoch (RTX 3050 6 GB laptop) → 100 epochs ≈ 38 h |
| `models/` | exists, but holds only the **face** models. No field detector has been exported. |

The 38-hour figure is why this is moving to an external GPU. Epoch 2 of a
100-epoch cosine schedule is worth roughly nothing — plan on a fresh run, not a
resume.

---

## Where everything lives

### Inputs

| Path | What | Committed? |
|---|---|---|
| `data/processed/fields/` | the merged YOLO dataset, **871 MB** | no — gitignored |
| `data/processed/fields/data.yaml` | split paths + the frozen 22 class names, in order | no |
| `data/processed/fields/{train,valid,test}/images/` | 8,320 / 2,321 / 1,012 images | no |
| `data/processed/fields/{train,valid,test}/labels/` | YOLO txt, one per image | no |
| `data/raw/`, `SIH/SIH/` | the source datasets the merge reads from | no — gitignored |
| `data/tools/build_field_dataset.py` | rebuilds `data/processed/fields` from the sources | yes |

> **The merged images are hardlinks, not copies.** `build_field_dataset.py`
> hardlinks from `data/raw/` and `SIH/SIH/` so the merge costs no extra disk.
> Copying the directory to another machine resolves them and moves real bytes —
> 871 MB is the true transfer size, and it is self-contained once it lands. Do
> not assume the labels can travel alone.

### Code

| Path | What |
|---|---|
| `data/tools/train_fields.py` | train + export. The only file that matters on the GPU box. |
| `scripts/run_training.sh` | this machine's wrapper: waits for the CUDA torch install, fixes the ultralytics/torch install order, then calls the above. **Windows and `.venv-train` specific — do not run it on the external box.** |
| `data/tools/build_field_dataset.py` | dataset merge, if the set has to be rebuilt |

### Outputs of a run

| Path | What |
|---|---|
| `runs/fields/weights/best.pt` | best-validation checkpoint, 57 MB |
| `runs/fields/weights/last.pt` | last epoch, 57 MB |
| `runs/fields/results.csv` | per-epoch metrics — the file to read to know how it went |
| `runs/fields/args.yaml` | the exact config that ran |
| `var/training.log` | stdout of the wrapper on this machine |

`runs/` and `*.pt` are gitignored. Torch checkpoints never enter the screening
image.

### What the screening path actually loads

Three files in `models/`, produced by the export step:

```
models/field_detector_22cls.onnx        fp32, fallback
models/field_detector_22cls.int8.onnx   shipped — preferred by the loader
models/field_detector_22cls.json        metadata sidecar
```

`models/` is gitignored. It currently holds the two face models fetched by
`scripts/fetch_face_models.py`; nothing for the field detector.
`core/registry.py:model_path()`
prefers `.int8.onnx`, falls back to `.onnx`, and returns `None` if neither is
there — absence is a supported state, not a crash. `core/registry.py:metadata()`
reads the sidecar; `modules/extraction/detect.py:72` takes the **class list and
`imgsz` from that sidecar, never from a hardcoded constant**, because the class
order is the dataset's. A sidecar that disagrees with the weights silently
mislabels every field.

Sidecar keys, written by `train_fields.py:_metadata()`:
`name`, `task`, `imgsz`, `classes` (22, ordered), `shipped`, `precision`,
`sha256`, `size_mb`, `trained_from`, `dataset`, `metrics`. The `sha256` is what
`api/router.py:model_versions()` puts in the audit log, so a historical verdict
can name the model that produced it.

---

## Running it on the external GPU

### 1. Transfer

Copy to the GPU box, keeping the repo-relative layout:

```
data/processed/fields/     871 MB   required
data/tools/train_fields.py          required
runs/fields/weights/last.pt         only if resuming
```

`data.yaml` uses relative paths (`../train/images`), so the tree works anywhere
as long as `data/processed/fields/` stays intact.

### 2. Environment

Do **not** reuse `scripts/run_training.sh` — it is Windows-path and
`.venv-train` specific. On the GPU box:

```bash
pip install ultralytics
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Must print `True`. One warning worth carrying over from this machine's run:
ultralytics declares only `torch>=1.8.0`, so installing it *after* a pinned CUDA
build silently swaps in a CPU-only wheel and reports the failure as
`Invalid CUDA 'device=0'`. Install ultralytics first, reassert the CUDA build,
then check `torch.cuda.is_available()`. That cost a run here.

### 3. Train

```bash
python data/tools/train_fields.py --epochs 100 --batch 12 --imgsz 640 --device 0
```

Raise `--batch` for a bigger card — 12 was chosen to fit 6 GB at 640 px with
yolo11s, and is the only flag that should change for better hardware. `--imgsz`
must stay 640: it is the latency budget in TECHNICAL-SPEC.md §10, and the
sidecar carries it through to inference.

Augmentation is set inside the script and is deliberate — `fliplr=0`,
`flipud=0`, `close_mosaic=10`. Do not override them from the command line; the
reasoning is in `data/TRAINING.md` § Augmentation.

`patience=25` stops early if validation mAP plateaus, so 100 epochs is a ceiling
rather than a promise.

**Resuming is not wired.** `--weights runs/fields/weights/last.pt` starts a
*fresh* run from those weights — it does not restore optimiser state or the LR
schedule, so the cosine restarts and the result is not a continuation. If a true
resume is ever needed it is one `resume=True` kwarg in `train_fields.py:train()`.

### 4. Export

`train_fields.py` exports automatically when training completes. To export a
checkpoint on its own:

```bash
python data/tools/train_fields.py --export-only --weights runs/fields/weights/best.pt
```

This needs `onnxruntime` for the dynamic int8 quantisation step. If it is
missing the script says so and ships fp32 only — usable, just larger and
slower.

---

## Bringing it back

Copy back **only** these three files, into `models/` at the repo root:

```
field_detector_22cls.int8.onnx
field_detector_22cls.onnx
field_detector_22cls.json
```

Optionally `runs/fields/results.csv`, to fill in `data/TRAINING.md` § Results.
Do not bring back the `.pt` files — they are gitignored, 57 MB each, and nothing
in the screening path can read them.

### Verify after copying

```bash
python -m pytest -q
```

The 4 tests in `tests/test_extraction.py` that currently skip with *"field
detector weights are not in models/ yet"* must now run and pass. One of them
asserts the ONNX output head is `(1, 4+nc, anchors)` against the real file — a
transposed export produces plausible boxes with wrong labels, which is the worst
failure mode available here, so treat that test as the acceptance gate.

Then:

```bash
uvicorn api.main:app
curl localhost:8000/health
```

`loaded` must contain `field_detector_22cls` and `missing` must not. `models`
must report a real `field_detector` version string instead of `null`.

---

## What lands when it works

OCR is gated on the detector: `modules/extraction/__init__.py:run()` only calls
`ocr.run(ctx)` when `ctx.field_boxes` is non-empty. So today every declared text
field emits `inconclusive`, coverage sits on the floor, and no real document can
reach GREEN. The detector is the single unblock for the whole extraction path.

---

## Limits to carry into any claim about this model

- **4 of 22 classes have zero instances** — `ghost_photo`, `barcode`,
  `hologram`, `doc_title`. They hold their index so the class order stays
  stable; the detector cannot learn them and must not be quoted on them.
- **4 more are thin and single-source** — `signature` 25, `blood_group` 48,
  `secondary_id` 68, `logo` 144. A per-class number for these means nothing.
- **Report the test split, not validation.** Validation drove early stopping.
- Splits were assigned per source card, not per file. Training on
  `data/raw/*/*/train` leaks augmented copies of the same card across splits —
  never point the trainer at the raw directories.

---

## Not trained here

For completeness, so nobody goes looking:

| Model | Where it comes from |
|---|---|
| OCR (PP-OCRv4 det/cls/rec) | ships inside the `rapidocr_onnxruntime` wheel, 16 MB. Never trained, never downloaded at runtime. |
| Face detection and embedding | not trained — SCRFD + ArcFace come from insightface `buffalo_sc`, fetched at build time by `scripts/fetch_face_models.py`. See `data/FACE.md`. |
| Passive liveness | not trained and **not deployed**. MiniFASNet ships as PyTorch and needs an ONNX conversion plus a licence read. `data/FACE.md`. |
| Tamper detectors | not trained and never will be — the classical track is OpenCV, no training data. Measured in `data/TAMPERING.md`. |
| Document-type classifier | not built. The officer selects the type at the counter, so it reports `not_applicable`. |
