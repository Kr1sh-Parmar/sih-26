# Technical Specification

Companion to `CONTRACTS.md` (the frozen interfaces) and `MODULES.md` (per-module acceptance criteria).

---

## 1. Architecture in one paragraph

A browser client captures a document image and live camera frames. A single FastAPI process decodes the image **once** into a numpy array and passes it by reference to every module. All modules run in that same process with ONNX sessions warm in memory — no microservices, because serialising a 3 MB scan four times costs more wall-clock than the inference does. Results stream back over a WebSocket as each module completes. A risk gate decides after the cheap deterministic tier whether to run expensive forensics. Fusion groups correlated signals into findings, scores by trust class, and produces evidence cards.

## 2. Layers

| Layer | Components | Budget |
|---|---|---|
| **L0 Capture** | Document scanner/camera · live webcam · reference issuer portal (offline, out-of-band) | — |
| **L1 Orchestration** | FastAPI · profile router · `ScreeningContext` build · decode once · WebSocket | 20 ms |
| **L2 Preprocess** | Quality gate · YOLOv11n-seg + quad warp · YOLOv11n-cls type classifier | 120 ms |
| **L3 Extraction** | YOLOv11s field detector · PaddleOCR on crops · MRZ parser · QR decoder · Florence-2 fallback → checksum ratifier | 250 ms |
| **L4 Validation** | Ed25519 signature verifier · Layers A–B arithmetic · Layers C–D cross-checks · Layers E–F lookups | 15 ms |
| **L5 Tampering** | Physical track · stamp analysis · digital track · *(escalated)* deep forensics | 160 / +600 ms |
| **L6 Face** | Doc embed · passive liveness · live embed · 1:1 match · *(escalated)* active liveness, 1:N | 320 / +900 ms |
| **L7 Fusion** | Risk gate · finding grouper · trust-class scoring · coverage check · console | 10 ms |
| **L8 Data** | Postgres · pgvector · trust anchor store · MinIO · ONNX registry · watchlist | — |

## 3. Three properties that matter more than the boxes

**Decode once.** L1 builds `ctx.image`. No module reopens the file. This is why the inference core is one process.

**Rules first, short-circuit allowed.** MRZ checksum failure, invalid signature, expired document, or watchlist hit returns RED before a single model runs. Under 200 ms, no CV.

**Stream as results land.** Officer sees validation at ~300 ms, face at ~700 ms, tampering at ~1.2 s. Perceived latency is what you are actually optimising and this is nearly free.

## 4. Model inventory

All ONNX Runtime, int8 quantised where possible, sessions created once at process start.

| Purpose | Model | Size | Input | ~CPU |
|---|---|---|---|---|
| Document segmentation | YOLOv11n-seg | 6 MB | 640² | 45 ms |
| Type classification | YOLOv11n-cls, 6 classes | 5 MB | 224² | 15 ms |
| Field detection | YOLOv11s-det, 22 classes | 22 MB | 640² | 110 ms |
| Text det + rec | PaddleOCR PP-OCRv4 (en, hi) | 15 MB | variable | 280 ms / 10 crops |
| MRZ recognition | PP-OCRv4 rec, OCR-B charset locked | shared | 48×320 | 40 ms |
| QR decode | OpenCV WeChatQRCode | 1 MB | full | 25 ms |
| VLM fallback | **Florence-2-base**, `<OCR_WITH_REGION>` | 460 MB | 768² | 1.5 s |
| Face det+align+embed | InsightFace `buffalo_l`, `det_size=(320,320)` | 330 MB | 320² → 112² | 160 ms/face |
| Passive liveness | MiniFASNet (Silent-Face) | 2 MB | 80×80 | 20 ms |
| Active liveness | MediaPipe FaceMesh, EAR blink | 3 MB | frames | 30 ms/frame |
| Stamp detection | YOLOv11n | 6 MB | 640² | 40 ms |
| Classical forensics | OpenCV — ELA, ORB copy-move, SRM noise | — | — | 150 ms |

**Warm footprint ≈ 450 MB** without Florence-2, ≈ 910 MB with it lazily loaded on first fallback.

### Why Florence-2-base and not a chat VLM

Two reasons, and the second matters more.

1. **CPU latency.** Qwen2.5-VL-3B INT8 is 15–25 s on CPU. Unusable. Florence-2-base is 0.23B params and runs in 1–2 s.
2. **Hallucination surface.** A chat VLM asked to return JSON fields will confidently invent a passport number for an unreadable smudge — that is what it was trained to do. Florence-2's `<OCR_WITH_REGION>` returns text *with bounding boxes grounded in the image*. It can misread a character; it structurally cannot fabricate a field out of nothing.

**Regardless, the checksum ratifier is mandatory.** No VLM output reaches L4 unratified:

```python
if source == "vlm_fallback":
    for field, value in output.items():
        if has_checksum(doc_type, field):
            trust = "arithmetic" if verify_checksum(doc_type, field, value) else "rejected"
        else:
            trust = "unverified"
    if all(f.trust == "unverified" for f in fields):
        force MANUAL_REVIEW regardless of score
```

Hard 8-second timeout on the fallback, falling through to "request re-capture". An unbounded fallback will hang the demo.

## 5. Field ontology — one detector, six document types

22 classes. Each profile declares which are expected and which are forbidden.

```
person_photo   ghost_photo    signature      qr_code      barcode      mrz
name           father_name    dob            gender       address      nationality
id_number      secondary_id   issue_date     expiry_date
issuing_authority             emblem         logo         hologram
blood_group    doc_title
```

**Do not train six per-type detectors.** One model, one warm session, and shared classes (name, dob, photo appear on all six) generalise better than six small models each seeing 200 images.

A forbidden class firing is itself a signal: an MRZ detected on a Voter ID is suspicious.

## 6. Validation layers

Layers A–D are deterministic, need no network, and run in under 15 ms combined. They are the backbone and the fast path.

**A — Intra-document integrity**
Ed25519 signature over the canonical payload (reference issuer). MRZ five check digits: document number, DOB, expiry, optional data, composite. Verhoeff on the 12-digit Aadhaar. PAN check character. EPIC format. DL state + RTO code.

**B — Format conformance**
Field lengths and charset per ICAO 9303. Nationality against ISO 3166-1 alpha-3 (mind MRZ quirks: `D` for Germany, GBR subtypes). Gender codes `M`/`F`/`<`. Date formats.

**C — Cross-field logic within one document**
DOB < issue < expiry. Expiry − issue equals a standard validity period (India: 10 y adult, 5 y minor). Age at issue consistent. Expiry not past. VIZ ↔ MRZ agreement on every shared field — **this is the highest-value tamper signal in the system.**

**D — Cross-document trust propagation**
When two documents are presented in one session and one is signed, the signed payload becomes ground truth for the other:

```
signed document verifies
  → its name / DOB / gender are PROVEN
  → compare against the unsigned document's printed fields
  → mismatch is a hard fail with cryptographic backing
```

This is the headline demo: officer scans Aadhaar and PAN together, the signed Aadhaar payload says DOB 1996, the PAN prints 1998, hard fail. No ML, cryptographic certainty, exact real-world fraud pattern.

**E — External lookups (local tables)**
Watchlist by document number and by name+DOB, seeded from OFAC SDN and UN Consolidated lists plus synthetic entries matching demo documents. Real sanctions lists give you realistic name-matching problems — transliteration variants, aliases, partial DOBs — which is the actually hard part.

**F — Temporal and behavioural**
Same document number at two checkpoints too far apart in too little time. Exit without matching entry. Duplicate crossings. Free, because the audit log already exists.

## 7. Tampering — two tracks

The critical distinction: **metadata and compression forensics only fire on uploaded files.** At a live counter the scanner writes the file, so EXIF is clean and the image is single-JPEG by construction. A professionally printed physical forgery passes ELA, EXIF, and double-JPEG completely clean — because the image genuinely is a fresh scan. It is the *object* that is fake.

### Track A — Physical artifact forensics (primary)

| Signal | Method |
|---|---|
| OCR-B conformance | Stroke width, glyph geometry in the MRZ strip vs ICAO spec |
| Layout geometry | Field positions relative to document corners vs template |
| Guilloche continuity | Security background must be continuous under text and around the photo |
| Ghost portrait | Present, correctly positioned, consistent with the main photo |
| Print halftone | Genuine printing has a specific screen pattern; inkjet does not |
| Photo boundary | Physical cut-and-paste edge artifacts |
| Stamp duplicate | Two stamps matching at pixel level are copy-pasted — **strongest, cheapest stamp signal** |
| Stamp date logic | Date within visa validity, entry before exit, stay within permitted duration |

**Coverage:** full for passport and Aadhaar (template references built). Partial for the other four — font consistency, layout geometry, copy-move only. This is a deliberate, statable trade-off: physical security-feature detection is template-dependent and six templates does not fit in eight weeks.

### Track B — Digital file forensics (uploads only)

| Signal | Weight |
|---|---|
| Copy-move (ORB/SIFT keypoint matching within one image) | High |
| EXIF software signature (`Adobe Photoshop` on a "scan") | High when present |
| Double-JPEG / DCT coefficient analysis | Medium |
| Noise residual inconsistency (SRM high-pass, regional statistics) | Medium |
| Error Level Analysis | **Low** |

**Two naming corrections that will be caught if you get them wrong:**

- It is **noise residual inconsistency**, not PRNU. PRNU requires ~50 images from a *known* camera to estimate a reference pattern. You have one image from an unknown device.
- **ELA is a visualisation, not a verdict.** Global recompression flattens it, mixed source quality produces false bright patches, PNG/PDF give nothing. Weighted 0.30 in `reliability.yaml`.

**No reference stamp template library.** Thousands of variants across countries and ports, no public reference set exists. Replaced by duplicate detection, date logic, and count-vs-declaration.

**Explainability via segmentation mask, not Grad-CAM.** Grad-CAM localisation on a classifier is weak and hard to defend under questioning. (Note: the learned segmentation model is on the cut list — classical copy-move already gives you region highlights.)

### The training trap

Train a CNN on your own synthetic splices and it learns *your splice generator's artifacts*, not forgery. You will score 99% on your held-out set and near-chance on anything real.

**Protocol:** train on one tampering-method family, test on a *different* one. Report both. A lower number on a harder, differently-generated set is more credible than a high number on your own distribution.

## 8. Face verification

### 1:1 doc-to-live

```
doc image → field_boxes[person_photo] → InsightFace → 512-d
live frames → quality gate → passive liveness → InsightFace → 512-d
             → cosine → calibrated verdict
```

**Do not use `((cos + 1) / 2) * 100`.** It maps a total stranger (cos ≈ 0.0) to **50** and a confident impostor (cos ≈ 0.16) to **58**. An officer reads 58 as "more than half, probably him." The scale is wrong in the direction that admits fraudsters.

Report either a logistic-calibrated probability fitted on your genuine/impostor distributions, or three bands plus margin: `cos 0.52, threshold 0.40, +0.12 above`.

**Calibrate on doc-vs-live pairs, not LFW.** Passport photos are printed, halftone-screened, overprinted with guilloche, sub-300 DPI once scanned, and up to ten years old. Published `buffalo_l` thresholds are live-to-live and will be wrong in the direction that rejects genuine travellers.

**Single detection pass.** Use `FaceAnalysis.get()` once and read `.embedding`. Calling RetinaFace separately then `app.get()` runs the detector twice per face, four times per comparison.

**Detection fallback chain** (never fail silently): primary detector → denoised retry (Aadhaar has a faint background pattern, passports have laminate reflection) → known photo region from `field_boxes` → explicit `face not found` status.

**Quality gates before comparing** — reject and prompt rather than compare badly. Document photos need a *more lenient* blur threshold than live captures (printed photos are naturally softer), and the correct UX response differs: for a bad document photo, ask to re-capture the *document at higher resolution*, not "retake your photo" — the printed photo cannot be retaken.

### Liveness

Passive first (MiniFASNet, one frame, ~20 ms), escalate to active (FaceMesh blink EAR) only on an uncertain score. Most genuine users never touch the slow path.

Test it against an actual printed photo and an actual phone screen before demo day. Untested liveness is theatre.

### 1:N duplicate identity

The problem statement's "multiple identities used by the same person." Embed the live face, query pgvector HNSW over prior screening events, flag near-duplicates carrying *different* document numbers. Stricter threshold than 1:1 because you are running many comparisons.

Escalated tier only.

### Bias

Face recognition has documented demographic accuracy disparities (NIST FRVT). Evaluate on FairFace and RFW, report the gap. In a border-security context this is a compliance item, not a nice-to-have.

## 9. Storage and retention

- Face **embeddings** persist; raw face crops do not survive the session TTL.
- ID numbers: salted hash + last four digits. Never the raw number.
- MinIO holds document images with a session TTL for audit; deletion is scheduled and documented.
- `screening_events.signals` stores the full JSONB signal list so historical cases can be re-scored after a weight change.

## 10. Latency budget (8-core CPU, no GPU)

| Stage | ms |
|---|---|
| Decode + quality gate | 60 |
| Segmentation + quad warp | 45 |
| Type classification | 15 |
| Field detection | 110 |
| PaddleOCR, ~10 crops | 280 |
| MRZ / QR parse + all validation layers | 25 |
| Face detect + embed ×2 + passive liveness | 320 |
| Physical + stamp + cheap forensics | 160 |
| Fusion | 5 |
| **Tier 1 total** | **~1,020** |
| Escalated (deep forensics + 1:N) | +1,200 |
| Florence-2 fallback | +1,500 |

### The five things that actually move the number

1. **Never OCR the whole page.** Detect field regions, OCR only those crops. 5–10×. This is why the field detector matters more than the OCR engine choice.
2. **Gate on deterministic checks.** Hard fails return RED without touching the CV stack.
3. **Stream over WebSocket.** Nearly free, transforms perceived latency.
4. **ONNX Runtime int8**, `intra_op_num_threads` tuned to the box, sessions created at startup — never per request.
5. **Stay CPU-only and say so.** "Runs on a commodity 8-core box, no GPU, no internet" is what a border post actually has.

## 11. Deployment

```yaml
services:
  api:      # FastAPI + all ONNX sessions warm. Models baked into image.
  db:       # postgres:16 + pgvector
  minio:    # object store, TTL lifecycle rules
  ui:       # nginx serving the React build
```

Single `docker compose up`. No model downloads at runtime. **Verify the offline claim by physically pulling the network cable before the demo** — a runtime model fetch you forgot about will surface at exactly the wrong moment.

## 12. Repository layout

```
screening/
├── CLAUDE.md
├── docs/
├── api/
│   ├── main.py            routes
│   ├── websocket.py       streaming results
│   └── router.py          profile selection
├── core/
│   ├── decode.py          decode ONCE
│   ├── quality.py         blur, brightness, size gates
│   ├── preprocess.py      deskew, perspective correct
│   └── registry.py        ONNX session registry, warm at startup
├── modules/
│   ├── extraction/        detect · ocr · mrz · qr · vlm · ratify · normalize
│   ├── validation/        layer_a..layer_f, each a pure function
│   ├── tamper/            physical/ · digital/ · stamps.py
│   └── face/              verify · gallery · liveness · calibrate
├── fusion/
│   ├── signal.py          FROZEN — see CONTRACTS.md
│   ├── context.py         FROZEN
│   ├── findings.py        anchor binding, noisy-OR
│   ├── score.py           trust-class precedence, coverage
│   └── evidence.py        card assembly and ordering
├── issuer/                reference issuer — OFFLINE, not importable by api/
├── profiles/              passport · visa · aadhaar · pan · voter_id · dl
├── config/                reliability.yaml · thresholds.yaml · bands.yaml
├── models/                ONNX weights, baked into image
├── data/                  generator/ · templates/ · ground_truth/
├── ui/                    React officer console
└── tests/
```

`issuer/` must not be importable from `api/`. Enforce it with a lint rule. The reference issuer is out-of-band tooling, not part of the screening path.
