# Progress — what is done, what is remaining

Session tracker. Updated as work lands so a new session can pick up cold without
re-deriving the state of the repo. Last updated **2026-09-09**.

**The detector has landed.** `field_detector_22cls` came back from the external
GPU on 2026-09-09 and is deployed. `MODEL-TRAINING.md` is now a record rather
than a handoff, and everything this file listed as "blocked on the detector
weights landing" is done.

---

## Where the repo stands, 2026-09-09

```
python -m pytest          381 passed, 5 skipped     (baseline 379 / 7)
frontend npm run verify   4/4 gates, 34 tests
models/                   field_detector_22cls, face_detector, face_embedding,
                          face_liveness, florence2 (x4), rec_devanagari
/health                   missing = []   - empty for the first time
```

The five remaining skips are all inverse-condition tests: they run only when
weights are *absent*, to prove the degradation path. Their skipping is the
detector being present.

### Done this session

| | |
|---|---|
| **Detector deployed** | sha256 verified against the sidecar, class order matches `data.yaml`, the head-shape acceptance gate passes. The 4 previously-skipped tests are live. |
| **Detector re-measured through the shipping path** | New `data/tools/eval_detector.py`. **0.926** recall on its own test split - reproduces the run's 0.906 and proves the int8 export and decoder are correct - and **0.142** on the generated cards the demo uses. D51. |
| **A regression the detector introduced, found and fixed** | The fixed-position MRZ read was the `else` of `if ctx.field_boxes`. A detector that located the name and missed the zone therefore suppressed the read that needs no detector: passport lost all five ICAO check digits and fell to Florence-2 at **9,654 ms, coverage 0.522**. Now **3,684 ms, coverage 0.619**. Visa gained its MRZ too. |
| **Latency, re-measured** | aadhaar 6,596 -> **481 ms** p50, pan 6,006 -> **443 ms**, voter_id **483 ms** - three of six now inside the 1,020 ms budget. passport 2,251 / 7,130, dl 551 / 5,708, visa 1,238 / 1,306 remain over, for two named reasons. |
| **Memory, re-measured** | 170 MB warm and idle, ~190 MB working, **1,428 MB only once the fallback loads** - which the common documents no longer do. Bimodal and one-way. |
| **VLM fallback re-gated** | Fired on any single unread field; now on a *share* of attempted reads. DL: 42% -> 17% of runs, mean 2,777 -> 1,522 ms. D53. |
| **Active liveness built** - cut-list item 2 un-cut | OpenCV's bundled Haar eye cascade: no new model, no new dependency, `tests/test_offline.py` untouched and passing. Size floor `MIN_FACE_PX = 320` measured against phantom blinks on static images. `POST /screen` takes a `live_frames` burst. D52. |
| **D48 held** | Five mutation families on a passport, none clears. A forged document did not become clearable when documents became readable - the thing most at risk this session. |
| **Console wired to the backend** | `Capture` now carries a document-type selector, two-step camera capture and the captured bytes through to `Screening`, which posts them to `/screen`. `POST /screen` was reachable and uncalled until now. Fixture scenes retained as the backup path. D54. |
| **A false-match bug caught before it shipped** | The first draft of the camera path reused the document frame as the live frame. `_locate` takes `largest(detect(image))` for both the document portrait *and* the live face, so one frame handed in twice compares a face to itself: **cosine 1.0, every impostor holding someone else's card cleared**. The camera source now photographs the card and the traveller separately, and a test measures the 1.0 so the reasoning cannot be lost. D54. |
| **Two bugs inside the Docker image** | The image had been built here 40 hours earlier and **never run**. The first execution of `docker compose --profile verify run --rm verify` found that `import cv2` fails inside it (`rapidocr-onnxruntime` drags in plain `opencv-python`, which shadows the pinned headless build and wants `libGL.so.1`) and that `tests/test_generator.py` cannot be collected without the build-time dependencies. Both fixed; the build now asserts `import cv2`. D55. |
| **Docker: the offline gate passes** | `docker compose --profile verify run --rm verify` — the whole suite inside the shipping image with `network_mode: none` — **exits 0**. It had never been run. The earlier claim that Docker "was never built here" was also wrong: `docker images` showed `sih-screening-api:latest` from 40 hours before. |
| **Four bugs in the image, one in the suite's guards** | `import cv2` failed inside the container; `/screen/replay/` could not find its fixtures; the console's build context ignored nothing; `tests/test_generator.py` could not be collected. Plus the guard bug that hid them: the generator imports Faker inside its functions, so every `try: import data.generator` probe reported it available in the image where it is not. D55. |
| **A fifth, found by screening a document in the running container** | Every real document came back as an error frame: `Object of type float32 is not JSON serializable`. `requirements.txt` pinned everything exactly *except* numpy, a range — host 1.26.4, image 2.4.6 — and NumPy 2 keeps float32 through a division where 1.x widened it. **The suite and the shipping artefact were running different code.** numpy pinned, coordinates cast at source, and a test that screens a real PAN over the real socket. D56. |
| **Container gate closed** | `docker compose up` + `GET /health`: `missing: []`, every model loaded. Console image builds. The suite passes inside the image with the network taken away. |
| **The demo runs, in a browser, against the containers** | Upload an Aadhaar then a PAN on the capture screen: PAN reaches **CLEAR at 83% coverage with three cryptographic propagation findings**, and the session view draws all three edges. Three defects were between "endpoint reachable" and "demo works" — sessions were reset on every capture (killing propagation), the console's quality gate was stricter than the pipeline's, and the viewer drew a passport while screening an Aadhaar. D57. |
| **Face calibration captured** | 6 volunteers × 40 frames at 720p, consent recorded, verified as six distinct identities (same person 0.83–0.94, different people −0.09–0.13). Cards rendered at 3× because the portrait landed *below* `doc_min_px` at native size. |

### Known-open after this session

- **The domain gap is the headline limitation.** 0.142 recall on generated cards
  means 2-4 fields located per demo document, coverage 0.47-0.73, and only the
  PAN reaching GREEN. Retraining was considered and declined with reasons (D51).
- **Three of six document types miss the latency budget.** passport and visa on
  the untargeted MRZ band read (~740-950 ms of p50); dl on the Florence-2 tail.
  Tightening the MRZ crop is the identified next optimisation and was not
  attempted, because the crop is what the read accuracy rests on.
- **Scenes 1 and 2 still do not run as scripted** - now for a specific reason
  (detector recall on generated renders) rather than "nothing is read at all".
  Scene 3, the headline, runs as scripted for the first time. See the
  2026-09-09 rehearsal record in `context/DEMO.md`.
- ~~Active liveness is not wired to the console.~~ **Done** — the console posts
  captures, including the liveness burst, to `/screen`. D54.
- **Devanagari is still unproven on a scanned card.** Unchanged.
- **Face calibration is one physical step from done.** `var/calibration/` holds
  6 people × 40 frames and 6 rendered cards (`sheet_00.png`, `sheet_01.png`).
  Print them, scan at 600 dpi, save each crop as `person_NN/doc.jpg`, then run
  `calibrate_face.py --far 0.01`. **Do not pass `--apply`** — it flips
  `calibrated: true`, which deletes the officer-facing "not yet calibrated"
  caveat, and 6 people is 15 identity pairs: a pilot, not an operating point.
  Set the threshold by hand and leave `calibrated: false`.

---

## Baseline at the start of this session

```
python -m pytest -q     342 passed, 6 skipped
frontend npm run verify  4/4 gates (tsc -b, 31 vitest, build, check-offline.sh)
var/screening.db         13 screening_events, 1 trust_anchor, 4 face_gallery, 8256 watchlist
models/                  face_detector, face_embedding, face_liveness, florence2 (x4)
                         MISSING: field_detector_22cls
```

The four modules, fusion, the risk gate, the API, the reference issuer and the
console are all implemented and tested. The gaps below are not "write the
module" — they are measurement, data, and a short list of unwritten code.

---

## Done — session of 2026-09-08

```
python -m pytest     364 passed, 6 skipped   (baseline 342 / 6)
frontend verify      4/4 gates, 34 tests     (baseline 31)
```

### Three bugs found that would have been seen by the panel

| | |
|---|---|
| **A retyped passport scored GREEN** | `COMPARABLE_SOURCES` contained `qr`, so with no detector the VIZ/MRZ check compared the *signed payload* against the MRZ — two things the issuer made together — and reported six passes reading "matches printed" when nothing printed was read. A passport with its print band wiped and reprinted was cleared at coverage 0.752. Now AMBER 0.496. **The fix declines to clear it; it does not detect it.** Detection returns with the detector. |
| **The container told Indian passports that IND is not a country** | The 134 KB ISO 3166 table lives under `data/raw/`, excluded wholesale. Fallback left 16 ICAO codes, so `is_country_code("IND")` was False in every fresh clone and in the image. Table now ships; a missing table now reports `inconclusive` rather than blaming the document. |
| **The calibration session could not have been run** | `render.py` could only pick a portrait from the SFHQ pool by seed, so a volunteer's photo could not go on a card — and their real ID may never be used. `extras["portrait_path"]` now overrides, and a missing file raises rather than silently pairing one person's document with another's face. |

### Also landed

- `POST /rescore/batch`; audit screen N+1 removed (one debounced request, keyed by `event_id`).
- **Phonetic watchlist matching** — Soundex + `difflib`, stdlib only. Emits `inconclusive`, never `fail`, because `watchlist.hit` is `hard_fail` in all six profiles and a guess about spelling must not detain anyone. 56/60 recall, 0 false positives, p95 0.11 ms.
- **Impossible transit fires** — `post_id` column (additive; the audit log is never rewritten), `config/posts.yaml`, haversine. Default stays `not_applicable` on a single post. The layer had no tests; it has six.
- **Latency measured end to end for the first time**: passport p50 1,352 / p95 7,073 ms; Aadhaar and PAN ~6 s in the VLM fallback. Against the 1,020 ms budget it **does not fit**.
- **"Under 500 MB warm" corrected**: 154 MB idle, 185 MB working, **1,556 MB once Florence-2 loads** — which is every Aadhaar and every PAN today.
- Calibration/bias/liveness harnesses all proven to run; two `--apply` bugs fixed in `calibrate_face.py` that would only have bitten on the day. `calibrated: false` untouched.
- `docs/PROVENANCE-SLIDE.md`; pycountry declined (strict subset of what is already held).
- D46, D47 recorded.

### Landed after the agents finished

- **The fallback reported 4 ms for six seconds of work.** `ratify()` started its
  own clock, so `extraction.vlm.*` timed the ratification and dropped the
  Florence-2 run that produced the reads. On `gen_pan.png` the extraction stage
  went from **4 ms to 6,051 ms**. Every per-stage table was wrong by three orders
  of magnitude on exactly the documents that blow the budget.
- **Devanagari deployed** — see above.

### The fusion audit — a fourth bug, and the worst of them

Nothing had audited fusion this session, and the VIZ/MRZ bug suggested where
to look: evidence that is not independent of what it claims to corroborate.

**A signed card could disagree with its own signature and pass.** Layer D
compared a signed document against the *other* documents in a session and never
against the card carrying the signature. Measured with a genuinely verified
Ed25519 signature: payload DOB 1960-03-24, printed DOB 1988-11-02, **zero
failing signals**.

And `apply_crypto_precedence` then suppressed the backup evidence too — it was
fed every field in the payload, so `tamper.physical.font_consistency`, the
check that exists to catch reprinting, was dropped as noise on exactly the
document it was built for.

Fixed by `validation.signed.<field>_mismatch` (hard-fail, all six profiles) and
by `confirmed_fields()` — a field earns suppression by being corroborated, not
by appearing in a payload. D48.

```
python -m pytest     374 passed, 7 skipped
```

### The fusion audit, completed

`score.py` was audited earlier; `findings.py`, `gate.py` and `evidence.py` were not.
Finishing it found a fifth defect of the same family.

**A tamper heuristic could wear a signature's trust class.** A finding took the
strongest class present in its anchor group, so a clean cryptographic pass beside a
failing heuristic produced `trust=cryptographic` with a probabilistic headline — a
guess with the authority of a signature, in the officer's evidence list. It also kept
crypto precedence permanently disabled, so the documented suppression never fired.
Fixed: the class comes from the failing members, the pool the headline already used.

**The risk gate's signed/unsigned branch was dead** — it escalated above 0.25 while
everything escalated above 0.15 three lines later. Removed rather than repaired: the
obvious inversion would let a signature buy less scrutiny of the printing, which is the
D48 assumption. `evidence.py` audited clean. D49, D50.

```
python -m pytest     379 passed, 7 skipped
```

### Known-open, and deliberately so

- **Latency misses budget on every document type.** Expected to improve when the detector replaces the VLM fallback on MRZ-less documents, but it is not measured and must not be claimed.
- **Florence-2 memory.** 1.5 GB resident is a real constraint on checkpoint hardware.
- ~~Docker was never built here — not on PATH, engine down.~~ **That was wrong**, and it is worth recording why: `docker images` shows `sih-screening-api:latest` built here 40 hours earlier. Nobody checked; the claim came from `docker` not being on PATH, which is a different fact.
- **The container gate is closed.** The suite passes inside the image offline, `up` + `/health` reports `missing: []`, a real document screens end to end, and the console image builds. What is left of ROADMAP Phase 5 is physical: the cable-out run, three timed rehearsals, the backup laptop and the USB video. See the 2026-09-09 container section in `context/DEMO.md`.
- **Devanagari is unproven on a scanned card.** It reads clean renders; on the generated cards, where Hindi is only small static text and labels, reads come back as noise. Do not claim Hindi field reading until the print-and-rescan pass tests it.

---

## Remaining after this session

### Code

| # | Work | Files | Size | Note |
|---|---|---|---|---|
| 1 | ~~Active liveness (blink EAR)~~ | `api/main.py`, `modules/face/liveness.py`, `modules/face/__init__.py` | **done** | Built 2026-09-09 with OpenCV's bundled Haar eye cascade — no new model, no new dependency, so `tests/test_offline.py` is untouched and passing. `MIN_FACE_PX = 320` is measured, not chosen. Not wired to the console; see Known-open. D52. |
| 2 | ~~Devanagari OCR deployment~~ | — | **done** | Deployed 2026-09-08. `models/rec_devanagari.onnx`, reads clean renders at 0.94–1.00. Drops inter-word spaces; unproven on scanned cards. |

### ~~Blocked on the detector weights landing~~ — **all done 2026-09-09**

- ~~4 skipped tests in `tests/test_extraction.py` go live~~ — they run and pass.
- ~~Verify the sidecar class order matches the weights~~ — pinned by
  `test_the_class_list_is_the_frozen_22_class_ontology_in_dataset_order`, and
  the sha256 was checked against the sidecar on copy.
- ~~Re-run the rehearsal~~ — new record dated 2026-09-09 in `context/DEMO.md`.
- ~~Re-run `scripts/measure_latency.py`~~ — done for all six document types, plus
  memory. The 2026-09-08 figures are marked in `data/EXTRACTION.md` as the
  detector-less floor they were.

### Needs a person, not a keyboard

Longest lead times in the project. Start the first one first.

| # | Work | Unblocks |
|---|---|---|
| 1 | **Doc-vs-live calibration set**, ~500 pairs, 30–50 people. Then `python data/tools/calibrate_face.py`, which flips `calibrated: false` and replaces the `threshold: 0.32` TODO in `config/thresholds.yaml`. | Demo Scene 4; the FAR/FRR curve the operating-point screen renders |
| 2 | **Print-and-rescan pass** over the six generated documents. `context/DATA.md`: a model trained on clean renders falls apart on a real scanner. Also lets `data/tools/eval_tamper.py --source scanned` revisit the halftone gap (D25). | Scenes 1–3 on real paper; honest tamper numbers |
| 3 | **Bias evaluation.** `scripts/eval_bias.py` runs the moment FairFace or RFW is on disk. FairFace ships via Google Drive, RFW needs a signed licence. Recorded as *unmeasured*, not *small* (D41). FairFace gives false-match rate only (one image per person); RFW gives both halves. | The bias question in DEMO.md |
| 4 | **Spoof testing** against an actual printed photo and an actual phone screen. No longer blocked — liveness weights are deployed (D40). `scripts/eval_liveness.py` is a direction check, not this test. | Scene 4's second half |

### Human-blocked acquisitions (`data/PROVENANCE.md` §Outstanding)

- **ICAO Doc 9303 parts 3 and 4** — `icao.int` 403s any scripted fetch, needs a browser. This is the one real external standard the pitch leans on.
- **Official specimens** — PRADO, UIDAI PVC, ITD PAN, ECI EPIC, Parivahan DL.
- **Roboflow exports** — needs a private API key; the publishable `rf_…` key is rejected by the export API.
- `pip install pycountry` for ISO 3166-1.

### Phase 5 hardening and rehearsal

- Physical **cable-out run**. `tests/test_offline.py` proves no networked import; it does not prove the run. Three consecutive clean passes.
- `docker compose down -v && docker compose up` from clean, on the demo box.
- Memory ceiling with all sessions warm (the claim is under 500 MB).
- Provenance + licence slide — the table in `data/PROVENANCE.md` is written, it needs to become a slide.
- **Three timed rehearsals**, including the honest failure. Scene 5 works end to end today.
- Backup video of the live capture flow on a USB stick; backup laptop with the same image.

---

## Deliberately not doing — declined with reasons, not forgotten

Do not re-open these without reading the linked reasoning first.

| Item | Where the reasoning lives |
|---|---|
| `tamper.physical.photo_boundary` | `data/TAMPERING.md` — a third reading of one artefact copy-move and noise-residual already verify. Inflates the score exactly where it matters most (D8). |
| Guilloche continuity | D18 / D38 — measured three ways on real line-work; none separated a break. |
| Document-type classifier | The officer selects the type at the counter. Reports `not_applicable`. |
| pgvector HNSW gallery | `core/store.py:234` — O(n) scan is correct at demo scale and carries its own upgrade note. |
| Postgres / MinIO | `docker-compose.yml` header — the implementation went to SQLite and in-memory. The services were never built, so nothing is missing. |
| Hindi-vs-Latin cross-script check | D-entry in `context/DECISIONS.md` — needs transliteration; an approximate comparison feeding a mismatch signal is the failure just fixed in Layers C and D. |
