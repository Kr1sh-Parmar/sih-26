# 22-class ontology coverage

Regenerate the merged set with `python data/tools/build_field_dataset.py`.

Every dataset is remapped onto the frozen 22-class ontology
(`TECHNICAL-SPEC.md` §5) so that **one** detector covers all six document
types (D17). Source class names never reach the model.

## Where we stand: 18 of 22 classes covered (was 11)

| Class | Instances | train / valid / test | Source |
|---|---|---|---|
| `id_number` | 9,838 | 7071 / 1888 / 879 | Aadhaar, PAN, Voter ID, DL, passport |
| `name` | 9,101 | 6553 / 1721 / 827 | all six types |
| `dob` | 7,889 | 5676 / 1491 / 722 | all six types |
| `father_name` | 4,861 | 3406 / 967 / 488 | Aadhaar, PAN, Voter ID, DL |
| `gender` | 3,854 | 2840 / 689 / 325 | Aadhaar, Voter ID, passport |
| `issuing_authority` | 2,359 | 1712 / 468 / 179 | Aadhaar, Voter ID, passport |
| `issue_date` | 1,599 | 1126 / 323 / 150 | Voter ID, DL, passport, visa |
| `emblem` | 1,511 | 1095 / 302 / 114 | Voter ID, Aadhaar |
| `person_photo` | 1,374 | 1002 / 274 / 98 | Voter ID, Aadhaar, DL |
| `address` | 959 | 672 / 183 / 104 | Voter ID, Aadhaar, DL |
| `qr_code` | 910 | 683 / 176 / 51 | Aadhaar |
| `expiry_date` | 792 | 563 / 169 / 60 | passport, DL, visa |
| `mrz` | 739 | 490 / 229 / 20 | passport |
| `nationality` | 699 | 509 / 142 / 48 | passport |
| `logo` | 144 | 104 / 27 / 13 | Aadhaar |
| `secondary_id` | 68 | 55 / 9 / 4 | Aadhaar VID |
| `blood_group` | 48 | 29 / 13 / 6 | DL |
| `signature` | 25 | 19 / 5 / 1 | Indian passport |
| `ghost_photo` | **0** | — | generator only |
| `barcode` | **0** | — | generator only |
| `hologram` | **0** | — | generator only |
| `doc_title` | **0** | — | generator only |

All 18 covered classes are present in **every** split. No source card spans two
splits (verified, 0).

### The four blocking zeros are closed

The previous handoff named four zeros that each killed a module. Three are
fixed and the fourth is now generator-only:

1. `qr_code` 0 → **910** — the Ed25519 anchor exists. Cryptographic trust
   class and the Scene 3 demo are buildable.
2. `expiry_date` 0 → **792** — `validation.expiry.expired` is detectable.
3. `person_photo` 449 (Voter ID only) → **1,374** across Voter ID, Aadhaar
   and DL. Passport photos are still uncovered — the passport VIZ sets we hold
   annotate text fields, not the portrait.
4. `ghost_photo` 0 → still **0**. Generator only.

### Thin classes — do not quote a per-class mAP on these

`signature` 25, `blood_group` 48, `secondary_id` 68, `logo` 144. Each comes
from a single small source. They exist so the class is not dead; they are not
enough to claim accuracy. The generator has to backfill them.

## Merged dataset

`data/processed/fields/` — one YOLO dataset on the 22-class ontology.

- **11,653 files from 5,375 unique source images**, 46,770 instances, 18 classes
- Split **8,320 / 2,321 / 1,012**, assigned **per source card**
- Images hardlinked — the merged set costs no extra disk
- 8,617 boxes dropped (see `build_field_dataset.py` for the per-source reasons)
- 504 files skipped as having no ontology box (document-level sets)

Verify the remap with
`python data/tools/verify_crops.py data/processed/fields <out.png> 4`.

### Two gates before adding any source

1. `python data/tools/audit_raw.py` — instances per class. Catches a project
   that advertises 33 classes and ships 27 boxes
   (`at-in/bangladeshi-passport-fields` does exactly this).
2. `python data/tools/peek_images.py <dir> <out.png>` — a contact sheet.
   **Not optional.** `fil-9zpqb/voter-01` passed gate 1 with 477 healthy
   `voter` boxes and was 146 Albion Online screenshots.

Then `python data/tools/draw_boxes.py <dir> <out.png>` for geometry —
Roboflow's YOLO export is not always trustworthy (see PROVENANCE).

### Train/test leakage — still handled

Source datasets ship augmented copies of one card spread across their own
train/valid/test splits. The builder ignores the shipped splits and assigns per
source image, keying on the filename prefix before `.rf.`. **Do not train on
any `data/raw/*/*/train` directory directly.**
