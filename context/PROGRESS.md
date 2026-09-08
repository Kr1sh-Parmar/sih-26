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

### Known-open, and deliberately so

- **Latency misses budget on every document type.** Expected to improve when the detector replaces the VLM fallback on MRZ-less documents, but it is not measured and must not be claimed.
- **Florence-2 memory.** 1.5 GB resident is a real constraint on checkpoint hardware.
- Docker was never built here — not on PATH, engine down. Phase 5's clean-build gate is still open and has to run on the demo box.

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
