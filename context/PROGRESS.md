# Progress — what is done, what is remaining

Session tracker. Updated as work lands so a new session can pick up cold without
re-deriving the state of the repo. Last updated **2026-09-08**.

**Excluded from this file by decision:** training the 22-class field detector.
That handoff lives in `MODEL-TRAINING.md` and is running on an external GPU.
Everything *downstream* of the weights landing is tracked here.

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

## Done this session

Three agents were dispatched in parallel and all three were killed mid-flight by
a DNS/API outage. Two had landed work; the rest was finished directly. Every item
below is verified, not assumed.

| Work | Where | Verified by |
|---|---|---|
| `POST /rescore/batch` — one request for a page of events, single shared scoring path, 200-event cap, unreadable events omitted rather than failing the batch | `api/main.py` | 4 new tests in `tests/test_rescore.py` |
| Audit screen N+1 removed — one batched request, debounced 150 ms, results keyed by `event_id` and never by position | `frontend/src/screens/Audit.tsx`, `transport/socket.ts` | 3 new vitest tests; all 4 console gates |
| **Phonetic watchlist near-matching** (Layer E) — Soundex buckets + `difflib` ratio, stdlib only | `modules/validation/layer_e.py`, `core/store.py` | 5 new tests; measured on the real 8,256-row list |
| **Impossible transit now fires** (Layer F) — `post_id` column, additive migration, `config/posts.yaml` with haversine distance | `modules/validation/layer_f.py`, `core/store.py`, `config/posts.yaml` | 6 new tests (the layer had none before) |
| D46, D47 recorded; stale "VLM fallback is still a stub" docstring corrected | `context/DECISIONS.md`, `modules/extraction/__init__.py` | — |

```
python -m pytest -q     357 passed, 6 skipped   (was 342 passed, 6 skipped)
frontend npm run verify  4/4 gates, 34 tests    (was 31)
```

### The one design decision worth re-reading

`validation.watchlist.hit` is listed under `hard_fail` in all six profiles — a
`fail` from Layer E is RED, detain, on the spot. So phonetic matching emits
**`inconclusive`, never `fail`**. A guess about spelling must not be able to
detain anyone. Full reasoning in D46.

Measured on the loaded OFAC + UN list: index build 72 ms once per process,
lookup p50 0.06 ms / p95 0.11 ms, recall 56/60 on vowel-transliterated names,
0 false positives on 15 unrelated Indian names.

### Also measured this session

Extraction without the field detector, on the generated documents:

| Document | What is read today |
|---|---|
| passport | **MRZ read and check-digit verified** from its ICAO fixed position. The VLM fallback correctly stands down (D45). |
| aadhaar | nothing — no MRZ, and the VLM fallback did not recover a usable field |
| pan | nothing |

So DEMO.md's "nothing printed can be read" is right for Aadhaar and PAN and
**overstated for passport** — the MRZ path already switches on all five ICAO
check digits and the whole VIZ/MRZ cross-check. That is worth re-checking when
the detector lands and the rehearsal record is rewritten.

---

## Remaining after this session

### Code

| # | Work | Files | Size | Note |
|---|---|---|---|---|
| 1 | **Active liveness (blink EAR)** | `api/`, `modules/face/liveness.py`, `frontend/src/screens/Capture.tsx` | 1–2 days | **Defaulted to SKIP.** Cut-list item 2 in ROADMAP.md. Needs a new FaceMesh model + dependency that risks `tests/test_offline.py`. Passive liveness is deployed and measured. Revisit only if a panel asks. |
| 2 | **Devanagari OCR deployment** | run `scripts/fetch_ocr_models.py` | build-time | Not attempted this session. Blocked on a `paddle2onnx` toolchain, not on code — every wheel on PyPI imports `paddle`. Routed and honestly evidence-stringed today (D44). |

### Blocked on the detector weights landing

No code to write. These are currently unrunnable:

- 4 skipped tests in `tests/test_extraction.py` (lines 338, 356, 369, 387) go live.
- **Verify the sidecar class order matches the weights.** A disagreeing sidecar silently mislabels every field — `modules/extraction/detect.py:72` takes classes and `imgsz` from the sidecar, never from a constant.
- Re-run the rehearsal and rewrite the `# Rehearsal record` section of `context/DEMO.md`. Scenes 1, 2 and the payoff of 3 are marked "No" today.
- Re-run `scripts/measure_latency.py` — the number agent B produces this session is a **floor** with the reading path short-circuited, not the shipping number.

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
