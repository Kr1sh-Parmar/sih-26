# Tampering — measured record

What Module 3 actually detects, measured rather than asserted. Regenerate with:

```
python data/tools/eval_tamper.py --limit 200
```

Numbers below: 200 genuine cards from `data/processed/fields/test/images`, the
held-out split of the field-detector dataset — real captures of real card
layouts, not renders. Each card also screened after each of the five mutation
families in `data/tools/mutate.py`.

---

## How the thresholds were chosen

**From the clean set alone.** Every cut is the score at which 5% of *genuine*
cards get flagged. No forgery took part in choosing any threshold, so every
family below is held out by construction.

That is stricter than CLAUDE.md's rule ("train on one mutation family, test on a
different one") and it exists for the same reason: a threshold tuned against the
forgeries it is then scored on measures the generator, not the forgery.

The 5% budget is a deliberate operational choice, not a round number. Tamper
signals are weighted probabilistic evidence, never hard fails — a false positive
costs an officer a second look, not a detention. It is still the number that
matters most: a check that misses a forgery costs one signal, a check that
accuses genuine documents makes an officer stop reading the whole evidence list.

---

## Results, 2026-09-07

| Check | Genuine flagged | Detects | Rate |
|---|---|---|---|
| `tamper.digital.copy_move` | **5.0%** | copy-move | **49.5%** |
| `tamper.digital.ela` | **5.0%** | photo swap | 36.0% |
| | | splice | 34.0% |
| `tamper.digital.noise_residual` | **5.0%** | retype | 23.0% |
| | | splice | 13.5% |
| | | photo swap | 5.0% |
| `tamper.physical.halftone` | 3.5% | *nothing* | 3.0–4.5% |

Copy-move is the one that works, and it is also the only check that yields a
region an officer can verify by eye — which is why D16 prefers keypoint matching
to Grad-CAM. ELA at ~35% is exactly what D15 says it is: a fragile visual aid,
weighted 0.30, not a verdict.

### Halftone does not work, and does not pretend to

Detection equals the false-positive rate at every threshold and under both
scorings tried (fraction of disagreeing tiles, and maximum deviation). At the
resolution these captures arrive at, the print screen consistency measurement
carries no information about tampering.

So `tamper.physical.halftone` reports **`inconclusive` with that reason**, and
costs coverage, rather than returning a coin flip wearing a number.
`physical.halftone()` and its evaluation are kept: on a 600 dpi flatbed scan the
screen is genuinely resolved, and re-running `eval_tamper.py` on such captures is
how the decision gets revisited.

---

## What these numbers are not

- **Not a forgery detection rate.** `data/tools/mutate.py` makes digital edits to
  a captured image. A professional physical forgery — printed, laminated,
  scanned fresh — is not obtainable and nothing here stands in for one. Every
  digital-file check passes such a document completely, because the file
  genuinely *is* a clean single-compression scan. It is the object that is fake
  (D12).
- **Not the physical track.** `layout_geometry` and `ocrb_conformance` are
  implemented and unit-tested but cannot run: they read `ctx.field_boxes`, and no
  detector weights are deployed (`MODEL-TRAINING.md`). They report `inconclusive`
  naming that reason.
- **Not everything the profiles declare.** Guilloche needs a vectorised template
  that does not exist; ghost portrait needs a `ghost_photo` class with zero
  training instances; stamps need a stamp class the 22-class ontology does not
  have. All three say so in the evidence string.

### Two checks the generator cannot exercise

| Check | Why not |
|---|---|
| `tamper.digital.exif_software` | The generator writes no EXIF. Covered instead by a unit test that builds an APP1 segment from the TIFF spec (`tests/exif_fixture.py`) — deliberately not by the same code that parses it. |
| `tamper.digital.double_jpeg` | It looks for a **non-standard quantisation table**, the fingerprint of an editor having written the file. OpenCV writes standard libjpeg tables, so the generator cannot produce the artefact. Covered by a unit test asserting OpenCV's own output at five qualities is recognised as standard. |

That second test earned its place immediately: the reference table was in
row-major order while a JPEG stores it zig-zagged, so **every genuine upload was
being reported as re-saved by editing software**. The check looked like it was
working the entire time.

---

## Ceilings worth knowing

- `double_jpeg` is quantisation-table *provenance*, not DCT coefficient analysis.
  True double-compression detection reads the quantised coefficients, which needs
  a second decode of the original bytes, and CLAUDE.md rule 6 forbids a module
  re-decoding the input. The evidence string says what was measured and nothing
  more. Upgrade path: the orchestrator hands the coefficients down beside
  `ctx.image`.
- `layout_geometry` compares against the median field position over labelled
  genuine cards (`data/tools/build_layout.py`), not a hand-drawn template. The
  measured spread is wide — a PAN date of birth moves ±5% of the page between
  captures — so a field must be genuinely elsewhere before it fires. That is the
  right way round: the check must never argue with a crooked scan.
- Fields measured on fewer than 50 genuine cards are recorded but never checked.
  `signature` has 25, from one source.
- Copy-move at 49.5%/5.0% is one operating point on a curve. Loosening the
  region-size floor to 0.002 of the page raises detection a few points and
  doubles the false-positive rate; the sweep is in `eval_tamper.py`.

---

## Log

| Date | Event |
|---|---|
| 2026-09-07 | Module implemented: 5 digital checks, 3 physical, structural gaps named |
| 2026-09-07 | First measurement — every check fired on clean cards; metrics were content-driven, not source-driven |
| 2026-09-07 | ELA and SRM renormalised by local detail; copy-move given compactness, disjointness and pixel-correlation guards |
| 2026-09-07 | Copy-move false positives 35% → 21% → 5.0% |
| 2026-09-07 | Quantisation zig-zag bug found by unit test; every genuine upload had been flagged |
| 2026-09-07 | Halftone measured as non-discriminating; moved to a named structural gap |
