# Implementation Roadmap

Eight weeks, six people, six document types, CPU only, live face capture.

Every phase has an **exit gate**. Do not start the next phase until the gate passes — the gates exist because this plan has three items that are easy to defer and fatal to defer.

---

## Team split

| Role | Person | Scope |
|---|---|---|
| **Integration owner** | 1 | `Signal`, `ScreeningContext`, profile loader, fusion, console. Owns the contracts. Strongest generalist. |
| **Extraction** | 2 | Field ontology, detector training, OCR, MRZ, QR, Florence-2 fallback, normalisation |
| **Validation + issuer** | 1 | Layers A–F, Ed25519 reference issuer, trust anchor store, watchlist |
| **Tampering + data** | 1 | Both tracks, synthetic generator, templates, forgery mutations |
| **Face** | 1 | 1:1, liveness, 1:N gallery, **calibration set** |

Extraction gets two people because it is the largest surface (six document types × field detection × OCR × three parse paths).

---

## The three items that will kill you if deferred

Track these weekly regardless of which phase you are in.

| Item | Owner | Why it is dangerous |
|---|---|---|
| **Doc-vs-live calibration set** (~500 pairs, 30–50 people) | Face | Long lead time — you need to *schedule people*. Without it the face threshold is a guess, and with a live camera a guessed threshold either rejects your own teammate or accepts an impostor, in front of judges. |
| **Six document templates** | Tampering | ~1.5 days each = 9 days of vector work. Cannot be compressed. Start in week 1, not week 5. |
| **Frozen contracts** | Integration | Four people build against them. Changing one in week 5 costs a week. |

---

## Phase 0 — Week 0: Contracts and scaffold

Nobody writes module code this week. The point is to make weeks 1–8 parallel.

- [ ] Freeze `Signal`, `ScreeningContext`, `Finding` — commit `CONTRACTS.md`
- [ ] Freeze the profile YAML schema; write all six profiles as stubs
- [ ] FastAPI app returning **fake signals** from a fixture file
- [ ] WebSocket streaming with the fake signals
- [ ] React console built against the fake stream
- [ ] `docker compose up` works end to end with mocks
- [ ] Download MIDV-2020; open a Roboflow workspace
- [ ] **Schedule the calibration capture session** (put it in a calendar)

**Exit gate:** `docker compose up` → open the console → paste a fixture → see evidence cards. All fake. Everyone now has a target.

---

## Phase 1 — Weeks 1–2: Deterministic spine

The whole system minus the models. Everything here is arithmetic and needs no training data.

**Extraction (2)**
- [ ] Field ontology finalised — 22 classes, mapped per document type
- [ ] Fork `identity-card-segmentation` + `achreffaty/mrz-ye7hu`; export ONNX
- [ ] Segmentation → quad warp → type classifier wired
- [ ] MRZ detect → OCR-B-restricted PaddleOCR → parser
- [ ] **MRZ five check digits, ICAO 9303** — full implementation with unit tests

**Validation + issuer (1)**
- [ ] Ed25519 reference issuer: canonicalise → SHA-256 → sign → QR encode
- [ ] `TrustAnchorStore` keyed by issuer ID
- [ ] Signature verifier
- [ ] Layer A: Verhoeff, PAN structure, EPIC format, DL state/RTO
- [ ] Layer B: ISO 3166 codes, field lengths, charsets, date formats
- [ ] Layer C: date ordering, validity period, age consistency

**Tampering + data (1)**
- [ ] Vectorise passport + Aadhaar templates from PRADO / official specimens
- [ ] Synthetic identity generator: Faker `en_IN`, **Verhoeff-valid Aadhaar**, format-valid PAN, TD3 MRZ with correct check digits

**Face (1)**
- [ ] InsightFace `buffalo_l` wired, single detection pass, `det_size=(320,320)`
- [ ] Quality gates: blur (separate thresholds doc vs live), size, pose
- [ ] Detection fallback chain with explicit `face not found`
- [ ] **Run the calibration capture session**

**Integration (1)**
- [ ] Profile loader, `reliability.yaml`, `bands.yaml`
- [ ] Fusion: hard-fail path, coverage check, weighted sum
- [ ] Real signals replace fixtures

**Exit gate:** upload a synthetic signed passport → real field set, real check-digit verdicts, real signature verdict, real evidence cards. **This alone is a demoable system.**

---

## Phase 2 — Weeks 3–4: Six documents, VIZ↔MRZ, trust propagation

**Extraction (2)**
- [ ] Annotate all six types against the 22-class ontology in Roboflow (~200 img each; 4-way parallel, 12–15 hrs total)
- [ ] Train **one** YOLOv11s multi-class field detector; export int8 ONNX
- [ ] PaddleOCR on crops only, en + hi
- [ ] Field normalisation: ISO dates, transliterated uppercase names
- [ ] QR decode + payload unpack

**Validation (1)**
- [ ] **VIZ ↔ MRZ cross-check** — the single highest-value tamper signal
- [ ] **Layer D trust propagation** — signed document validates unsigned siblings
- [ ] Watchlist: load OFAC SDN + UN Consolidated; name matching with alias and transliteration variants
- [ ] Layer F: crossing history, impossible transit

**Tampering (1)**
- [ ] Remaining four templates
- [ ] Forgery mutation generator with ground-truth masks: photo swap, DOB splice, VIZ↔MRZ desync, QR replacement, copy-move
- [ ] Print → scan → photograph capture pass (**do not skip; models trained on clean renders fail on real scans**)

**Face (1)**
- [ ] Calibrate threshold on the doc-vs-live pairs; produce the FAR/FRR curve
- [ ] Passive liveness (MiniFASNet) integrated
- [ ] pgvector HNSW gallery + 1:N duplicate search

**Integration (1)**
- [ ] Risk gate with the escalation policy
- [ ] Finding grouper: anchor binding, IoU resolution, noisy-OR
- [ ] Trust-class precedence

**Exit gate:** scan Aadhaar + PAN together → signed Aadhaar validates the PAN's printed DOB → mismatch fires as a hard fail with cryptographic backing. **This is the headline demo. Protect this week.**

---

## Phase 3 — Weeks 5–6: Tampering and the fallback

**Tampering (1) + Extraction help**
- [ ] Classical digital track: copy-move (ORB), SRM noise residual, ELA, double-JPEG, EXIF
- [ ] Physical track for passport + Aadhaar: OCR-B conformance, guilloche continuity, ghost portrait, layout geometry
- [ ] Partial physical track for the other four: font consistency, layout geometry
- [ ] Stamp detection + duplicate + date logic + count-vs-declaration
- [ ] Region highlights from copy-move matches feed the console overlay

**Extraction (1)**
- [ ] Florence-2-base ONNX, `<OCR_WITH_REGION>`, 8-second hard timeout
- [ ] **Checksum ratifier** — mandatory gate on all VLM output
- [ ] Fallback-of-fallback: "request re-capture"

**Face (1)**
- [ ] Active liveness (FaceMesh blink EAR), escalated only
- [ ] **Bias evaluation** on FairFace / RFW; document the disparity
- [ ] Spoof testing: printed photo, phone screen, both must be rejected

**Integration (1)**
- [ ] Evidence card ordering and suppression rules
- [ ] Collapsed passing-signal count; always-visible cryptographic passes
- [ ] Audit log: full signal JSONB, model versions, officer ID

**Exit gate:** tamper a document live on camera → system flags the region with a specific, readable reason.

---

## Phase 4 — Week 7: Console and completeness

- [ ] Side-by-side document view with tamper region overlay
- [ ] Extracted fields with per-field confidence and validation status
- [ ] Face pair side by side with verdict band and margin
- [ ] Evidence cards: hard fails first, then findings by trust class, then coverage gaps, then crypto passes, then collapsed count
- [ ] FAR/FRR operating-point control the operator can move
- [ ] `disclosure` string rendered for reference-issuer verifications
- [ ] Session view for multi-document trust propagation
- [ ] Re-scoring: change weights, re-score a historical event from stored signals

**Exit gate:** a person who has never seen the system can read a RED verdict and say *why*.

---

## Phase 5 — Week 8: Hardening and rehearsal

- [ ] **Pull the network cable.** Full run offline. Fix anything that reaches out.
- [ ] Latency measurement on the actual demo machine; publish p50/p95
- [ ] Memory ceiling check with all sessions warm
- [ ] Retention policy enforced: face crops expire, ID numbers hashed
- [ ] Provenance + licence slide for every dataset
- [ ] Demo rehearsal ×3, including **one honest failure case**
- [ ] Backup: pre-recorded video of the live capture flow in case the webcam fails on the day

**Exit gate:** three clean rehearsals, offline, on demo hardware.

---

## Cut list

If behind, cut **in this order**. Each is a deliberate trade with a defensible answer.

| # | Cut | What you say |
|---|---|---|
| 1 | Learned tamper segmentation model | "Classical signals are individually explainable and need no training data. Copy-move already gives region highlights." |
| 2 | Active liveness | "Passive liveness covers the realistic threat at a manned checkpoint where an officer is physically present." |
| 3 | Layer F temporal analysis | "Framework is in place; it needs deployment history to be meaningful." |
| 4 | Physical track for the four partial-coverage documents | "Physical security-feature detection is template-dependent. Implemented for the two highest-volume documents; it generalises." |
| 5 | 1:N gallery | Last resort — it is explicitly named in the problem statement. |

## Never cut

These five are what make the system credible to an SSB officer, and four are nearly free.

1. MRZ check digits (ICAO 9303) — your one real external standard
2. VIZ ↔ MRZ cross-check — highest-value tamper signal
3. Layer D trust propagation — the headline demo
4. Coverage floor (inconclusive is not pass) — a two-line safety property
5. The evidence list — without it you have a black box

## Weekly checkpoint

Five questions, every Friday:

1. Are the contracts still frozen?
2. How many calibration pairs are captured? (target 500 by end of week 4)
3. How many of six templates are done? (target 6 by end of week 4)
4. Does `docker compose up` still work from clean?
5. What is p95 latency on the demo machine today?
