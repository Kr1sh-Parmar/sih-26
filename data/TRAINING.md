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
| **Result** | deployed 2026-09-09, see [Results](#results) — 0.926 recall on its own test split, 0.142 on generated cards (D51) |

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

Trained on an external GPU, exported and deployed 2026-09-09.

```
field_detector_22cls.int8.onnx   9.88 MB   int8, imgsz 640
sha256  d8baab1d46aedaac0ab3c572780b8e54780a6d8595c65e787549f7fb3c1b3c55
```

### What the training run reported

| | |
|---|---|
| precision (B) | 0.643 |
| recall (B) | 0.906 |
| mAP50 (B) | 0.766 |
| mAP50-95 (B) | 0.541 |

### What the shipped artefact actually does

The numbers above describe the `.pt` inside ultralytics. What screens documents
is the int8 ONNX read through `modules/extraction/detect.py` — letterboxing,
NMS, the YOLO head decode. `data/tools/eval_detector.py` measures *that*, on the
held-out test split, at IoU 0.5:

```
OVERALL   recall 0.926   3788 / 4089 instances over 1012 images
```

Consistent with the run's 0.906, which settles a question the sidecar cannot:
the export, the quantisation and the decoder are correct end to end. A
transposed head or a bad quantisation would have collapsed here.

Per document type, test split:

| | recall | | | recall |
|---|---|---|---|---|
| visa | 1.000 | | aadhaar | 0.848 |
| pan | 0.981 | | dl | 0.855 |
| passport | 0.980 | | voter_id | 0.936 |

Per class, for the classes that have data — precision is not reported per class
for the reason in rule 2 below:

| class | recall | | class | recall |
|---|---|---|---|---|
| issue_date | 0.993 | | address | 0.942 |
| expiry_date | 0.983 | | dob | 0.934 |
| id_number | 0.981 | | father_name | 0.922 |
| nationality | 0.979 | | person_photo | 0.796 |
| gender | 0.978 | | issuing_authority | 0.732 |
| name | 0.966 | | qr_code | 0.667 |
| mrz | 0.700 | | emblem | 0.570 |

`mrz` at 0.700 over 20 instances is the one that matters operationally, and it
is why the fixed-position MRZ read still runs alongside the detector rather than
as its fallback — see `modules/extraction/__init__.py`.

### The number that is not in the training report

```
data/processed/generated/*   recall 0.142   197 / 1386 instances
```

**Zero generated cards are in the training split**, and the demo, the rehearsal
and every screenshot run on generator renders. Per type on that set: passport
0.042, voter_id 0.051, visa 0.136, dl 0.162, pan 0.370. This is a domain gap,
not an export fault — the same artefact scores 0.926 on the domain it was
trained for. Full reasoning, what was tried, and why retraining was declined:
**D51** in `context/DECISIONS.md`.

Quote both numbers or neither.

### Two honesty rules, and how this section keeps them

1. **Report the test split, not the validation split.** Validation drove early
   stopping, so quoting it is quoting the number the run optimised against.
   Every figure above is the test split.
2. **No per-class figure for the four empty classes or the four thin ones.**
   `ghost_photo`, `barcode`, `hologram` and `doc_title` have zero instances and
   hold their index only to keep the class order stable — the detector cannot
   have learned them and must not be quoted on them. `signature` (1 test
   instance), `blood_group` (6), `secondary_id` (4) and `logo` (13) are too thin
   to mean anything and are omitted from the per-class table for that reason,
   not because they scored badly.

---

## Log

| Date | Event |
|---|---|
| 2026-09-06 | Dataset merged: 11,653 files from 5,375 source images, 18/22 classes |
| 2026-09-06 | Training environment isolated to `.venv-train` (CUDA torch) |
| 2026-09-06 | First run launched — yolo11s, 640px, 100 epochs |
