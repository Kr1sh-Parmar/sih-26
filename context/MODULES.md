# Module Briefs

One page per module. Each has a scope, a definition of done, and the specific mistakes to avoid.

---

## Module 1 — Extraction

**Owner:** 2 people
**Input:** `ctx.image`, `ctx.doc_type`, `ctx.profile`
**Output:** `ctx.field_boxes`, `ctx.fields`, `ctx.faces['doc']`, signals under `extraction.*`

### Pipeline

```
quality gate → segmentation + quad warp → type classify
  → field detect (22-class) → OCR crops only
                            → MRZ strip → OCR-B → parse → check digits
                            → QR region → decode → payload
  → [low confidence] → Florence-2 → checksum ratifier
```

### Definition of done

- [ ] One YOLOv11s detector covering all six document types on the 22-class ontology
- [ ] Field-level OCR with per-field confidence in `NormalizedField`
- [ ] MRZ parser passing all ICAO 9303 published examples
- [ ] All five MRZ check digits implemented and independently tested
- [ ] QR decode and payload unpack
- [ ] Florence-2 fallback with 8 s hard timeout and re-capture fallthrough
- [ ] Checksum ratifier gating 100% of VLM output
- [ ] Normalisation: ISO-8601 dates, transliterated uppercase names, ISO 3166 codes
- [ ] p95 under 250 ms for the fast path

### Pitfalls

- **Do not OCR the whole page.** Crops only. This is 5–10× and it is the single biggest latency win.
- **Do not train six detectors.** One multi-class model.
- **Regex is not validation.** `^\d{12}$` passes for `000000000000`. Format checks belong in Layer B; the Verhoeff checksum belongs in Layer A. Module 1 outputs fields; Module 2 judges them.
- **Restrict the MRZ charset** to OCR-B alphanumerics plus `<`. Large accuracy gain, free.
- **VLM output is never trusted directly.** Ratify or mark `unverified`.

---

## Module 2 — Validation

**Owner:** 1 person (also owns the reference issuer)
**Input:** `ctx.fields`, `ctx.prior_docs`, trust anchor store, watchlist
**Output:** signals under `validation.*`

### Six layers

| Layer | Content | Trust class |
|---|---|---|
| A | Ed25519 signature; MRZ check digits; Verhoeff; PAN check char; EPIC; DL state+RTO | crypto / arithmetic |
| B | Field lengths, charsets, ISO 3166, gender codes, date formats | arithmetic |
| C | Date ordering, validity period, age consistency, **VIZ↔MRZ agreement** | arithmetic |
| D | Cross-document trust propagation | crypto when one side is signed |
| E | Watchlist, document-number history | arithmetic |
| F | Impossible transit, duplicate crossings | probabilistic |

### Definition of done

- [ ] Reference issuer: canonicalise → SHA-256 → Ed25519 → QR, with deterministic field ordering
- [ ] `TrustAnchorStore` keyed by issuer ID, `is_reference` flag driving the console disclosure
- [ ] All six documents' arithmetic anchors implemented and unit tested
- [ ] VIZ↔MRZ cross-check on every shared field
- [ ] Layer D: signed document's payload validates unsigned siblings in the same session
- [ ] Watchlist loaded from OFAC SDN + UN Consolidated with alias and transliteration matching
- [ ] All eight validation states representable: `AUTHENTIC`, `TAMPERED`, `INVALID_SIGNATURE`, `UNKNOWN_ISSUER`, `REVOKED`, `EXPIRED`, `MALFORMED_PAYLOAD`, `NO_CRYPTO_ANCHOR`
- [ ] Layers A–D complete in under 15 ms combined

### Pitfalls

- **We are not an issuing authority.** No document creation in the screening path. `issuer/` is separate and not importable from `api/`.
- **`NO_CRYPTO_ANCHOR` is the honest state** for a document with no verifiable signature. Do not silently treat it as pass.
- **Canonicalisation must be deterministic** — fixed field order, fixed encoding, fixed date format, explicit null handling. Identical logical data must produce identical bytes or signatures will fail randomly.
- **Never trust a public key supplied inside the payload.** Look it up in the trust anchor store by issuer ID.
- **Layer D is the headline demo.** Budget time for it.

---

## Module 3 — Tampering

**Owner:** 1 person (also owns synthetic data)
**Input:** `ctx.warped`, `ctx.field_boxes`, template reference
**Output:** signals under `tamper.*`

### Two tracks

**Physical (primary):** OCR-B conformance, layout geometry, guilloche continuity, ghost portrait, print halftone, photo boundary, stamp duplicate, stamp date logic.

**Digital (uploads only):** copy-move, EXIF software, double-JPEG, noise residual, ELA.

**Coverage:** full physical track for passport and Aadhaar; partial (font consistency, layout geometry, copy-move) for the other four.

### Definition of done

- [ ] Cheap checks in Tier 1 under 160 ms
- [ ] Deep forensics (copy-move, SRM noise) in Tier 2 only
- [ ] Every signal emits a `region` for the console overlay
- [ ] Reliability weights in `config/reliability.yaml`, defensible line by line
- [ ] Synthetic forgery generator with ground-truth masks
- [ ] Held-out evaluation on a **different mutation family** than training

### Pitfalls

- **It is noise residual inconsistency, not PRNU.** PRNU needs ~50 images from a known camera.
- **ELA is a visualisation, weight 0.30.** Say its limitations before a judge does.
- **No reference stamp template library.** Duplicate detection + date logic instead.
- **Metadata analysis does not fire on scanner input.** The scanner wrote the file.
- **Do not use Grad-CAM for localisation.** Copy-move keypoint matches give you real region highlights.
- **Do not train on your own splices and report the held-out number as accuracy.** It measures your generator, not forgery.
- **Stamps have no expected position** on a visa page. Drop position checks for stamps; keep them for fixed-layout documents.

---

## Module 4 — Face

**Owner:** 1 person
**Input:** `ctx.faces['doc']`, live frames
**Output:** signals under `face.*`

### Sub-modules

**4a — 1:1 verification.** InsightFace `buffalo_l`, single detection pass, cosine, calibrated threshold, three bands plus margin.

**4b — Liveness.** Passive (MiniFASNet) first; escalate to active (FaceMesh blink EAR) only on an uncertain score.

**4c — 1:N duplicate identity.** pgvector HNSW over prior screening events, flag near-duplicates with different document numbers. Escalated tier only.

### Definition of done

- [ ] Single detection pass — no double RetinaFace
- [ ] Detection fallback chain: primary → denoised → known photo region → explicit `face not found`
- [ ] Quality gates with **separate thresholds for document and live** faces
- [ ] Threshold calibrated on ≥500 doc-vs-live pairs from ≥30 people
- [ ] FAR/FRR curve exposed as an operator control
- [ ] Passive liveness verified against a printed photo and a phone screen
- [ ] 1:N gallery with a stricter threshold than 1:1
- [ ] Bias evaluation on FairFace/RFW, disparity documented
- [ ] Embeddings persisted; raw crops expire with the session

### Pitfalls

- **Never `((cos+1)/2)*100`.** Maps a stranger to 50.
- **Never use LFW thresholds** for doc-vs-live. Different domain.
- **`app.get()` already detects.** Calling RetinaFace first doubles the cost.
- **Bad document photo ≠ retake your selfie.** Ask for a higher-resolution *document* capture — the printed photo cannot be retaken.
- **Never fail silently on no-face.** Explicit status, always.

---

## Fusion

**Owner:** integration owner
**Input:** `ctx.signals`, profile weights, `reliability.yaml`
**Output:** verdict, score, ordered evidence cards

### Definition of done

- [ ] Hard-fail path returns RED without scoring
- [ ] Coverage floor: below 0.70 returns AMBER with "re-capture required"
- [ ] Anchor binding, including region→field resolution by IoU
- [ ] Noisy-OR within findings, weighted sum across findings
- [ ] Cryptographic precedence suppressing probabilistic disputes on signed fields
- [ ] Card ordering per `CONTRACTS.md` §7
- [ ] Full signal list persisted as JSONB for re-scoring
- [ ] Under 10 ms

### Pitfalls

- **Do not sum correlated signals.** One altered DOB fires four signals; summing inflates the score by 4× in exactly the cases that matter most.
- **Do not use XGBoost.** No real forgery distribution to fit on, and the officer needs a reason, not a number.
- **Ordering is by decision impact**, not module or raw weight. A hard fail with weight 0 outranks a 0.35 probabilistic finding.
- **Passing crypto signals always render.** They are the most reassuring thing an officer sees. Passing probabilistic signals collapse to a count.
- **Store signals, not cards.** Cards are a view.

---

## Officer console

**Owner:** integration owner

### Definition of done

- [ ] Side-by-side document view with tamper region overlay
- [ ] Extracted fields with per-field confidence and validation status
- [ ] Face pair side by side, verdict band, margin from threshold
- [ ] Evidence cards in the specified order, supporting signals under a disclosure triangle
- [ ] Trust class visible per line — the officer must see *how certain* each finding is
- [ ] `disclosure` string rendered for reference-issuer verifications
- [ ] FAR/FRR operating-point control
- [ ] Multi-document session view for trust propagation
- [ ] Results stream in — first verdict visible at ~450 ms

### Pitfalls

- **Do not show a bare percentage.** Score plus reasons, or nothing.
- **Do not hide the trust class.** Flattening a signature check and a texture heuristic into one number is exactly what this system exists to avoid.
- **Do not overclaim in the UI.** A reference-issuer verification must not look like a government verification.
