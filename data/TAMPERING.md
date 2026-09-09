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

## Ghost portrait — added 2026-09-07

The one physical check that is a **comparison rather than a texture statistic**,
which is why it works where guilloche does not. The ghost is the same
photograph printed a second time, faded; a forger who replaces the portrait and
forgets the faded copy leaves two different people on one page.

Measured over 24 generated passports and Aadhaar cards, correlating both
portraits as equalised greyscale thumbnails:

| | |
|---|---|
| Genuine pairs | median **0.991**, minimum 0.952 |
| Portrait swapped, ghost left | median **0.732**, maximum 0.884 |
| At `ghost_agreement_min: 0.90` | genuine flagged **0.0%**, swaps caught **100.0%** |

The cut sits 6% below the lowest genuine score and was chosen from the clean
distribution alone (D26). Equalising first is what makes it work: the ghost is
printed lighter and softer by design, so comparing raw intensities would report
every genuine document as a mismatch.

**This number is optimistic and will not survive contact with a real document.**
Our generator makes the ghost a literal downscale of the same pixel array, so it
correlates near-perfectly. A real ghost is separately halftone-printed at a
different size and screen; genuine agreement will be materially lower and the
threshold will need re-fitting against real captures before anyone quotes 100%.

A missing ghost is reported as a **failure**, not a gap — if the detector found
the main portrait on the same page and no ghost on a document type that carries
one, the absence is the finding.

---

## Guilloche — measured three ways, still disabled

The original block said guilloche needed *"a reference drawing of a genuine
document of this type, which we have not built"*. `data/generator/` now draws a
real one — a tiled hypotrochoid, the curve a rose engine actually traces — so
that reason expired. Three formulations were measured against it:

| Formulation | Result |
|---|---|
| Low-energy islands (pattern erased in a rectangle) | **No separation.** Every family identical to clean. A retyped box is *higher* energy, not lower, because the redrawn text adds more edge than the erased pattern carried. |
| Inside-vs-outside-mask texture ratio | Separates, but **content-driven and inconsistent in direction** — retype 3.10, photo swap 0.14 on the same statistic. It measures "is this region texturally unusual", which is what `ela` and `noise_residual` already report; a third reading of one artefact is D8's correlated double count. |
| Phase continuity at the tile period | **Clean documents score 0.039–0.083** — near zero. There is no phase to break: the generator varies the figure per tile, so adjacent tiles are already uncorrelated. Mutations were indistinguishable. |

So `tamper.physical.guilloche_break` stays `inconclusive`, and **the reason an
officer reads has been corrected** — it is no longer "we have no template", it is
"measured, and it does not separate a break from ordinary variation".

One caveat that cuts the other way: the third result is partly a fact about *our*
guilloche. The generator deliberately varies the figure tile to tile. A real
passport's background may be more regular, in which case phase continuity would
become measurable. That is worth re-testing against a real specimen scan, and it
is the reason `physical.hypotrochoid` and the probe stay in the tree.

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

## The same checks, measured on generated documents

`python data/tools/eval_tamper.py --source generated` now runs the whole harness
over `data/generator/` output instead of scraped imagery. 24 documents:

| Check | Genuine flagged | Best family | Rate |
|---|---|---|---|
| copy-move | 4.2% | copy-move | **29.2%** |
| ELA | 4.2% | copy-move | 8.3% |
| SRM residual | 4.2% | recompress | 16.7% |

**Every number is worse than on scraped cards, and that is the honest reading of
it.** Generated documents are clean renders — no scanner noise, no lighting, no
print. ELA and the noise residual both work by finding a region whose *source*
differs from the rest of the page, and on a render there is barely any source
signature to differ. The sweep suggests `ela_z: 24.3` and
`noise_outlier_frac: 0.312` against the configured 16.8 and 0.078.

**Those suggestions were not adopted.** A threshold fitted to renders would be
badly wrong on the real captures the system actually screens. The scraped
numbers stay authoritative; the generated run exists to answer "where did your
data come from" with something reproducible, and to be re-run after the
print-and-rescan pass `data/PROVENANCE.md` still owes.

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
| 2026-09-07 | Ghost portrait implemented and measured: 0% false positives, 100% of portrait swaps caught on generated documents |
| 2026-09-07 | Guilloche measured three ways on real generated line-work; none separated a break. Block reason corrected from "no template" to the measurement |
| 2026-09-07 | `photo_boundary` declined - see below |
| 2026-09-07 | Evaluation harness extended to generated documents (`--source generated`) |
| 2026-09-07 | Module implemented: 5 digital checks, 3 physical, structural gaps named |
| 2026-09-07 | First measurement — every check fired on clean cards; metrics were content-driven, not source-driven |
| 2026-09-07 | ELA and SRM renormalised by local detail; copy-move given compactness, disjointness and pixel-correlation guards |
| 2026-09-07 | Copy-move false positives 35% → 21% → 5.0% |
| 2026-09-07 | Quantisation zig-zag bug found by unit test; every genuine upload had been flagged |
| 2026-09-07 | Halftone measured as non-discriminating; moved to a named structural gap |


---

## `photo_boundary` was declined, not forgotten

TECHNICAL-SPEC §7 Track A and MODULES.md both name it — physical cut-and-paste
edge artefacts. It has **no registered signal ID and no reliability weight**, so
it would fall through to `_default: 0.50` and borrow authority nobody assigned it.

It is not implemented, for one reason: the artefact it looks for is the same
pixel evidence `tamper.digital.copy_move` already verifies by correlation and
`tamper.digital.noise_residual` already reports. A third reading of one artefact
inflates the score in exactly the cases that matter most — D8, and the reason
findings exist instead of raw signal sums.

Adding it would need its own ID in CONTRACTS §1, its own weight, and evidence
that it sees something the other two miss. None of those exist, so it is a line
in this file rather than a check that fires.
