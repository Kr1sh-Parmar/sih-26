# Field detector — training record

One YOLOv11s detector covering all six document types on the frozen 22-class
ontology (D17). Not six detectors: shared classes — `name`, `dob`,
`person_photo`, `signature` appear on every type — generalise better from
pooled data than six small models each seeing 200 images, and it is one warm
ONNX session instead of six.

Regenerate the dataset with `data/tools/build_field_dataset.py`; retrain with
`bash scripts/run_training.sh <epochs>`.

---

## Status

| | |
|---|---|
| **State** | running — started 2026-09-06, 100 epochs |
| **Result** | pending, see [Results](#results) |

---

## Where training is allowed to happen

Training runs in `.venv-train`, which is the only place `torch` and CUDA exist
on this machine. `data/tools/train_fields.py` refuses to run under the base
interpreter, and nothing under `api/`, `core/`, `modules/` or `fusion/` imports
torch.

This is CLAUDE.md rule 2 read precisely: *every model is ONNX Runtime on CPU*
is a statement about **inference**. Training on a GPU is ordinary build-time
work. Keeping the two in separate environments makes that boundary a fact about
the filesystem rather than a promise in a document — and it means the demo claim
("no GPU, no internet") is checkable by looking at what the API process can
import.

Only the exported int8 ONNX crosses into the screening path.

---

## Data

`data/processed/fields/` — the merged set, built by remapping every source
dataset onto the 22-class ontology so source class names never reach the model.

| Split | Images | Boxes |
|---|---|---|
| train | 8,320 | 33,605 |
| valid | 2,321 | 9,076 |
| test | 1,012 | 4,089 |

18 of 22 classes carry instances. Four are **empty** and the detector cannot
learn them: `ghost_photo`, `barcode`, `hologram`, `doc_title`. They exist in the
ontology so the class index is stable; the synthetic generator has to backfill
them. **Do not quote a per-class number for those four, or for the thin ones** —
`signature` 25, `blood_group` 48, `secondary_id` 68, `logo` 144 — each comes
from a single small source.

Splits were assigned **per source card**, not per file. Source datasets ship
augmented copies of one card spread across their own train/valid/test
directories, so training on `data/raw/*/*/train` leaks. `data.yaml` here points
only at the merged set.

---

## Configuration

`data/tools/train_fields.py`, defaults:

| Setting | Value | Why |
|---|---|---|
| model | `yolo11s` | 22 MB, ~110 ms on CPU at 640 — its share of the Tier 1 budget |
| imgsz | 640 | matches the latency budget in TECHNICAL-SPEC.md §10 |
| batch | 12 | fits 6 GB at 640 with yolo11s |
| epochs | 100 | `patience=25` stops earlier if valid mAP plateaus |
| device | RTX 3050 6 GB Laptop | build-time only |

### Augmentation, and the two that are switched off

`fliplr=0.0` and `flipud=0.0`. Documents get photographed at every angle and
under every light, but they are never mirrored and never upside down in a
scanner. Left-right flip would teach the detector that mirrored text is normal,
which is exactly the thing OCR then has to un-learn — and `id_number`,
`dob` and `mrz` are all text fields whose whole value is their reading order.

`close_mosaic=10`. Mosaic pastes four cards into one frame, which helps early
and is actively wrong at the end: a real capture at a counter holds exactly one
document, so the last ten epochs train on that distribution.

`degrees=7.0`, `perspective=0.0005`, `hsv_v=0.4` are kept — a card handed across
a counter is tilted, slightly keystoned, and lit by whatever is overhead.

---

## Export

`train_fields.py` exports automatically on completion:

```
models/field_detector_22cls.onnx        fp32
models/field_detector_22cls.int8.onnx   shipped
models/field_detector_22cls.json        metadata
```

Quantisation is **dynamic** int8. Static would need a calibration pass and buys
little on a detector this size — measure before adding one.

The `.json` carries the class list, input size, sha256, size and final metrics.
`core/registry.py` reads the class list from it rather than hardcoding, and
`MODEL_VERSIONS` in `api/router.py` reads the hash, so an audit log can answer
*which model produced this verdict* instead of reporting `null`.

`models/` is gitignored. The weights are baked into the Docker image, never
fetched at runtime.

---

## Results

*Pending — this section is filled in when the run completes.*

What goes here: mAP50 and mAP50-95 on the held-out **test** split, per-class
precision and recall for the 18 classes that have data, measured CPU latency of
the exported int8 model at 640, and the model hash.

Two honesty rules for whatever number lands here:

1. **Report the test split, not the validation split.** Validation drove early
   stopping, so quoting it is quoting the number the run optimised against.
2. **No per-class figure for the four empty classes or the four thin ones.**
   A class with 25 instances from one source produces a number that means
   nothing, and a panel that asks where it came from will find that out.

---

## Log

| Date | Event |
|---|---|
| 2026-09-06 | Dataset merged: 11,653 files from 5,375 source images, 18/22 classes |
| 2026-09-06 | Training environment isolated to `.venv-train` (CUDA torch) |
| 2026-09-06 | First run launched — yolo11s, 640px, 100 epochs |
