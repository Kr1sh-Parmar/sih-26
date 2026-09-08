# Extraction — the VLM fallback, measured

What Florence-2 actually does when the normal read path cannot, measured rather
than quoted from the spec. Regenerate by running a document through
`modules.extraction.vlm.generate` and timing it; the end-to-end figure comes
from `api.router.screen` on a generated passport with no detector weights.

Deployed by `python scripts/fetch_vlm_model.py` — build time only, four
quantised ONNX graphs, 275 MB. Loaded **lazily**: it is the one model in the
inventory not warmed at startup.

---

## Latency, 2026-09-07

| Document | Read | Regions returned |
|---|---|---|
| Passport | **7.34 s** | 20 |
| Aadhaar | 6.48 s | 7 |
| PAN | 5.90 s | 3 |
| Voter ID | 5.81 s | 9 |
| Full screening, passport, no detector | **8.2 s** | — |

**TECHNICAL-SPEC §4 says 1.5 s and §10 budgets +1,500 ms. The measured cost is
four to five times that.** The 8-second hard timeout in the same section was
written as a safety net against a hang; on this hardware it is a live
constraint, and a passport sits at 7.3 s against it. Some documents will time
out and fall through to "request re-capture", which is the designed behaviour
but not the intended frequency.

That number is CPU, single process, on the development machine. It is not the
demo box, and it should be re-measured there before anyone quotes it.

---

## What it reads well, and what it does not

Transcription quality splits cleanly, and the split matters more than the
headline:

| | |
|---|---|
| **Dates** | Exact. Every date on the generated passport came back character-perfect and in the right order. |
| **Words** | Close but not exact. `CHABRA` for `CHHABRA` — one dropped character in a surname. |
| **Identity numbers** | Unreliable. `M37011978` for `M3701978` — one inserted digit. |
| **Devanagari** | Garbage. `स्वारेवेवे` where the card reads `पासपोर्ट सं.`. Florence-2 has no Devanagari training; it renders plausible-looking nonsense. |
| **MRZ** | Not returned as a single strip. The model breaks the two lines into fragments, so the ICAO parser never sees a 44-character line. |

A dropped character in a surname is a misread. A dropped character in an
identity number is a *different person*, and it is exactly why nothing from this
module reaches validation unratified.

---

## What actually ends up in `ctx.fields`

On a generated passport, with no field detector deployed:

```
fields read : dob 1967-09-28, issue_date 2018-10-29, expiry_date 2028-10-26
verdict     : AMBER, coverage 0.28
```

All three dates correct. All three `unverified`, because no arithmetic anchor
confirms a date. Coverage lands at 0.28, well under the 0.70 floor, so the
verdict is AMBER "re-capture required" — which is `force MANUAL_REVIEW` from the
spec, arrived at through the coverage machinery rather than a new mechanism.

**The ratifier has not yet fired positively on a real read.** Passport's
arithmetic anchor is the MRZ, which the model does not return as a parseable
strip; Aadhaar, PAN and Voter ID anchor on the identity number, which it does
not read accurately enough to validate. So today the fallback contributes
correct dates and nothing that can be proven.

That is a real limitation and it is the honest headline: **the fallback improves
coverage and evidence, and it does not yet let a document be read to the point
of clearing.**

---

## Reading the MRZ without a detector — added 2026-09-07

The highest-value thing this module could do for a passport, and the previous
entry recorded that it did not do it. It does now, and **not with the VLM.**

ICAO 9303 fixes the machine-readable zone at the foot of the data page. That is
a published layout, so it needs no learned detector — crop the bottom quarter and
read it with the ordinary OCR path. Cheaper than Florence-2 (about 2 s against
7.3 s) and it returns a parseable strip, which Florence-2 does not.

This switches on all five ICAO check digits in Layer A and the whole VIZ↔MRZ
cross-check in Layer C — both written, tested, and until now unreachable on any
document, because with no detector `ocr.run` never executed at all.

### The bug underneath it

Every attempt read the two MRZ lines at **exactly 44 characters** and was then
thrown away. The crop also catches the microtext strip beneath, so the read
arrived as four lines of 44/44/22/18, the geometry gate saw four lines, and a
perfectly read MRZ was discarded because the crop was not tight.
`select_mrz_lines()` now picks the contiguous run matching a supported geometry.

It also un-broke `apply_positional_charset`, which returns untouched unless given
exactly two lines — so whenever a stray row was present, the ICAO positional
repair had been silently doing nothing.

### Measured, 30 generated passports

| | |
|---|---|
| Strip parsed | 28/30 |
| **Character-exact** | **21/30 (70%)** |
| Well-formed but wrong | 7/30 |
| Read time | ~2 s |

**70% is the number that shapes the design.** The 7 wrong reads produce a valid
44-character strip with one wrong character, which fails a check digit — and a
failed composite check digit is a hard fail. Handed straight to Layer A, **a
fifth of genuine passports would be detained on an OCR error**, and the officer
would be told so with arithmetic certainty.

Confidence cannot gate it. The misreads scored **higher** on average than the
exact reads:

| | median | range |
|---|---|---|
| exact reads | 0.751 | min 0.576 |
| misreads | 0.791 | max 0.904 |

Upscaling the band moved accuracy 67% → 72% at 3x. Not a fix.

### So the check digits test the read, not the document

On this path only, a strip whose own check digits disagree with its characters is
reported **unreadable**, not tampered. With a reader this accurate a failure is
far more likely a misread than a forgery, and "re-capture at a higher resolution"
is the honest sentence. After the change: **15 of 15 genuine passports AMBER,
none RED.**

The cost is real and is stated in D43: **this path can confirm a good MRZ and can
never report a tampered one.** It is smaller than the alternative — before this,
nothing was read — and it is temporary. `_read_mrz_field`, the detector-fed path,
keeps the geometry gate alone, so forgery detection survives there once a tight
crop puts the reader in a different accuracy regime.

---

## Devanagari — deployed 2026-09-08

`aadhaar`, `voter_id` and `dl` declare `ocr_lang: [en, hi]`. Nothing read the key.

Measured: the bundled `ch_PP-OCRv4_rec_infer.onnx` returns an **empty string at
confidence 0.00** on rendered Devanagari — not garbage, nothing at all. Empty is
the safe failure, since it becomes `inconclusive` rather than a wrong value.

| input | result |
|---|---|
| `प्रदीप घरत` | `''` at 0.00 |
| `भारत सरकार` | `''` at 0.00 |
| `PRADEEP GHARAT` | exact, 0.90 |
| `1991-08-04` | exact, 0.98 |

`ocr_lang` is live config now and the recogniser is chosen per profile, as a
**fallback rather than a switch**: every value on these documents is printed in
Latin as well as Devanagari, so Latin runs first and the second pass only fires
when it came back empty.

**Deployed.** `paddle2onnx` plus the PaddlePaddle runtime were installed as build-time tooling (never `requirements.txt`, which is the screening image) and `scripts/fetch_ocr_models.py` converted the PP-OCRv3 Devanagari recogniser to `models/rec_devanagari.onnx`, 9.0 MB, with its 167-entry dictionary — 86 Devanagari, 79 ASCII. The Dockerfile copies `models/`, so the container gets it without fetching anything at run time.

---

## What was achieved

- The four-graph generation loop runs: vision encoder → token embedding →
  encoder → KV-cached decoder, greedy, deadline-checked between tokens.
- `<OCR_WITH_REGION>` output is parsed into text plus pixel boxes.
- The 8-second timeout fires between decoded tokens, so it genuinely stops
  rather than merely intending to.
- Everything read passes through `modules/extraction/ratify.py`. A value that
  fails its checksum is discarded, never stored.
- Two triggers: a low-confidence OCR read, and — the one that matters now —
  **no field boxes at all**, which is every document until the detector returns
  from the GPU.
- The tokeniser's encode half runs at build time only. The screening path
  carries a decoder and no merge loop.

## What was not

- **Beam search.** The generation config asks for 3 beams; this is greedy.
  Three times the decode cost against an 8-second ceiling, for a transcription
  task with no fluency to optimise. Revisit if quality is the blocker.
- **Devanagari.** Not the fallback's to fix. It is the same gap D24 records for
  the OCR path, and it needs a recognition model, not a different reader.
- **Reading the MRZ.** The highest-value thing this module could do for a
  passport, and it does not do it. A cropped, contrast-normalised strip fed as
  its own image would likely work far better than the whole page; that is the
  obvious next attempt.
- **A measured accuracy rate.** Four documents is an anecdote. A proper pass
  over `data/processed/generated/` with per-field exact-match rates is what
  belongs here, and it is not done.

---

## Ceilings worth knowing

- The cross-attention KV cache is captured once, on the first decode step, and
  never refreshed. It has to be: on later steps the merged export's `If` node
  returns a placeholder for the branch it did not take, with a zero batch
  dimension, and feeding that back fails three steps later with a broadcast
  error nowhere near the cause.
- Field assignment without a detector is shape-matching, not understanding. A
  number that validates is that number, a date is a date, an MRZ line is an MRZ.
  **Names and addresses are read and deliberately not assigned** — a line of
  capitals could be the name, the father's name or an address, and a wrong guess
  lands where Layer C and Layer D compare against it.
- Dates are ordered birth, issue, expiry. True on all six types; a document
  issued before its holder was born would defeat it, and Layer C would then
  report a date-order failure an officer can read.

---

## Log

| Date | Event |
|---|---|
| 2026-09-07 | Ratifier written against the same checksum functions Layer A uses |
| 2026-09-07 | Florence-2 fetched, prompt tokenised at build time into the sidecar |
| 2026-09-07 | Decoder failed on step 3; cause was the refreshed encoder KV cache |
| 2026-09-07 | Loop working; passport read in 7.3 s, 20 grounded regions |
| 2026-09-07 | Measured: dates exact, identity numbers and names misread |
| 2026-09-08 | First end-to-end latency run. Passport p50 1,352 ms / p95 7,073 ms (n=30); aadhaar p50 6,596 / p95 7,924 (n=12); pan p50 6,006 / p95 6,355 (n=12). Over the 1,020 ms Tier 1 budget on every type. Floor for passport, ceiling for the MRZ-less types — no detector deployed |
| 2026-09-08 | The passport total is bimodal: 28/30 read the MRZ and land near 1.3 s, 2/30 fall to Florence-2 and land against its 8 s ceiling. Aadhaar and PAN take the VLM 12/12 |
| 2026-09-08 | Extraction stage p50 1,014 ms against a 250 ms budget, on the MRZ path alone. The cost is the untargeted read: `read_mrz` gets the bottom quarter of the page, not a crop |
| 2026-09-08 | The ratifier's signals carry no `latency_ms`, so the per-stage extraction row understates the VLM path by three orders of magnitude. Trust the end-to-end row on aadhaar and pan |
| 2026-09-08 | Memory measured (`scripts/measure_memory.py`): 154 MB warm and idle, 185 MB working on the MRZ path, **1,556 MB once Florence-2 loads**. DEMO.md's "under 500 MB warm" corrected |

### Measured, and the ceiling

Rendered with the generator's own `NotoSansDevanagari-Regular.ttf` and read back:

| Rendered | Read | Confidence |
|---|---|---|
| आधार | आधार | 1.00 |
| नाम | नाम | 1.00 |
| भारत सरकार | भारतसरकार | 1.00 |
| जन्म तिथि | जन्मतिथि | 0.94 |

**It drops inter-word spaces.** Harmless for the single-token fields this is a
fallback for, and it would matter for a multi-word name — which is why nothing
compares a Devanagari read against a Latin one. That check is still deliberately
not built: it needs transliteration, and an approximate comparison feeding a
mismatch signal is the failure already fixed in Layers C and D.

**On a real card it is harder than this table looks.** The generated cards carry
Devanagari only in static text and field *labels* at small point size, and reads
off those crops came back as Latin-ish noise. The clean-render numbers above are
the model working; they are not a claim about a scanned card.

| Date | Event |
|---|---|
| 2026-09-08 | Devanagari recogniser converted and deployed; reads clean renders at 0.94–1.00, drops spaces |
