# SIH 26188 — AI-Based Fake Identity & Document Screening System
### Technical Specification, System Architecture & Dataset Inventory

**Problem Statement ID:** 26188
**Organisation:** Ministry of Home Affairs
**Department:** Sashastra Seema Bal (SSB), Police II Division
**Category:** Software

---

## Table of Contents

1. [Problem Statement Summary](#1-problem-statement-summary)
2. [Critical Assessment — Corrections to Common Approaches](#2-critical-assessment)
3. [System Architecture](#3-system-architecture)
4. [Module Specifications](#4-module-specifications)
5. [Risk Fusion Engine](#5-risk-fusion-engine)
6. [Dataset Inventory](#6-dataset-inventory)
7. [Roboflow Universe — Verified Assessment](#7-roboflow-universe-verified-assessment)
8. [Synthetic Data Generation Plan](#8-synthetic-data-generation-plan)
9. [Technology Stack](#9-technology-stack)
10. [Repository Structure](#10-repository-structure)
11. [Development Roadmap](#11-development-roadmap)
12. [Legal & Compliance](#12-legal--compliance)
13. [Resource Links Appendix](#13-resource-links-appendix)

---

## 1. Problem Statement Summary

### Operational context

Border checkpoints process thousands of identity documents daily — passports, visas, national ID cards, permits, travel authorisations. Manual verification is slow, error-prone, and cannot reliably detect sophisticated forgeries.

**Threats to be addressed:**
- Fake passports and visas
- Altered photographs
- Modified dates of birth
- Tampered visa stamps
- Identity impersonation
- Multiple identities used by the same person
- Expired or blacklisted travel documents
- High passenger volume causing delays

### Strategic note on SSB's mandate

Sashastra Seema Bal is the border guarding force for the **India–Nepal (1,751 km)** and **India–Bhutan (699 km)** borders. These are *open borders* — Nepali and Bhutanese citizens do not require a passport or visa to enter India under the respective friendship treaties.

This changes the document mix in the field significantly:

| Document | Relevance to SSB |
|---|---|
| Nepali Citizenship Certificate | Very high — primary ID at Indo-Nepal crossings |
| Indian Aadhaar / Voter ID / Passport | Very high — Indian nationals crossing |
| Nepali passport | High |
| Bhutanese permits and Voter ID | Moderate |
| Third-country passports + visas | Lower volume, higher risk |

**Recommendation:** build the international passport/visa pipeline (it demonstrates ICAO-standard rigour), but make the *demo narrative* about the documents SSB actually inspects. Explicitly acknowledging the open-border reality signals domain understanding that most competing teams will not have.

### Required modules

| Module | Objective |
|---|---|
| 1 — OCR Extraction | Extract all relevant fields from identity documents |
| 2 — Document Validation | Verify extracted information against official standards |
| 3 — Tampering Detection | Detect digitally or physically altered documents |
| 4 — Face Verification | Confirm document owner matches presented individual |
| + Risk Score | Fuse all signals into an actionable decision for the officer |

### Expected impact

- Reduce verification time from minutes to seconds
- Improve forged/tampered document detection
- Standardise screening decisions across checkpoints
- Enable data-driven risk assessment
- Create a digital trail for investigation and intelligence

---

## 2. Critical Assessment

These are the errors most commonly made on this problem statement. Fixing them early saves weeks.

### 2.1 Metadata analysis is near-useless at a physical checkpoint

If the officer scans the document at the counter, **the scanner writes the file**. EXIF will always look clean, timestamps will be consistent, and the image will be single-JPEG. A professionally printed physical forgery passes ELA, double-JPEG detection, and EXIF checks *completely clean* — because the image genuinely is a fresh scan. It is the physical object that is fake.

**Tampering detection therefore splits into two tracks that share almost no code:**

| Track | Applies to | Techniques |
|---|---|---|
| **Digital file forensics** | Pre-submitted files — e-visa uploads, emailed scans, online applications | ELA, double-JPEG/DCT, EXIF, copy-move, splice segmentation |
| **Physical artifact forensics** | Live scans at the counter | OCR-B font conformance, layout template geometry, guilloche continuity, print halftone analysis, hologram/OVD presence, ghost portrait check, stamp geometry |

Most teams build ~90% digital. The SSB use case is ~90% physical. **Build the physical track as primary.**

### 2.2 PRNU is the wrong term and the wrong technique

PRNU (Photo Response Non-Uniformity) is sensor-noise fingerprinting. It requires ~50+ images from a *known* camera to estimate a reference pattern. You have one image from an unknown device.

What you can actually do is **noise residual inconsistency**: apply SRM/high-pass filters, then look for regions whose residual statistics differ from their surroundings. Related concept, different method. Do not say "PRNU" in your pitch.

### 2.3 ELA is weaker than commonly claimed

Error Level Analysis is useful as a *visualisation* for the officer, but as a signal it is fragile:
- Global recompression after tampering flattens the difference
- Mixed-quality source images produce false bright patches
- PNG and PDF input yield nothing at all

Keep it, weight it low, and never let it carry a forgery claim alone. State the limitation before a judge does.

### 2.4 A per-country stamp template library is not achievable

Thousands of entry/exit stamp variants exist across countries and ports, with no public reference set. Replace template matching with logic that needs no templates:

- **Duplicate stamp detection** — two stamps matching at pixel level are copy-pasted. Strongest and cheapest stamp signal.
- **Date-logic consistency** — stamp date within visa validity, entry before exit, stay duration within permitted duration.
- **Count vs declaration** — number of entry stamps vs declared trips.
- **Placement validity** — stamp on a page that should not carry one.

### 2.5 The synthetic-training trap

If you generate synthetic splices and train a CNN on them, it learns *your splice generator's artifacts*, not forgery. You will score 99% on your held-out set and near-chance on real forgeries.

**Mitigation:** train on one tampering method family, test on a *different* one. Train on SIDTD (crop-and-replace + inpainting), test on IDNet or MIDV-Holo. Report both numbers. This is more credible than a single high number.

### 2.6 The face match score rescaling is misleading

The common formula `((cos + 1) / 2) * 100` maps:

| Cosine similarity | Reality | Displayed score |
|---|---|---|
| 0.00 | Total stranger | **50** |
| 0.16 | Confident impostor | **58** |
| 0.60 | Strong genuine match | **80** |

An officer reads "58%" as "more than half, probably him." The scale is wrong in the direction that admits fraudsters.

**Fix:** either fit a logistic calibration on your genuine/impostor score distributions so the number is an actual probability, or drop the percentage and show a three-band verdict plus the margin from threshold (`cos 0.52, threshold 0.40, +0.12 above`).

### 2.7 Document-photo-to-live is a different domain from live-to-live

Passport photos are printed, halftone-screened, overprinted with guilloche and holograms, sub-300 DPI once scanned, and often up to ten years old. ArcFace degrades measurably.

**Calibrate a separate threshold on doc-vs-live pairs.** It will be lower than the standard live-to-live figure. Using 0.4 unmodified produces an FRR that makes the system unusable.

### 2.8 Redundant detection wastes latency

A common pattern runs `RetinaFace.detect_faces()` then `FaceAnalysis.get()` — which internally runs RetinaFace *again*, plus alignment, plus embedding. That is two full detector passes per face, four per comparison.

**Fix:** use `FaceAnalysis` once and read `.embedding` off the result. Set `det_size=(320, 320)` — the `buffalo_l` default of 640×640 is unnecessary for a cropped ID photo.

### 2.9 Liveness is lower priority than it appears

At a manned SSB checkpoint the officer is physically looking at the person. A printed-photo attack is not a realistic threat there. Liveness matters for e-gates and remote e-visa enrollment.

Build it — it demos well and future-proofs the e-gate story — but do not let it consume time needed for MRZ and physical-forgery work. Scoping this explicitly reads as operational understanding.

### 2.10 Missing sub-module: 1:N duplicate identity search

"Multiple identities used by the same person" is **not** 1:1 verification. It is 1:N search: embed the live face, query a gallery of prior enrollments, flag near-duplicates carrying different document numbers.

Different code path, different index, different threshold. Most teams miss this. It is explicitly named in the problem statement.

### 2.11 FAR/FRR is an operator decision, not a constant

"Tune for very low FAR" is not a plan. At 5,000 passengers/day, an FRR of 2% is 100 secondary inspections daily.

**Expose the FAR/FRR curve in the UI** and let the checkpoint commander set the operating point. Far stronger than a hardcoded threshold.

### 2.12 Roboflow is a build-time tool, not a runtime dependency

Border checkpoints have no reliable internet, and hosted inference adds 200–800 ms per call. Both violate the core requirements.

**Use Roboflow to annotate, version, and train. Then export weights and run them locally** — ONNX in your own runtime, or Roboflow Inference in a Docker container on the same box. At demo time nothing leaves the machine. "Fully air-gapped operation" is a differentiator with MHA.

### 2.13 What Roboflow does *not* provide

| Assumption | Reality |
|---|---|
| "OCR is available on Roboflow" | Roboflow does detection, segmentation, classification. It draws boxes; it does not read characters. You still need PaddleOCR/docTR, plus the parser, check-digit logic, and field normalisation. Roboflow covers ~25% of Module 1 |
| "Face detection is available on Roboflow" | InsightFace `buffalo_l` bundles RetinaFace detection + 5-point alignment + ArcFace embedding, optimised. A community Roboflow face detector gives worse boxes, no landmarks, and an extra model in your latency budget. Roboflow's only genuine Module 4 contribution is the anti-spoofing classifier |
| "Tampering must be built by us" | **Correct.** But Roboflow is still the right *tool* for building it — annotation, versioning, training on your synthetic forgery set |

---

## 3. System Architecture

### 3.1 Three separate architectural decisions

The "module-wise vs document-wise" question conflates three things. The answer differs for each:

| Axis | Decision | Rationale |
|---|---|---|
| **Code organisation** | Module-wise | Each module is a package with one clean entry point returning typed signals. Testable, parallelisable across teammates |
| **Execution routing** | Document-wise | A YAML profile per document type decides which checks run and how they are weighted |
| **Deployment** | **Single process** | This is the latency answer — see 3.3 |

### 3.2 Runtime layers

```
┌─────────────────────────────────────────────────────────────┐
│  BROWSER CLIENT                                             │
│  getUserMedia capture · officer console · WebSocket stream  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  ORCHESTRATION API  (FastAPI)                               │
│  Profile router · decode ONCE · async fan-out · SSE/WS      │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  INFERENCE CORE — one process, all models warm in memory    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Rules engine │  │ Vision models│  │ Forensics        │   │
│  │ No ML        │  │ ONNX int8    │  │ ELA, copy-move,  │   │
│  │ < 10 ms      │  │ warm         │  │ noise, metadata  │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  RISK FUSION & EVIDENCE                                     │
│  Weighted score · hard-fail overrides · per-signal reasons  │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  DATA LAYER                                                 │
│  Postgres · pgvector face gallery · MinIO · audit log       │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 Three properties that matter more than the boxes

**Decode once.** The orchestration layer decodes the upload into a single numpy array and passes it *by reference* to every module. No module re-reads bytes from disk or receives an image over HTTP.

This is why the inference core is one process, not four microservices. Microservices per module means each gets the image via encode → HTTP transfer → decode → infer → encode result. A 3 MB scan serialised four times costs more wall-clock than the inference itself.

**Rules engine runs first and can short-circuit.** MRZ checksum failure, expired document, or watchlist hit returns RED before any model is touched. That path is under 200 ms with no CV at all.

**Results stream as they land.** The client holds a WebSocket open:

| Time | What appears |
|---|---|
| ~300 ms | Validation verdict |
| ~700 ms | Face match |
| ~1.2 s | Tampering analysis |

The officer reads the first result while the third is still computing. Perceived latency is what you are actually optimising.

### 3.4 Document profiles (execution routing)

```yaml
# profiles/passport.yaml
passport:
  checks: [mrz, viz_fields, face_doc, stamps, ela, copy_move, ocrb_font]
  weights:
    mrz_checksum:        0.30
    viz_mrz_mismatch:    0.35
    face_match:          0.20
    tamper_heatmap:      0.10
    stamp_duplicate:     0.05
  hard_fail: [mrz_composite_checksum, expired, watchlist_hit]

# profiles/aadhaar.yaml
aadhaar:
  checks: [qr_verify, viz_fields, face_doc, hologram, guilloche]
  weights:
    qr_signature:        0.50   # cryptographic — dominates
    qr_viz_mismatch:     0.25
    face_match:          0.20
    hologram_present:    0.05
  hard_fail: [qr_signature_invalid, verhoeff_checksum_fail]
```

Aadhaar's signed QR is a **cryptographic** integrity check — stronger than passport MRZ check digits. See section 4.2.

### 3.5 Latency budget (CPU-only, ~1.4 s p95)

| Stage | Budget |
|---|---|
| Decode, deskew, quality gate | 80 ms |
| Doc type + segmentation crop (yolov11n-seg @ 640) | 40 ms |
| MRZ detect + OCR the strip only | 120 ms |
| VIZ field boxes + OCR crops only | 250 ms |
| Face detect + embed, both images | 200 ms |
| ELA + copy-move + stamp checks | 150 ms |
| Fusion | < 5 ms |

**Five things that actually move the number:**

1. **Never OCR the whole page.** Detect field regions, OCR only those crops. 5–10× win. This is why the field-detection model matters more than the OCR engine choice.
2. **Gate on cheap deterministic checks.** MRZ checksum, expiry, watchlist hash — all under 200 ms, no models. Hard-fail returns RED without touching the CV stack.
3. **Stream over WebSocket** as each module finishes. Nearly free, transforms perceived latency.
4. **ONNX Runtime, int8 quantised**, `intra_op_num_threads` tuned to the box, sessions created once at startup — never per-request.
5. **Stay CPU-only and say so.** Border posts do not have GPUs. "Runs on a 4-core box with no internet" beats "0.3 s on an A100" with this audience.

### 3.6 The signal contract

Freeze this in week one. It is what lets four people work in parallel without integration hell.

```python
from dataclasses import dataclass

@dataclass
class Signal:
    id: str                  # "mrz.checksum.dob"
    module: str              # "validation" | "tamper" | "face" | "extraction"
    verdict: str             # "pass" | "fail" | "inconclusive"
    confidence: float        # 0.0 - 1.0
    weight: float            # from the document profile
    hard_fail: bool          # bypasses the weighted score entirely
    evidence: str            # "MRZ DOB 1991-03-04 != printed 1991-08-04"
    region: tuple | None     # bbox for the UI overlay
    latency_ms: int
```

Every module returns `list[Signal]`. Fusion consumes only this. No module imports another module's internals.

---

## 4. Module Specifications

### 4.1 Module 1 — OCR Extraction

**Pipeline:** capture → quality gate → segmentation crop → perspective correct → doc type classify → field detect → OCR crops → parse → normalise

**The MRZ is the highest-value component.** Every ICAO-compliant passport carries a machine-readable zone: two lines of 44 characters encoding name, document number, nationality, DOB, sex, and expiry — each with **check digits**, plus a composite check digit over the whole thing.

This gives you two things nearly free:

1. **Self-validating data.** A forged document number that fails its own check digit is caught by arithmetic. No ML.
2. **A cross-check axis.** Amateur forgers edit the printed date of birth (the Visual Inspection Zone) and forget the MRZ, or vice versa. **VIZ ↔ MRZ mismatch is your most reliable, most explainable tamper signal** — and it demos beautifully, because you can show exactly which two fields disagree.

**Build MRZ parsing in week one.** It makes Modules 1 and 2 largely the same code and gives Module 3 a strong non-ML signal to lean on.

**Good news on Indian passports:** they use standard ICAO TD3 format. All MRZ work on MIDV-2020's European passports transfers directly — same two 44-character lines, same check-digit algorithm, same OCR-B font. Only the VIZ layout differs, which is a field-detection retrain, not new science.

**OCR configuration:**
- Engine: PaddleOCR or docTR (better on ID-card layouts than Tesseract; both have ONNX exports)
- MRZ strip: restrict the charset to OCR-B alphanumerics + `<`. Massive accuracy gain.
- VIZ fields: OCR crops only, never the full page

**Extracted fields:**

| Passport | Visa | Aadhaar | PAN |
|---|---|---|---|
| Name | Visa Number | Name | Name |
| Passport Number | Visa Type | Aadhaar (masked) | Father's Name |
| Nationality | Entry Validation | DOB / YOB | DOB |
| Date of Birth | Stay Duration | Gender | PAN Number |
| Date of Expiry | Validity dates | Address | |
| Gender | Passport Number ref | VID | |

### 4.2 Module 2 — Document Validation

Six layers. **The first four require zero ML, zero network, and run in under 10 ms combined.** They are the backbone and the fast path.

#### Layer A — Intra-document integrity (cryptographic or arithmetic)

| Document | Check |
|---|---|
| Passport | Five MRZ check digits: document number, DOB, expiry, optional data, composite |
| Aadhaar | **Verify the UIDAI-signed Secure QR.** Also Verhoeff checksum on the 12-digit number |
| PAN | Format + structural rules |
| Driving Licence | State code + RTO code validity |

**The Aadhaar QR is your single strongest asset for Indian documents.**

The Secure QR contains the last 4 digits of the Aadhaar number, name, address, gender, date of birth, and photograph — signed with UIDAI's digital signature, making it tamper-proof. The public certificate for signature validation is downloadable from UIDAI.

This means you can verify an Aadhaar card **cryptographically, offline, with certainty** — not a confidence score, a signature that validates or does not. If someone photoshops the DOB, the printed text no longer matches the signed payload, and the QR cannot be forged without UIDAI's private key.

Validation flow: verify QR signature → compare signed payload against OCR'd printed text → any mismatch is a hard fail with cryptographic proof. This requires **no training data at all**.

#### Layer B — Format and schema conformance
- Field lengths and character sets per ICAO Doc 9303
- Nationality against ISO 3166-1 alpha-3 (note MRZ quirks: `D` for Germany, GBR subtypes)
- Date formats, gender codes (`M` / `F` / `<`), document type codes

#### Layer C — Cross-field logic within one document
- DOB < issue date < expiry date
- Expiry − issue equals a standard validity period (India: 10 years adult, 5 years minor). An 8-year window is fabricated.
- Age at issue consistent with the validity granted
- Expiry not in the past

#### Layer D — Cross-document consistency *(most teams miss this)*
- Name on visa matches passport (after transliteration normalisation)
- Passport number printed on the visa matches the passport's own number
- **Visa validity cannot extend beyond passport expiry** — a visa outliving its passport is a hard fail
- Stamp dates fall inside visa validity

#### Layer E — External lookups (mocked for demo)
- Watchlist / blacklist by document number and by name + DOB
- Lost and stolen document registry (Interpol SLTD is the real system; seed a local table)
- Prior-crossing history for this document number

#### Layer F — Temporal and behavioural
- Same document number scanned at two checkpoints too far apart in too little time
- Exit without matching entry, or duplicate entries
- Free, because you already have the audit log

**Layers A–D** are deterministic, explainable, instant — the backbone.
**Layers E–F** turn this from a screening tool into an intelligence tool, which is the language the problem statement uses.

### 4.3 Module 3 — Tampering Detection

Two tracks (see 2.1). Present this as a **signal ensemble** where each signal is independently explainable — never as "we trained a model that detects fakes."

#### Track A — Physical artifact forensics (PRIMARY for SSB)

| Signal | Method |
|---|---|
| OCR-B font conformance | Character stroke width, glyph geometry in the MRZ strip vs the ICAO spec |
| Layout template geometry | Field positions relative to document corners vs the official template |
| Guilloche continuity | Security background pattern must be continuous under text and around the photo |
| Ghost portrait | Present, correctly positioned, and matching the main photo |
| Hologram / OVD | Presence and chromaticity behaviour (multi-angle capture) |
| Print halftone analysis | Genuine printing has a specific screen pattern; inkjet forgeries do not |
| Photo boundary | Physical edge artifacts where a photo was cut and glued |
| Stamp logic | Duplicate detection, date consistency, count vs declaration |

#### Track B — Digital file forensics (SECONDARY, for e-visa flow)

| Signal | Method | Weight |
|---|---|---|
| Error Level Analysis | Recompress at known quality, diff. Good for the officer overlay | Low |
| Noise residual inconsistency | SRM/high-pass filter, regional statistic outliers | Medium |
| Copy-move detection | SIFT/ORB keypoint matching within one image | High |
| Double-JPEG / DCT | Compression history analysis | Medium |
| Metadata | `exiftool` / `pikepdf`. `Software: Adobe Photoshop` on a "scan" is a free win | High when present |
| Learned localisation | Segmentation model producing a heatmap, not a binary label | Medium |

**Explainability:** use a **segmentation model outputting a mask**, not Grad-CAM on a classifier. Grad-CAM localisation is weak and hard to defend under questioning.

**Build order:** classical signals first (they always work, no data needed), learned model second (it might not).

### 4.4 Module 4 — Face Verification

**4a — 1:1 Verification**

```
Document image ──► detect ──► align ──► embed ──┐
                                                 ├──► cosine ──► calibrated verdict
Live capture ──► liveness ──► detect ──► embed ──┘
```

| Component | Choice |
|---|---|
| Detection + alignment + embedding | InsightFace `buffalo_l`, single pass, `det_size=(320,320)` |
| Embedding | ArcFace, 512-d |
| Metric | Cosine similarity |
| Threshold | **Calibrated separately on doc-vs-live pairs** — not the live-to-live default |
| Output | Three bands (MATCH / MANUAL_REVIEW / MISMATCH) + margin from threshold |

**Quality gates before comparing** (reject and prompt re-capture rather than compare badly):
- Blur — Laplacian variance threshold
- Brightness / contrast
- Face size relative to frame
- Yaw / pitch / roll angle

**4b — 1:N Duplicate Identity Search**

The problem statement's "multiple identities used by the same person." Embed the live face, query a pgvector index over all prior enrollments, flag near-duplicates carrying *different* document numbers. Separate threshold from 1:1 — 1:N needs a stricter one because you are running many comparisons.

At demo scale, `pgvector` with an HNSW index is plenty. Mention FAISS/Milvus for production scale; do not build it.

**Bias evaluation is mandatory here.** Face recognition has documented accuracy disparities across demographics (see NIST FRVT). In a border-security context with real consequences, validate across skin tones, ages, and genders using FairFace or RFW, and report the disparity. A panel that asks this question and gets a real answer will remember it.

**Privacy:** store embeddings + audit logs, not raw face images. Encrypt at rest. Do not retain live captures beyond the session unless legally mandated.

---

## 5. Risk Fusion Engine

**Do not use gradient boosting.** Two reasons: you have no real forgery distribution to train weights on, and a border officer detaining someone needs a *justification*, not a number.

### Design

```
RISK = Σ (wᵢ × sᵢ)  →  GREEN (clear) / AMBER (secondary) / RED (detain)
```

**Hard-fail conditions bypass the score entirely** and go straight to RED:
- MRZ composite check-digit failure
- Aadhaar QR signature invalid
- Document expired
- Watchlist hit
- Visa validity exceeds passport validity

**Every contributing signal surfaces as an evidence card:**

> `MRZ DOB 1991-03-04 ≠ printed DOB 1991-08-04` — weight 0.35 — [highlight region]

Keep weights in the YAML profile so you can tune them live on stage.

### Officer console requirements

The UI is where you win or lose. Required elements:

- Side-by-side document view with tamper heatmap overlay
- Extracted fields with per-field confidence and validation status
- Face match pair, side by side, with the verdict band
- Risk band with the **evidence list**, not just a number
- FAR/FRR operating-point control
- Audit trail: score, model versions, timestamp, officer ID

**Human-in-the-loop.** This system assists, never replaces, the officer's decision — especially at MANUAL_REVIEW and near-threshold scores. State this explicitly in the pitch.

---

## 6. Dataset Inventory

### 6.1 The honest framing

**There is no public dataset of real forged passports, and there is no legitimate public dataset of real Indian government IDs.** There never will be — it is PII plus a forgery manual, and for Aadhaar specifically it is criminal under Section 29 of the Aadhaar Act 2016.

Two consequences:
1. The **MIDV family from Smart Engines** is the backbone of essentially every usable dataset below.
2. Roughly **40% of what you need, you generate yourselves.** Budget for it as real work.

Frame this as a strength in your pitch:

> *"Real Indian ID datasets cannot legally exist, so we built a synthetic generator from official specimens with checksum-valid identity numbers. For Aadhaar specifically, we need no forgery training data at all — we verify UIDAI's cryptographic signature."*

### 6.2 Tier 1 — Core ID document datasets (Modules 1, 2, 4)

| Dataset | What it gives you | Size | Where |
|---|---|---|---|
| **MIDV-2020** | **The backbone.** 1000 video clips, 1000 scans, 1000 photos of 1000 unique mock documents, each with unique field values and artificially generated faces. Ground truth includes ideal text field values, document quadrangle position, and face position in every frame. Trains doc localisation, field detection, OCR evaluation, and face-crop pipeline | 72,409 images | `ftp://smartengines.com/midv-2020`<br>`l3i-share.univ-lr.fr/MIDV2020/midv2020.html` |
| **MIDV-500** | 50 document types — more type diversity, weaker annotation. Use for doc-type classification robustness | 500 clips | `ftp://smartengines.com/midv-500` |
| **MIDV-2019** | MIDV-500 recaptured under low light and heavy projective distortion. Hardens your quality gate and deskew | — | `ftp://smartengines.com/midv-2019` |
| **DocXPand-25k** | Independent synthetic ID generator + 25k images, with separate field crops (photos, ghost images, barcodes, datamatrices). **License: CC BY-NC-SA 4.0** — non-commercial, fine for SIH, must be flagged | 25k | `github.com/quicksign/docxpand` |

**Download MIDV-2020 first.** Everything else in your pipeline can be built against it.

**Gap:** MIDV-2020 covers ten European document types. **No Indian documents.** That gap is filled by Roboflow + your own generation.

### 6.3 Tier 2 — Forgery and tampering (Module 3)

| Dataset | What it gives you | Where |
|---|---|---|
| **SIDTD** | The most directly on-target set available. Extends MIDV-2020 — originals treated as bona fide, forged versions generated by **Crop & Replace** and **inpainting**, across ten European nationalities (Albanian, Azerbaijani, Estonian, Finnish, Greek, Lithuanian, Russian, Serbian, Slovakian, Spanish). Ships download code, a generator for new forgeries, and baseline models | `github.com/Oriolrt/SIDTD_Dataset`<br>`tc11.cvc.uab.es/datasets/SIDTD_1` |
| **MIDV-Holo** | **Your physical-forgery track.** 700 video clips of artificial ID documents with and without holograms under varied lighting, plus 400 clips of presentation attacks: copy without hologram, hand-drawn pseudo-hologram, photocopy, and **physical photo-replacement**. Ships binary hologram location masks | `github.com/SmartEngines/midv-holo`<br>data: `ftp://smartengines.com/midv-holo`<br>License: CC BY-SA 2.5 |
| **IDNet** | Larger and deliberately harder. The authors show its fraud samples achieve higher SSIM against originals than SIDTD's — meaning stealthier, closer to untampered. **Use as your hard test set, not training** | `arxiv.org/abs/2408.01690` |
| **DocTamper** | Large-scale document *text* tampering with pixel masks. Mostly Chinese, but text splicing artifacts transfer. Best available for text-manipulation detection | `github.com/qcf-568/DocTamper` |
| **FindIt** | Real (not synthetic) forged French administrative documents from the ICPR 2018 fraud detection contest. Small but genuinely human-made | ICPR 2018 Find-it contest page |
| **MIDV-DynAttack** | Extends MIDV-Holo with static and dynamic hologram attacks, tripling attack samples | `github.com/EPITAResearchLab/pouliquen.25.icdar` |

**Critical protocol:** train on SIDTD, **test on IDNet or MIDV-Holo**. Reporting a number on a harder, differently-generated set is the difference between a credible claim and an overfit one.

### 6.4 Tier 3 — Generic image forensics (pretraining)

Document forgery sets are too small to train from scratch. Pretrain on these, then fine-tune.

| Dataset | Purpose | Where |
|---|---|---|
| **CASIA v1 / v2** | Splicing and copy-move, standard baseline | Widely mirrored on GitHub/Kaggle |
| **CoMoFoD** | Copy-move specifically, with post-processing variants | `vcl.fer.hr/comofod` |
| **DEFACTO** | ~150k manipulations from MS-COCO. Largest, best for pretraining | Kaggle / IEEE DataPort |
| **IMD2020** | Real-world manipulated images found in the wild | `staff.utia.cas.cz/novozada/db` |
| **Columbia Uncompressed** | Uncompressed splicing — clean signal for validating noise-residual code | Columbia DVMM |

### 6.5 Tier 4 — Face (Module 4)

| Dataset | Purpose | Where |
|---|---|---|
| **LFW** | Standard 1:1 verification protocol. Sanity-check your threshold code | `vis-www.cs.umass.edu/lfw` |
| **AgeDB-30** | Age-variant verification. **The one that matters most** — a 10-year-old passport photo is your hardest genuine case | InsightFace eval packs |
| **CFP-FP** | Frontal-to-profile. Live capture is not always frontal | InsightFace eval packs |
| **FairFace** | Balanced across race, gender, age. For your bias audit | `github.com/joojs/fairface` |
| **RFW** | Racial Faces in the Wild — standard demographic-bias benchmark | `whdeng.cn/RFW` |

**Do not download MS1M or VGGFace2.** You are not training a face model; ArcFace weights are pretrained. Downloading a training corpus you will not use is a common time sink.

**The unavoidable gap:** no public dataset of ID-document-photo ↔ live-selfie pairs exists. It is inherently PII. MIDV-2020 gives document faces but no matching live captures. **You must build this yourself** — see section 8.

### 6.6 Tier 5 — Anti-spoofing / liveness

| Dataset | Notes | Where |
|---|---|---|
| **CelebA-Spoof** | 625k images, 10k subjects, openly downloadable. **The practical choice** | `github.com/ZhangYuanhan-AI/CelebA-Spoof` |
| **LCC-FASD** | Small, fast to iterate on for a demo | Kaggle |
| **DLC-2021** | Document Liveness Challenge — screen recaptures and printed copies of documents. Relevant to "is this a photo of a screen showing a document" | Smart Engines |
| CASIA-FASD, Replay-Attack, OULU-NPU, SiW | Academic standards, but **all require a signed EULA from the host university**. Turnaround exceeds hackathon timelines. **Skip** | — |

### 6.7 Official specimen sources (template base for generation)

Published by the issuing authorities. Legally clean, and the ground truth your generator needs.

| Document | Source |
|---|---|
| **Indian passport** | **PRADO** — EU Council public register of authentic identity and travel documents: `consilium.europa.eu/prado`. Has Indian passport specimens with security features annotated. Also Passport Seva / MEA security-feature lists |
| **Aadhaar letter + PVC card** | UIDAI publishes sample card images in guidelines and press releases. The PVC card carries a hologram, ghost image, and guilloche pattern — all named, checkable security features |
| **PAN card** | Income Tax Department official card format |
| **Voter ID (EPIC)** | Election Commission of India specimen |
| **Driving licence** | Parivahan / MoRTH — the smart card DL format is standardised under the Central Motor Vehicles Rules, so there is a written spec, not just an image |
| **Passport MRZ layout** | ICAO Doc 9303, free PDF, all 13 parts: `icao.int` |

### 6.8 Reference data (not ML, but required)

| What | Where |
|---|---|
| ICAO Doc 9303 (MRZ spec, check digits, field layouts) | `icao.int` — free PDF |
| ISO 3166-1 alpha-3 country codes | `pycountry` Python package |
| **OFAC SDN list** — real sanctions list, free CSV/XML, includes names, DOBs, and passport numbers | `treasury.gov/ofac` downloads |
| **UN Security Council Consolidated List** — free XML | `scsanctions.un.org` |
| UIDAI Secure QR spec + public certificate | `uidai.gov.in/en/ecosystem/authentication-devices-documents/qr-code-reader.html` |

**On the sanctions lists:** instead of inventing a fake watchlist, load a real published one. Your blacklist lookup then has realistic name-matching problems — transliteration variants, aliases, partial DOBs — which is exactly the hard part, and exactly what will impress a panel.

---

## 7. Roboflow Universe — Verified Assessment

### 7.1 Reality check

Universe is community-uploaded. Most entries are small hobby datasets; several are outright broken (class names that are literally Roboflow's CSV export boilerplate). **Use Roboflow for the localisation layer** — "where is the MRZ, where are the fields, where are the stamps." Keep the **forgery judgment** in your own logic. Nothing on Universe will tell you a passport is fake.

### 7.2 Verification results on commonly cited links

| Project | Claimed | **Verified** | Verdict |
|---|---|---|---|
| `centurion-.../aadhaar-card-details-extraction-n4hyw` | 6.3k images | **2,645 images**, classes `["0","1","2","3","4"]` — unnamed integers, annotation label reads "car" (leftover) | Usable only after you manually map what classes 0–4 mean |
| `cutm-iwh4a/aadhaar-card-details` | Separate dataset | **2,645 images, identical classes** | **Same dataset re-uploaded.** 231 downloads vs 28 — this is the more-used copy. Do not count it twice |
| `vexil-infotech/voterid-card-details-extraction` | Voter ID extraction | **31 images**, 7 classes, Public Domain, "trained model" available | Schema is good (Address, Age, Father's_Name, Gender, Husband_Name, IssueDate, Name). **31 images is not trainable.** Use the schema, ignore the model |
| `passport-stamp/passport-stamp` | Entry/departure stamps | **47 images**, 3 classes (`entry_stamp`, `departure_stamp`, `stamp`), yolov11n model, 8 versions | Correct schema, far too small. Starting weights only — augment heavily with synthetic stamps |
| `detect-for-id/passport-id` | "Passport ID detector" | **9,892 images**, classes: `glasses`, `sunglasses`, `cloth-mask`, `earphone`, `headwear` | **Not a passport detector.** It is an ICAO photo-compliance model. Genuinely useful for checking whether a submitted photo meets passport standards — but not for document detection |
| `document-forgery-detection/document-forgery-detection` | Popular (10k views, 312 downloads) | 402 images, single class name is an export artifact string | **Popularity ≠ quality.** Do not build your tampering claim on this |
| `docdetection-qgqkm/pan-document-classification` | `real_pan` / `fake_pan` | 2,979 images, no provenance | Tempting class names, unauditable definition. **Avoid** |
| `swaroopai/passport-data-prediction-jiczw` | Passport fields | Not verified | Check before committing |
| `tampering-detection/tampering-detection-1` | Multi-doc tampering | Could not confirm this slug; `tampering-detection-0muly` exists in the same workspace (900 imgs) | Verify which you mean |

**Verification procedure for any Universe link (30 seconds):**
1. Image count — under ~150 means schema reference only
2. Class names — integers (`0`,`1`,`2`) or export boilerplate mean unusable without manual mapping
3. Thumbnail — does it show a real person's card? If yes, see 7.4

### 7.3 Recommended Roboflow projects

#### Indian documents

| Purpose | Project | Size | Notes |
|---|---|---|---|
| **Aadhaar — best annotation** | `sujeet-kumar-5vze5/aadhaar-details-detection` | 224 | **15 properly named classes**: `aadhaar number`, `address`, `dob`, `photo`, `emblem`, `father`, `gender`, `goi symbol`, `issue date`, `logo`, `name`, `uiai icon`, `uiai symbol`, `vid`, `yob`. Annotates *security elements*, not just text |
| **Aadhaar — largest structured** | `monika-ztd2k/aadhaar-card-1-ebbdz` | 938 | 18 classes: `a_qr`, `a_photo`, `a_emb`, `a_num`, `a_masked`, `a_govt`, `a_uidai`, `a_vid`, plus `card_passport`, `card_voter_id`, `p_front`, `p_num` |
| **Aadhaar security features** | `project-epimx/id-bdbwr` | 93 | `Emblem logo`, `Goi logo`, `Goi symbol`, `Text layer`, `fake`. Tiny but the only one annotating security elements with a fake class |
| **Aadhaar tampering** | `tampering-detection/tampering-detection-0muly` | 900 | `Tampered Hologram`, `Tampered image`, `Tampered logo`, `Tampered text`, `QR missing`. Conceptually exactly Module 3 for Indian docs. **Uneven annotation — audit first** |
| **Aadhaar back** | `mitesh-workspace/back-aadhaar-card` | 584 | Single class `aadhaar-father-name` |
| **Doc-type routing** | `mahrprojects/identity-card-classifier` | 220 | `aadhar` / `driver-license` / `pan` / `passport` / `voter` |
| **PAN fields** | `mitesh-workspace/pan-card-annotation` | 600 | `pan-name`, `pan-dob`, `pan-father-name`, `pan-no` |
| **PAN fields (alt)** | `smartxtract/pan-card-ygz7o` | 245 | `name`, `date_of_birth`, `father's_name`, `pan_number` |
| **PAN front/back** | `panbg/pan-vngzj` | 1,388 | Largest PAN set |
| **Aadhaar + PAN** | `aadharpan-yolo/aadhaar-pan-document-detection` | 150 | MIT licensed |
| **Driving licence** | `jaspreetsingh/indian-driving-licence-reader-rlxel` | 40 | `name`, `dl_number`, `dob`. Schema only |
| **Voter ID** | `fil-9zpqb/voter-01` | 146 | Has trained model |

#### International / generic

| Purpose | Project | Size | Notes |
|---|---|---|---|
| **Passport VIZ fields** | `misha-88lag/passport-exe8g` | 328 | 14 field classes: `date_of_birth`, `expiry_date`, `doc_id`, `nationality`, `issue_date`, `place_of_birth`, `authority`, `gender`, etc. **Highest-value model on this list** — this is your VIZ↔MRZ cross-check localiser |
| **South Asian passport fields** | `at-in/bangladeshi-passport-fields` | 200 | **33 classes** including `ghost_portrait`, `holder_signature`, `issuing_authority`, `emergency_contact_*`. Ghost portrait is a security feature Indian passports also carry |
| **Passport fields + face** | `passportdetection-rgnih/passport-fields-fio-photo` | 181 | Includes a `face` class. **License: BY-NC-SA 4.0** — flag it |
| **Passport field classes** | `arvind-kumar-wjygd/passport-ppwp8` | 25 | 13 classes incl. `Paasport_no`, `DOE`, `DOI`, `Place_of_Issue`. Too small, good schema |
| **MRZ localisation** | `achreffaty/mrz-ye7hu` | 496 | Largest clean MRZ set. Classes `MRZ`, `MRZ_P` |
| **MRZ + page** | `phiphi-20ww6/passport-page-mrz-detection` | 279 | Gives `mrz` AND `passport_page` — both crops in one pass |
| **MRZ (with model)** | `spacex-hken9/mrz-h6s9s` | 248 | Has a trained model |
| **Doc crop / deskew** | `ip2-kbjz5/identity-card-segmentation` | 157 | yolov11n-seg, trained model. Segmentation gives corners for perspective correction |
| **Doc type classify** | `2bs/identity-type` | 483 | `Chip_Id_Card`, `UnChip_Id_Card`, `passport`. Has model |
| **Stamps (largest)** | `shujing-liang/stamp-detection-f3yka` | 2,342 | Trained model. Cleanest of the stamp sets |
| **Stamps (alt)** | `social-code-llc/stamp-seal-detection` | 306 | Trained model |
| **Stamp binary** | `class-cemy0/stamp-wnh42` | 2,292 | `Stamp` / `Non_Stamp` |
| **Anti-spoofing** | `face-anti-spoofing-detection/face-anti-spoofing-detection` | 6,129 | Trained model, `fake`/`real` |
| **Anti-spoofing (classification)** | `project-uqhrw/face-anti-spoofing-icbck` | 8,269 | `real`/`spoof`, has model |
| **Spoof attack types** | `thanh-huy-xagag/anti-spoofing-avfew` | 1,246 | 4 classes: `live`, `photo`, `device`, `mask` — attack-type granularity |
| **Photo compliance** | `detect-for-id/passport-id` | 9,892 | `glasses`, `sunglasses`, `cloth-mask`, `earphone`, `headwear`. Public Domain. Use for ICAO photo-standard checking |

### 7.4 Provenance warning

**Audit every Indian ID dataset before use.** Most Aadhaar and PAN sets on Universe were built by scraping real cards off the web — you will see real names, real numbers, real faces.

If that is what you find, two options:
1. Use the annotation **schema only** and re-annotate your own synthetic data against it
2. Mask every number and face before training

**Do not ship sample images from these sets in your presentation deck.** An MHA panel is exactly the audience that will ask where your training data came from.

### 7.5 Licensing

Most Universe projects are CC BY 4.0 (attribution required). Exceptions noted above: MIT (`aadharpan-yolo`), Public Domain (`vexil-infotech`, `detect-for-id`), BY-NC-SA 4.0 (`passportdetection-rgnih`).

**Include one slide listing provenance and license per dataset.** Costs five minutes, preempts the most awkward question you will get.

---

## 8. Synthetic Data Generation Plan

This is roughly 40% of your data work. Treat it as a first-class deliverable — it produces both your training data *and* your live demo.

| Deliverable | How | Target |
|---|---|---|
| **Indian document templates** | Vectorise official specimens (section 6.7) into layered templates: background guilloche, static text, field slots, photo slot, QR slot | 5 doc types |
| **Synthetic identities** | Faker with `en_IN` locale for names/addresses. Generate **Aadhaar numbers passing the Verhoeff checksum**, PAN numbers matching official format rules, passport numbers matching the Indian pattern, MRZ lines with correct check digits | 2,000 identities |
| **Synthetic faces** | **Reuse MIDV-2020's** — already artificially generated, zero PII exposure. Or generate fresh with a GAN | 2,000 |
| **Real Aadhaar QRs (validation only)** | Team members generate their *own* offline eKYC / Secure QR from `myaadhaar.uidai.gov.in`, validate the parser, then delete. **Never commit** | 5–10, consent only |
| **Capture realism** | **Print the generated templates, then scan and photograph** under varied lighting and angle. A model trained purely on clean digital renders falls apart on real scans | 3 captures each |
| **Doc-photo ↔ live-face pairs** | Print a photo onto a mock ID template, scan it, capture live webcam frames. Include deliberate impostor pairs. **This is what calibrates your face threshold** — without it, the threshold is a guess | 30–50 people, ~500 pairs |
| **Forgeries with ground truth** | Photo swap, DOB splice, MRZ↔VIZ desync, QR removal/replacement, hologram absence, copy-move. **Log a ground-truth mask on every one** | 2,000–3,000 |
| **Passport stamps** | No public dataset exists. Render synthetic stamps (circle/rectangle variants, dates, port codes) onto MIDV passport pages, then forge by duplicating and date-editing | 1,000 |
| **Cross-document pairs** | Matched passport+visa sets, plus deliberately inconsistent ones (name mismatch, visa outliving passport). Trivial to script; directly demos Validation Layer D | 300 |
| **Watchlist seed** | OFAC/UN lists + synthetic entries matching your test documents so hits actually fire in the demo | — |

**The print-and-rescan step is the one teams skip and should not.** Two afternoons with a printer and a phone camera is the difference between a model that works on your laptop and one that works at the demo table.

---

## 9. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| **OCR** | PaddleOCR or docTR | Better on ID-card layouts than Tesseract; both have ONNX exports |
| **MRZ parsing** | Custom, ~200 lines | ICAO 9303 check-digit logic. Do not use an unmaintained wrapper |
| **Aadhaar QR** | Open-source Secure QR parser + UIDAI public certificate | Cryptographic verification, fully offline |
| **Face** | InsightFace `buffalo_l` (RetinaFace + ArcFace) | 512-d embeddings, single-pass detect+align+embed |
| **Face gallery (1:N)** | Postgres `pgvector`, HNSW index | Demo-scale sufficient; mention FAISS/Milvus for production |
| **Tampering** | OpenCV (ELA, copy-move, noise residual) + PyTorch segmentation | Ensemble, not one model |
| **Metadata** | `exiftool`, `pikepdf`, Pillow | EXIF, PDF incremental-update history |
| **Model runtime** | **ONNX Runtime, int8 quantised** | CPU-only, warm sessions, tuned thread count |
| **Backend** | FastAPI + WebSocket | Async fan-out, streaming results |
| **Store** | Postgres + MinIO | Postgres for cases/audit, MinIO for images |
| **Frontend** | React + Vite | Officer console |
| **Packaging** | Docker Compose, **fully offline** | Border posts have no reliable internet |
| **Training/annotation** | Roboflow (build-time only) | Export weights, run locally |

---

## 10. Repository Structure

```
screening/
├── api/
│   ├── main.py              # FastAPI app
│   ├── websocket.py         # streaming results
│   └── router.py            # document profile routing
├── core/
│   ├── decode.py            # decode ONCE, shared numpy array
│   ├── quality.py           # blur, brightness, size gates
│   └── preprocess.py        # deskew, perspective correct
├── modules/
│   ├── extraction/
│   │   ├── detect.py        # doc type, crop, field boxes
│   │   ├── ocr.py           # PaddleOCR on crops only
│   │   ├── mrz.py           # parse + check digits (ICAO 9303)
│   │   ├── aadhaar_qr.py    # UIDAI signature verification
│   │   └── normalize.py     # dates, names, ISO codes
│   ├── validation/
│   │   ├── layer_a_integrity.py     # checksums, signatures
│   │   ├── layer_b_format.py        # schema conformance
│   │   ├── layer_c_crossfield.py    # within-document logic
│   │   ├── layer_d_crossdoc.py      # passport ↔ visa
│   │   ├── layer_e_lookup.py        # watchlist, SLTD
│   │   └── layer_f_temporal.py      # crossing history
│   ├── tamper/
│   │   ├── physical/        # font, layout, guilloche, hologram
│   │   ├── digital/         # ELA, DCT, copy-move, metadata
│   │   ├── stamps.py        # duplicate + date logic
│   │   └── segment.py       # learned heatmap
│   └── face/
│       ├── verify.py        # 1:1
│       ├── gallery.py       # 1:N pgvector
│       ├── liveness.py      # passive anti-spoof
│       └── calibrate.py     # FAR/FRR curve
├── fusion/
│   ├── signal.py            # the Signal dataclass — FROZEN
│   ├── score.py             # weighted + hard-fail
│   └── evidence.py          # human-readable reasons
├── profiles/
│   ├── passport.yaml
│   ├── visa.yaml
│   ├── aadhaar.yaml
│   ├── voter_id.yaml
│   └── driving_licence.yaml
├── models/                  # ONNX weights, baked into image
├── data/
│   ├── generator/           # synthetic doc + forgery generator
│   ├── templates/           # vectorised specimen templates
│   └── ground_truth/        # masks, labels
├── ui/                      # React officer console
├── docker-compose.yml
└── tests/
```

---

## 11. Development Roadmap

### Phase 0 — Week 0 (this week)

- **Freeze the `Signal` contract and profile schema.** Everything else depends on it.
- Stand up FastAPI with a stub endpoint returning fake signals
- Build the React console against those stubs
- Download MIDV-2020

*Everyone now has a target to code against, and the UI is never blocked.*

### Phase 1 — Weeks 1–2: Extraction & validation spine

- Fork `ip2-kbjz5/identity-card-segmentation` and `achreffaty/mrz-ye7hu`, export ONNX
- Wire: crop → MRZ detect → PaddleOCR (charset-restricted) → parser → check digits
- Implement validation Layers A–C
- Implement the Aadhaar Secure QR verifier

**Deliverable:** upload a passport or Aadhaar, get a validated field set with per-field checksum/signature status. *This alone is a demoable system.*

### Phase 2 — Weeks 3–4: Cross-checks & face

- Train the VIZ field detector from `misha-88lag/passport-exe8g`
- Add the VIZ↔MRZ mismatch signal
- Implement Layer D across passport + visa
- InsightFace 1:1 verify, threshold calibrated on doc-vs-live pairs
- pgvector gallery for 1:N duplicate identity

**Deliverable:** cross-document contradictions surfaced, face verdict, duplicate-identity flag.

### Phase 3 — Weeks 5–6: Tampering

- Classical signals first: ELA, copy-move, noise residual, stamp duplicates, metadata
- Build the synthetic forgery generator
- Annotate in Roboflow, train a segmentation model for the heatmap
- Physical-track signals: OCR-B conformance, layout geometry, guilloche

**Deliverable:** tamper heatmap with region-level evidence.

### Phase 4 — Weeks 7–8: Hardening & story

- Anti-spoofing model integrated
- FAR/FRR curve exposed in the UI
- Bias evaluation across FairFace/RFW, results documented
- Audit log complete
- **Offline Docker Compose install verified with the network cable pulled**
- Rehearse the live-tampering demo **and one honest failure case**

### Team split (six people)

| Role | Scope |
|---|---|
| 2 × Extraction + Validation | Largest surface area |
| 1 × Face + Gallery | 1:1, 1:N, liveness, calibration |
| 2 × Tampering + Data generation | Both tracks + synthetic generator |
| 1 × API + Fusion + Console | **Integration owner — your strongest generalist** |

### Cut list (if behind schedule)

**Cut in this order:**
1. Active liveness (keep passive only)
2. Learned tamper segmentation (classical signals alone are defensible)
3. Layer F temporal analysis
4. Driving licence and permit support (passport + visa + Aadhaar proves the architecture generalises)

**Do not cut:**
- MRZ check digits
- VIZ↔MRZ cross-check
- Aadhaar QR signature verification
- Layer D cross-document validation
- The evidence list in the UI

*These five are what make the system credible to an SSB officer, and four of them are nearly free.*

---

## 12. Legal & Compliance

### Aadhaar

- **Aadhaar Act 2016, Section 29** restricts sharing of Aadhaar information. UIDAI explicitly prohibits service providers from sharing, publishing, or displaying the offline eKYC XML or its contents. Non-compliance invites action under Sections 29(2), 29(3), 29(4) and 37 of the Act.
- **Support masked Aadhaar** (last four digits only)
- **Store a salted hash, never the number**
- Verify and discard — do not retain

### DPDP Act 2023

- Data minimisation: collect only what the screening decision requires
- Purpose limitation: screening data is not repurposed
- Storage limitation: define and enforce retention periods
- Encrypt at rest and in transit

### Face data

- Store **embeddings + audit logs, not raw face images**
- Do not retain live captures beyond the session unless legally mandated
- Encrypt the embedding store
- **Bias testing is a compliance item, not a nice-to-have.** NIST FRVT documents accuracy disparities across demographics; in a border-security context those disparities have real consequences

### Training data provenance

- Every source used must be synthetic, official specimen, or officially published
- **Do not use scraped Indian ID datasets.** Several circulate on Kaggle and GitHub with names like "Aadhaar card images" or "Indian ID OCR dataset". Many contain real people's documents uploaded without consent
- Maintain a provenance + license table and put it on a slide

### System positioning

- **Human-in-the-loop.** The system assists, never replaces, the officer's decision
- Full audit trail: score, model version, timestamp, officer ID, per-signal evidence
- Reproducibility: a decision must be reconstructable months later for an investigation

---

## 13. Resource Links Appendix

### Core datasets

| Resource | Link |
|---|---|
| MIDV-2020 (FTP) | `ftp://smartengines.com/midv-2020` |
| MIDV-2020 (mirror + docs) | https://l3i-share.univ-lr.fr/MIDV2020/midv2020.html |
| MIDV-2020 paper | https://arxiv.org/abs/2107.00396 |
| MIDV-500 | `ftp://smartengines.com/midv-500` |
| MIDV-2019 | `ftp://smartengines.com/midv-2019` |
| MIDV-Holo | https://github.com/SmartEngines/midv-holo |
| MIDV-Holo data | `ftp://smartengines.com/midv-holo` |
| SIDTD | https://github.com/Oriolrt/SIDTD_Dataset |
| SIDTD (CVC repository) | https://tc11.cvc.uab.es/datasets/SIDTD_1/ |
| SIDTD paper | https://www.nature.com/articles/s41597-024-04160-9 |
| IDNet paper | https://arxiv.org/abs/2408.01690 |
| DocXPand-25k | https://github.com/quicksign/docxpand |
| DocTamper | https://github.com/qcf-568/DocTamper |
| MIDV-DynAttack | https://github.com/EPITAResearchLab/pouliquen.25.icdar |
| CelebA-Spoof | https://github.com/ZhangYuanhan-AI/CelebA-Spoof |
| FairFace | https://github.com/joojs/fairface |
| CoMoFoD | https://www.vcl.fer.hr/comofod/ |

### Official / government

| Resource | Link |
|---|---|
| UIDAI QR Code Reader + public certificate | https://uidai.gov.in/en/ecosystem/authentication-devices-documents/qr-code-reader.html |
| UIDAI documentation | https://docs.uidai.gov.in/ |
| UIDAI offline eKYC (resident portal) | https://myaadhaar.uidai.gov.in/offline-ekyc |
| PRADO — authentic document register | https://www.consilium.europa.eu/prado/ |
| ICAO Doc 9303 | https://www.icao.int/publications/pages/publication.aspx?docnum=9303 |
| OFAC SDN sanctions list | https://ofac.treasury.gov/sanctions-list-service |
| UN Security Council Consolidated List | https://scsanctions.un.org/ |

### Implementation references

| Resource | Link |
|---|---|
| Roboflow Inference SDK | https://inference.roboflow.com/inference_helpers/inference_sdk/ |
| Aadhaar Offline KYC (Android reference) | https://github.com/GovindaPaliwal/Aadhaar-Offline-KYC-Android-Library |
| InsightFace | https://github.com/deepinsight/insightface |
| PaddleOCR | https://github.com/PaddlePaddle/PaddleOCR |
| docTR | https://github.com/mindee/doctr |
| pgvector | https://github.com/pgvector/pgvector |
| ONNX Runtime | https://onnxruntime.ai/ |

### Roboflow Universe — recommended projects

**Indian documents**
- https://universe.roboflow.com/sujeet-kumar-5vze5/aadhaar-details-detection
- https://universe.roboflow.com/monika-ztd2k/aadhaar-card-1-ebbdz
- https://universe.roboflow.com/project-epimx/id-bdbwr
- https://universe.roboflow.com/tampering-detection/tampering-detection-0muly
- https://universe.roboflow.com/mitesh-workspace/back-aadhaar-card
- https://universe.roboflow.com/mahrprojects/identity-card-classifier
- https://universe.roboflow.com/mitesh-workspace/pan-card-annotation
- https://universe.roboflow.com/smartxtract/pan-card-ygz7o
- https://universe.roboflow.com/panbg/pan-vngzj
- https://universe.roboflow.com/aadharpan-yolo/aadhaar-pan-document-detection
- https://universe.roboflow.com/jaspreetsingh/indian-driving-licence-reader-rlxel
- https://universe.roboflow.com/fil-9zpqb/voter-01

**International / generic**
- https://universe.roboflow.com/misha-88lag/passport-exe8g
- https://universe.roboflow.com/at-in/bangladeshi-passport-fields
- https://universe.roboflow.com/achreffaty/mrz-ye7hu
- https://universe.roboflow.com/phiphi-20ww6/passport-page-mrz-detection
- https://universe.roboflow.com/spacex-hken9/mrz-h6s9s
- https://universe.roboflow.com/ip2-kbjz5/identity-card-segmentation
- https://universe.roboflow.com/2bs/identity-type
- https://universe.roboflow.com/shujing-liang/stamp-detection-f3yka
- https://universe.roboflow.com/social-code-llc/stamp-seal-detection
- https://universe.roboflow.com/passport-stamp/passport-stamp
- https://universe.roboflow.com/face-anti-spoofing-detection/face-anti-spoofing-detection
- https://universe.roboflow.com/project-uqhrw/face-anti-spoofing-icbck
- https://universe.roboflow.com/thanh-huy-xagag/anti-spoofing-avfew
- https://universe.roboflow.com/detect-for-id/passport-id

**Verified as problematic — avoid or handle with care**
- `document-forgery-detection/document-forgery-detection` — 402 imgs, export-artifact class name
- `docdetection-qgqkm/pan-document-classification` — unauditable `real_pan`/`fake_pan`
- `centurion-.../aadhaar-card-details-extraction-n4hyw` and `cutm-iwh4a/aadhaar-card-details` — same dataset, unnamed integer classes
- `vexil-infotech/voterid-card-details-extraction` — 31 images, schema only

---

*Document compiled for SIH PS 26188. Verify all Roboflow image counts and class names before committing — Universe projects change without notice.*
