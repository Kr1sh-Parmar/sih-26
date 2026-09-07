# Decision Log

Why things are the way they are. Read this before proposing a change — several of these look wrong until you know the reasoning.

Format: **Decision** · **Rejected alternative** · **Why**.

---

## D1 — No UIDAI dependency of any kind

**Rejected:** verifying the real Aadhaar Secure QR against UIDAI's published certificate.

**Why:** team decision, final. The architecture must not depend on any government key, certificate, API, or database. Aadhaar is treated exactly like the other five documents — signed by our reference issuer.

**Consequence:** we lose "we verify a real government signature." Our compensating real anchor is the **ICAO 9303 MRZ check digits** — a genuine public international standard requiring no permission, present on every passport in the world.

---

## D2 — Reference issuer, not an issuance product

**Rejected:** the full SecureDoc issuance platform (issuer registration, document creation, signing, QR generation, verification of our own signatures).

**Why:** SSB officers receive documents issued by *other* authorities, years ago. There is no `POST /api/documents` at a border checkpoint. A demo of "create a document, then verify the document you just created" proves SHA-256 works; it does not screen a stranger's document.

**Kept from that design:** canonicalise → hash → verify, the trusted key registry (now the trust anchor store), the verification state machine, `verification_logs`.

**Cut:** issuer registration, document creation, signing in the screening path, and the `document_data` table storing traveller PII.

**Added:** `NO_CRYPTO_ANCHOR` — the honest state for a document with no verifiable signature.

**Placement:** `issuer/` is out-of-band. It writes public keys into the trust anchor store during setup and is never called at inspection. Enforced by lint.

---

## D3 — Three trust classes, with cryptographic precedence

**Rejected:** one uniform confidence score across all checks.

**Why:** flattening a signature verification and an ELA heuristic into the same number destroys the information the officer most needs — *how much to trust this verdict*. It also produces false positives: an ELA hotspot over a cryptographically signed date of birth is noise, and fusion should know that.

---

## D4 — CPU only, Florence-2-base instead of Qwen2.5-VL-3B

**Rejected:** Qwen2.5-VL-3B INT8 via vLLM.

**Why:** no GPU. Qwen2.5-VL-3B on CPU is 15–25 s per image — not slow, unusable. vLLM is also CUDA-first and version-fragile for VLMs. Florence-2-base is 0.23B params, 1–2 s on CPU.

**Second reason, which matters more:** Florence-2's `<OCR_WITH_REGION>` returns text *with bounding boxes grounded in the image*. A chat VLM asked for JSON will confidently invent a passport number for an unreadable smudge, because generating plausible structured output is what it was trained to do. In a border system, plausible-but-wrong is worse than visibly-broken.

**Kept:** the Qwen path behind a config flag, for if a GPU appears.

**Mandatory regardless:** the checksum ratifier. No VLM output reaches validation unratified.

---

## D5 — Single process, not microservices

**Rejected:** one service per module.

**Why:** each service would receive the image via encode → HTTP → decode. A 3 MB scan serialised four times costs more wall-clock than the inference. One process, models warm, decode once, pass the numpy array by reference.

---

## D6 — Two-tier cascade, one risk gate

**Rejected:** running every check on every document.

**Why:** ~85% of documents are resolved by deterministic checks in under 400 ms. Deep forensics, active liveness, and 1:N search on all of them would blow the budget for no gain. All four modules independently converged on this pattern; it is unified at the system level rather than repeated four times.

---

## D7 — Weighted rules for fusion, not XGBoost

**Rejected:** gradient boosting over signal features.

**Why:** two reasons. There is no real forgery distribution to fit weights on — training on synthetic data would fit our own generator. And an officer detaining someone needs a justification, not a number. Weights live in YAML and can be tuned live on stage.

---

## D8 — Findings, not raw signals, in the score

**Rejected:** summing signal weights directly.

**Why:** one altered date of birth fires four correlated signals (VIZ↔MRZ mismatch, tamper mask overlap, font inconsistency, age mismatch). Summing inflates the score ~4× in exactly the cases that matter most, and shows the officer four bullets for one problem. Signals are grouped by anchor, combined with noisy-OR within a group, summed across groups.

---

## D9 — Coverage floor: inconclusive is not pass

**Rejected:** treating `inconclusive` as a zero contribution.

**Why:** a blurry photo makes the face check inconclusive → contributes 0 → total stays low → GREEN. You have just cleared an impostor because the camera was out of focus. Below 70% weighted coverage the verdict is AMBER with "re-capture required", never GREEN.

`not_applicable` is distinct: Aadhaar genuinely has no MRZ, so that check is excluded from the coverage denominator rather than counted as a gap.

---

## D10 — No 0–100 face score

**Rejected:** `((cos + 1) / 2) * 100`.

**Why:** it maps a total stranger (cos ≈ 0.0) to **50** and a confident impostor (cos ≈ 0.16) to **58**. An officer reads 58 as "more than half, probably him." The scale is misleading in the direction that admits fraudsters. Report a calibrated probability or three bands plus margin from threshold.

---

## D11 — Face threshold calibrated on our own doc-vs-live pairs

**Rejected:** published InsightFace/LFW benchmark thresholds as a starting point.

**Why:** those are live-to-live. Document photos are printed, halftone-screened, overprinted with guilloche, sub-300 DPI once scanned, and up to ten years old. The published threshold is wrong in the direction that rejects genuine travellers. With a live camera in the demo, this is a blocker, not a task.

---

## D12 — Tampering splits into physical and digital tracks

**Rejected:** one tampering module built around ELA, EXIF, and compression history.

**Why:** at a live counter the scanner writes the file. EXIF is clean, the image is single-JPEG, and a professionally printed physical forgery passes all digital forensics — because the image genuinely *is* a fresh scan. It is the object that is fake. Digital forensics only fires on uploaded files.

---

## D13 — Noise residual inconsistency, not PRNU

**Rejected:** calling it PRNU.

**Why:** PRNU is sensor-noise fingerprinting requiring ~50 flat-field images from a *known* camera to estimate a reference pattern. We have one image from an unknown device. The technique we actually run is SRM high-pass filtering with regional statistic comparison. Different method, different name, and a forensics-literate judge will catch it.

---

## D14 — No stamp template library

**Rejected:** a reference database of genuine stamp patterns with embedding similarity search.

**Why:** thousands of entry/exit stamp variants across countries and ports, with no public reference set obtainable. Replaced by duplicate detection (pixel-identical stamps are copy-pasted — the strongest and cheapest signal), date logic, and count-vs-declaration.

**Kept:** the embedding infrastructure, repointed at the face gallery where it is genuinely needed.

---

## D15 — ELA weighted 0.30

**Rejected:** ELA as a primary photo-replacement detector.

**Why:** global recompression after tampering flattens the difference, mixed-quality source images produce false bright patches, and PNG/PDF give nothing at all. It remains valuable as an officer-facing visualisation. Stating the limitation before a judge does reads as competence.

---

## D16 — Segmentation mask, not Grad-CAM, for localisation

**Rejected:** Grad-CAM heatmaps from a classifier.

**Why:** Grad-CAM localisation is coarse and hard to defend under questioning. Copy-move keypoint matching already produces real, checkable region highlights. (The learned segmentation model is cut-list item 1; classical signals alone are defensible.)

---

## D17 — One field detector for six document types

**Rejected:** one Roboflow model per document type.

**Why:** six warm ONNX sessions plus a classifier, versus one. Shared classes (name, dob, photo, signature appear on all six) generalise better from pooled data than six small models each seeing 200 images. A 22-class ontology covers all six; each profile declares expected and forbidden classes, and a forbidden class firing is itself a signal.

---

## D18 — Six document types, tiered tampering depth

**Rejected:** three documents deep (passport, Aadhaar, visa) with the rest detect-only.

**Why:** team decision. Six is in scope.

**How it is made survivable:** all six get extraction, validation, and face verification. Only passport and Aadhaar get the full physical tampering track, because physical security-feature detection needs a per-template geometric reference at ~2 days each. The other four get font consistency, layout geometry, and copy-move.

**Statable as:** "Physical security-feature detection is template-dependent. We implemented it for the two highest-volume documents; the framework generalises."

**Cost absorbed by:** cutting the learned tamper segmentation model.

---

## D19 — Cross-document trust propagation replaces passport↔visa

**Rejected:** passport↔visa cross-check as the Layer D demo.

**Why:** team dropped the visa cross-check. With six Indian documents, a better version exists: a signed document's payload becomes ground truth for unsigned documents presented alongside it. Scan Aadhaar and PAN together, the signed Aadhaar payload says DOB 1996, the PAN prints 1998 → hard fail with cryptographic backing.

This only works *because* six types are in scope. It is the headline demo.

**Note:** the passport↔visa comparison is near-free once both are extracted (string equality). The hook stays in the profile schema.

---

## D20 — Live webcam capture, real liveness

**Rejected:** pre-recorded frames.

**Why:** team decision. Consequences: the doc-vs-live calibration set becomes a blocker (D11), passive liveness must actually reject a printed photo and a phone screen, and the live-capture quality gate must take the sharpest of N frames because webcam autofocus hunting produces blur.

---

## D21 — Real sanctions lists as the watchlist seed

**Rejected:** an invented watchlist table.

**Why:** OFAC SDN and the UN Consolidated List are free, public, and real. They give the lookup genuine name-matching problems — transliteration variants, aliases, partial DOBs — which is the actually hard part of watchlist matching and the part a panel will probe.

---

## D22 — All data synthetic, including team documents

**Rejected:** building the demo database from team members' real Aadhaar, PAN, and passports.

**Why:** real ID numbers in a database that gets screen-recorded, demoed, and possibly committed is a genuine exposure under the Aadhaar Act and DPDP Act. Generating tampered variants would mean producing altered images of real government IDs — awkward to display to an MHA panel regardless of intent.

**The workable version:** real faces (consent), synthetic everything else. Team member's photo → synthetic identity with checksum-valid numbers → rendered onto a specimen template → printed, scanned, signed by the reference issuer. The face verification demo is unchanged; nothing is lost.

---

## D23 — PAN, EPIC and DL are structural checks, not check characters

**Rejected:** implementing a "PAN check character" algorithm.

**Why:** there isn't one to implement. The Income Tax Department publishes the
composition of a PAN — five letters, four digits, one letter, with the fourth
character encoding holder type and the fifth being the first letter of the
surname — but it has never published a check-character algorithm, and the
schemes circulating online are reverse-engineering folklore. The same is true
of the EPIC number and the driving licence number.

Earlier drafts of these documents said "PAN check character", and the Scene 3
fixture claimed *"PAN check character F is correct for ABLPG7040"*. That was
wrong, and it was wrong in the direction that overclaims certainty to a panel.

**What we actually verify for PAN:**

| Rule | Real? |
|---|---|
| `^[A-Z]{5}[0-9]{4}[A-Z]$` | published composition |
| 4th character is a valid holder-type code (P, C, H, F, …) | published |
| 5th character equals the first letter of the surname | published, and a genuine cross-field constraint |
| a check character over the other nine | **does not exist** |

The fifth-character rule is the one with teeth: it ties the number to the
printed name, so a spliced name breaks it. It is still not a checksum.
`check_pan("AAAPA0000A")` passes, and there is a test that asserts it does, so
the ceiling is recorded rather than discovered on stage.

**Consequence:** of the six documents, exactly two carry a real arithmetic
anchor — the passport and visa MRZ check digits (ICAO 9303) and the Aadhaar
Verhoeff digit. The other four have structure only. That is precisely the
national gap described in `CONTEXT.md` §5, and it is the reason cross-document
trust propagation (D19) carries so much weight on a PAN.

**How to say it:** "Aadhaar has a real check digit, Verhoeff, and we verify it.
The passport MRZ has five, from ICAO 9303, and we verify all of them. PAN,
Voter ID and the driving licence have published structure but no checksum — so
for those we verify structure, and lean on the signed document beside them."

---

## D24 — RapidOCR (PP-OCR on ONNX), not PaddleOCR

**Rejected:** PaddleOCR, as named in `TECHNICAL-SPEC.md` §4.

**Why:** the models are the same — PP-OCRv4 detection, angle classification and
recognition. The difference is the runtime. PaddleOCR brings `paddlepaddle`, a
second inference engine alongside ONNX Runtime, which sits badly against
CLAUDE.md rule 2: *every model is ONNX Runtime on CPU*. Two runtimes means two
sets of threading knobs, two memory pools and two things to prove offline.

RapidOCR ships the same PP-OCRv4 weights already exported to ONNX and runs them
on the `onnxruntime` we load everything else with. **The three model files ship
inside the wheel (16 MB)**, so nothing is fetched on first use — which matters
more than it sounds: PaddleOCR downloads its models on first call, and a model
fetch you forgot about surfaces exactly when the network cable comes out.

**What it costs:** Hindi. The bundled recogniser is `ch_PP-OCRv4_rec_infer.onnx`
— Chinese and English. The `aadhaar`, `voter_id` and `dl` profiles declare
`ocr_lang: [en, hi]`, and today only the `en` half of that is true.

Devanagari needs PP-OCR's `devanagari` recognition model and its character
dictionary, fetched at **build time** into `models/` and passed to RapidOCR by
config. That is a download and a licence check, not a code change, and it is
tracked rather than quietly ignored — an Aadhaar whose name is printed only in
Devanagari currently reads as `inconclusive`, which is honest but is not
coverage.

**Statable as:** "Same PP-OCRv4 models the paper describes, run on ONNX Runtime
so the whole system has one inference engine. Hindi recognition is a second
model file we have not yet added."

---

## D25 — Halftone is implemented, measured, and disabled

**Rejected:** shipping `tamper.physical.halftone` as a working check because the spec lists it.

**Why:** it was measured and it does not discriminate. On 200 genuine cards, detection rate equals the false-positive rate at every threshold, under both scorings tried (fraction of disagreeing tiles, and maximum deviation from the modal screen frequency). At the resolution these captures arrive at, print-screen consistency carries no information about tampering.

A check returning a coin flip is worse than no check. It is weighted 0.50 in `reliability.yaml`, so shipping it would inject noise into the score at half the strength of a real signal, and it would occupy an evidence card an officer reads as if it meant something.

So it reports **`inconclusive` naming that reason**, and costs coverage, exactly like the checks blocked by a missing template or a missing class. `physical.halftone()` and its evaluation are kept: on a 600 dpi flatbed scan the screen is genuinely resolved, and re-running `data/tools/eval_tamper.py` on such captures is how this gets revisited.

**Statable as:** "We implemented it, measured it, found it was noise at our capture resolution, and turned it off rather than let it contribute. The measurement is in the repository."

---

## D26 — Tamper thresholds are chosen from genuine documents alone

**Rejected:** tuning each threshold to the point that maximises detection on our own forgeries.

**Why:** CLAUDE.md's rule is to tune on one mutation family and report on another, because a threshold tuned against the forgeries it is then scored on measures the generator rather than the forgery. Choosing the cut from the **clean set only** — the score at which 5% of genuine cards get flagged — is a stronger version of the same discipline: no forgery participates in setting any threshold, so every family is held out by construction.

The 5% budget is an operational choice, not a round number. Tamper signals are weighted probabilistic evidence, never hard fails, so a false positive costs an officer a second look rather than a detention. It is still the number that matters most — a check that misses a forgery costs one signal; a check that accuses genuine documents makes an officer stop reading the whole evidence list.

**Consequence:** the reported numbers are lower than a tuned-on-forgeries version would print. Measured: copy-move 49.5% at 5.0% false positives, ELA 34–36% on splice and photo swap. `data/TAMPERING.md`.

---

## D27 — The layout reference is measured, not drawn

**Rejected:** hand-vectorised per-document templates for the layout geometry check.

**Why:** six templates is nine days of vector work the roadmap says cannot be compressed, and it was the thing blocking `tamper.physical.layout_geometry`. But the check does not need a drawing — it needs to know where each field sits on a genuine card, and 8,320 already-labelled cards say exactly that.

`data/tools/build_layout.py` writes the median normalised centre and spread per class per document type into `config/layout/<doc_type>.json`. It is a better sentence in front of a panel than a template would be: the reference is not our drawing of what a card looks like, it is what several thousand genuine cards did.

**Two limits, both enforced in code:** counts are unique source cards, not files — Roboflow ships five to ten augmented copies of each card and counting files would inflate every number and defeat the guard. And a field measured on fewer than 50 cards is recorded but never checked; `signature` has 25, from one source.

**What it does not replace:** guilloche continuity, which needs the actual line-work of a genuine document and remains blocked (D18).

---

## D28 — `confidence` is certainty, everywhere, including the face score

**Rejected:** carrying the raw cosine on `Signal.confidence` so the risk gate can test it against the review band.

**Why:** two consumers wanted incompatible things from one field. `fusion/gate.py` read it as a score; `fusion/findings.py` multiplies it by reliability in the noisy-OR, which only makes sense if it means certainty. The contract has always said certainty — *"0.0-1.0. For deterministic checks use 1.0"*.

Reading it as a score ran the wrong way. A **confident** impostor — cosine 0.10 against a 0.32 threshold — arrived at fusion as confidence 0.10 and was scored as a barely-there finding. Measured end to end, a genuine pair scored 0.130 and an impostor 0.129.

The face module now emits certainty, scaled so that any score inside the configured review band comes out below 1.0. That is an exact translation of the old band test, and the gate expresses it as *"escalate when the check is not sure"*. The same pair now scores 0.130 and 0.274.

**Worth naming:** this is D10 one layer down. A number that reads plausibly and is wrong in the direction that admits fraudsters, which is the failure mode this system exists to avoid.

---

## D29 — `buffalo_sc` and raw ONNX, not `buffalo_l` and the insightface package

**Rejected:** `InsightFace.FaceAnalysis` with the `buffalo_l` pack, as TECHNICAL-SPEC §4 names.

**Why, on the pack:** the Tier 1 face budget is 320 ms for two faces plus passive liveness (§2, L6). §4 puts `buffalo_l` at 160 ms per face — the entire budget spent before liveness runs. `buffalo_sc` is the same SCRFD-plus-ArcFace pipeline at 16 MB against 289 MB and measures 15 ms for both faces. On our separation check it buys nothing back: genuine median 0.890 against impostor median 0.019.

**Why, on the package:** `FaceAnalysis` downloads its own weights on first use, into a home directory, at whatever moment the first traveller arrives. That is precisely the runtime network call CLAUDE.md rule 3 forbids, and it would stay invisible in a demo right up until the cable came out. It also pulls scikit-image and cython in for a detector we can run on the ONNX Runtime session already in the process.

**What it costs:** about a hundred lines — SCRFD output decode and a five-point similarity alignment — both in `modules/face/`. `scripts/fetch_face_models.py --pack buffalo_l` measures the other side of the trade.

---

## D30 — Passive liveness is not deployed, and says so rather than passing

**Rejected:** shipping the face module without a liveness signal, or letting the check default to `pass` when weights are absent.

**Why:** MiniFASNet ships from Silent-Face-Anti-Spoofing as PyTorch `.pth`. The ONNX mirrors we found need an account; converting the `.pth` needs torch — which lives only in `.venv-train` and must never enter the screening process — plus the model class from that repository, whose licence needs reading before it goes in a submission. That is a decision, not an afternoon.

A spoof check that has not run must never look like one that passed. The signal is `inconclusive` and costs coverage, and the evidence string ends *"Confirm visually."* — at a manned counter the officer is the liveness check, and the console has to say the machine is not helping with this one.

Everything except the weights is written. Dropping `models/face_liveness.onnx` and its sidecar in place starts it returning verdicts with no other change; the registry already warms it and already reports it in the audit log.

**Consequence:** DEMO.md Scene 4 cannot be run as written. That is a scheduling fact, not a surprise on the day.
