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

---

## D31 — The generator renders programmatically; it does not vectorise specimens

**Rejected:** six hand-vectorised templates traced from PRADO and official specimens, ~1.5 days each, as `DATA.md` and `ROADMAP.md` both specify.

**Why:** vector art produces images with **no annotations**, and annotations are what was actually missing. `ghost_photo`, `barcode`, `hologram` and `doc_title` had zero instances in every scraped source — the detector could not learn them, and `tamper.physical.ghost_missing` was blocked on a class that never appears on any card the model has seen. Nine days of drawing would have produced six beautiful documents and not one label.

A renderer knows where it drew each field, so the YOLO label is a by-product of drawing rather than a second job. All four empty classes filled on the first run.

**What it also bought:** guilloche drawn the way it is actually made — a hypotrochoid, the curve a rose engine traces — so the physical track has continuous line-work to check a break against, rather than a texture that only looks the part. And a `session()` that emits a matched Aadhaar+PAN pair with one signed and one disagreeing, which makes Scene 3 a data file instead of a hope.

**What it costs:** the documents are cleaner than real print. `DATA.md` is right that a model trained only on clean renders falls apart on a scanner, and the print-and-rescan pass is still owed.

---

## D32 — Generated numbers are constructed by the validator, not checked against it

**Rejected:** the generator computing its own check digits, Verhoeff included.

**Why:** two implementations of the same checksum that drift apart produce a set where every document is quietly invalid *and* every validation test still passes, because both sides are testing the same bug. `verhoeff_digit()` in `modules/validation/checksums.py` has carried the docstring *"Used by the synthetic generator"* since it was written, with nothing using it. It does now, along with `mrz.build_td3()` for the TD3 strip.

The identity is also **self-consistent by construction** — one person, one date of birth, one face across every document they hold. Making two documents disagree is then a single deliberate edit, which is exactly the shape Layer D needs to demonstrate.

That last part was not free. The portrait was first picked from the *render* seed rather than the identity, so one person's Aadhaar and PAN carried two different faces. Invisible on a single card and fatal in a session: Scene 3 puts the two side by side, so an officer would have been shown two different people, and the face module would have flagged a generator artefact as a mismatch. The portrait belongs to the identity now, and a test asserts it.

---

## D33 — The raw capture expires; the audit trail does not

**Rejected:** one retention rule for everything a screening produces.

**Why:** they are two different things with opposite requirements. The **document image** is the traveller's identity document, and `TECHNICAL-SPEC.md` §9 says it must not outlive the session — it is the only unredacted personal data the system ever holds. The **signal list** is the audit trail, and CONTEXT.md §3 says decisions get challenged months later, so it has to survive long enough to be re-scored.

So `api/main.py` evicts `PENDING` (raw bytes, decoded context, live frame) and `SESSIONS` (Layer D priors) on a TTL from `config/thresholds.yaml`, and evicts nothing from `screening_events` or `face_gallery`. A 512-float embedding cannot be turned back into a face; a JPEG can be turned back into a person.

**What this fixed:** the comment above those two dicts already claimed this behaviour. Nothing implemented it. Every upload's bytes stayed resident for the life of the process and `GET /screen/{id}/image` served them back indefinitely — an unbounded memory leak and a stated-policy violation in the same four lines.

**Session priors expire too, and that is the sharper half.** A signed Aadhaar from an hour ago still sitting in `SESSIONS` would become ground truth for whoever is standing at the counter now. Layer D would then cross-check a stranger's PAN against a payload that proves nothing about them.

**ponytail:** eviction is opportunistic, on the next request that touches the map, not a background task. A single-counter process does not need a scheduler, and a scheduler is one more thing that can be wedged at 3am. The ceiling is that nothing expires while the process is idle, which is acceptable when the thing being bounded is memory.

---

## D34 — Re-scoring reconstructs the signed field set from the record

**Rejected:** persisting the verified payload so a re-score can reproduce cryptographic precedence exactly.

**Why:** the payload is the traveller's name, date of birth and gender. Storing it to make an audit feature more faithful would put exactly the personal data CLAUDE.md rule 5 and `TECHNICAL-SPEC.md` §9 exist to keep out of the database — and it would sit there for the life of the audit trail, which is the longest-lived thing in the system.

`fusion.score.apply_crypto_precedence` needs `signed_fields` to know which probabilistic disputes a signature already settled. On re-score that set is rebuilt from the stored signals instead: every `field:` anchor carrying a `cryptographic` trust class. It is an approximation and is documented as one — a signed field that nothing disputed is absent from it, and its absence changes nothing, because there is no probabilistic finding at that anchor to suppress.

**The other half of the same decision:** `api/router.rescore()` restates `score()`'s ordering — hard fail, coverage floor, cryptographic precedence, bands — because the coverage floor is itself band-dependent and cannot be re-banded after the fact. Every piece of arithmetic is imported rather than copied; only the order is written twice, and `tests/test_rescore.py` pins the two together by asserting they agree exactly when handed the configured bands. The real fix is a `bands=` parameter on `score()`, which is a change to frozen-contract-adjacent code and was left alone deliberately.


---

## D35 — The ratifier discards a failed read rather than storing it

**Rejected:** storing every VLM read and letting the score account for the ones that fail their checksum.

**Why:** a value known to be wrong is not inert. Layer C compares the printed value against the MRZ and Layer D compares it against a signed sibling document, so a misread identity number does not sit quietly with a low weight — it *manufactures* a mismatch, in the two checks this system is actually sold on. The cheapest way to keep a bad read out of those comparisons is never to put it in `ctx.fields`.

The three-way outcome TECHNICAL-SPEC §4 describes maps onto the frozen `TrustClass` like this: checksum verifies → stored, `arithmetic`; checksum fails → **not stored**, `extraction.vlm.ratified` fails; no checksum exists → stored, `unverified`, and it costs coverage.

**`force MANUAL_REVIEW` needed no new mechanism.** Unratified fields emit `inconclusive`, coverage drops below the 0.70 floor, and the verdict is AMBER "re-capture required" (D9). Measured end to end on a generated passport: coverage 0.28, AMBER.

**Two signals, not two per field.** `extraction.vlm.ratified` and `extraction.vlm.unratified` are registered as concrete ids with one weight each, and one screening may not emit an id twice. "Some of this output could not be checked" is one condition however many fields it covers; charging coverage per field would count one problem several times (D8).

---

## D36 — The fallback fires when nothing was located, not only on a weak read

**Rejected:** the documented trigger alone — a field OCR located and read below its confidence floor.

**Why:** `extraction.run()` only calls OCR when `ctx.field_boxes` is non-empty, and with no detector weights it is always empty, so the documented trigger can never fire on the system as it stands. `<OCR_WITH_REGION>` reads a whole page and grounds each string in a box; it needs no field to aim at. That makes it the only reader that works before the detector comes back from the GPU.

**What it costs:** the fallback now runs on every document, so every screening pays 6 to 8 seconds. That is the honest price of reading anything at all right now, and it disappears the moment the detector lands.

**What it is worth, measured:** correct dates and nothing provable. Florence-2 transcribes dates exactly and drops or inserts characters in names and identity numbers — `CHABRA` for `CHHABRA`, `M37011978` for `M3701978`. It does not return the MRZ as a parseable strip. So the ratifier has not yet confirmed a single real read, and the fallback improves coverage and evidence without letting a document clear. `data/EXTRACTION.md` carries the numbers.

**And the spec is optimistic.** §4 says 1.5 s and §10 budgets +1,500 ms; the measurement is 5.8 to 7.3 s per document against an 8 s hard timeout. The timeout was written as a safety net against a hang and is now a live constraint.

---

## D37 — An unverified read may not contradict a proven value

**Rejected:** letting Layers C and D compare whatever sits in `ctx.fields`, regardless of how it got there.

**Why:** it was reachable, and the consequence was the worst verdict this system can produce. Florence-2 transcribes a date perfectly and then returns `CHABRA` for `CHHABRA` (`data/EXTRACTION.md`). The ratifier correctly stores such a field as `unverified` — no checksum exists for a name, so nothing can confirm it. Layer D then compared that string against a cryptographically proven payload, found it different, and emitted `validation.crossdoc.name_mismatch`: **a hard fail on four profiles, carrying trust class `cryptographic`** because the *other* side of the comparison is signed.

A genuine traveller detained on a transcription error, with the console reporting the strongest certainty the architecture has. Verified empirically before the fix: a one-character misread on a generated PAN, against a signed Aadhaar prior, produced `fail / hard_fail=True / cryptographic`.

That is exactly the laundering of a probabilistic read into a cryptographic verdict that D3 exists to prevent. The trust class was never wrong about the *signature* — it was wrong about the comparison, which is only as strong as its weaker side.

**The fix:** `modules/validation/__init__.py` defines `COMPARABLE_SOURCES = {"ocr", "mrz", "qr"}` and `comparable()`. Each of the three earned its place — `qr` is a signed payload, `mrz` carries its own check digits, `ocr` is gated on a confidence floor. `vlm` has none of the three. When the only reading of a field came from the fallback, Layers C and D report `inconclusive` naming that reason, which costs coverage — correct, because agreement genuinely was not established (D9) — and never produces a false hard fail.

**What it does not do:** go blind. An OCR-sourced disagreement still fires and still hard-fails; Layer D trust propagation is the headline demo and is on the never-cut list. Four tests in `tests/test_validation.py` pin both halves.

**The general lesson, worth more than the fix:** a comparison inherits the trust class of its *weakest* input, not its strongest. Anywhere else two values of different provenance are compared, the same question applies.


---

## D38 — Guilloche continuity was measured against a real one, and stayed off

**Rejected:** enabling `tamper.physical.guilloche_break` once the generator gave us line-work to check.

**Why:** the old block said guilloche needed a reference drawing we had not built. `data/generator/` draws one now — a tiled hypotrochoid, the curve a rose engine actually traces — so that reason expired and the check was re-examined properly. Three formulations were measured:

- **low-energy islands**, on the theory that a pasted patch erases the pattern: no separation at all. A retyped box comes out *higher* energy than its surroundings, because the redrawn text adds more edge than the erased background carried;
- **inside-versus-outside texture ratio**: separates, but content-driven and inconsistent in direction — 3.10 on retype and 0.14 on photo swap, on the same statistic. It measures "is this region texturally unusual", which is what `ela` and `noise_residual` already report. A third reading of one artefact is the correlated double count D8 exists to prevent;
- **phase continuity at the tile period**: clean documents score 0.039–0.083. There is no phase to break — the generator varies the figure tile to tile, so adjacent tiles are already uncorrelated.

So it stays `inconclusive`, but **the sentence the officer reads has been corrected**. "We have no template" is no longer true and would have quietly become a lie the moment the generator landed. It now says the check was measured and does not separate a break from ordinary variation.

**The caveat, which cuts the other way:** the third result is partly a fact about *our* guilloche rather than about guilloche. A real passport's background may be more regular, in which case phase continuity becomes measurable. `hypotrochoid()` and the probe stay in the tree for that reason, and this is worth re-testing against a specimen scan.

**`photo_boundary` was declined at the same time.** TECHNICAL-SPEC §7 and MODULES.md both name it; it has no registered ID and no reliability weight, so it would silently take `_default: 0.50`. The edge artefact it looks for is the same pixel evidence copy-move already verifies by correlation. Named in `data/TAMPERING.md` rather than built.

---

## D39 — The ghost portrait check is a comparison, which is why it works

**Rejected:** treating the ghost portrait as another texture statistic alongside halftone and guilloche.

**Why:** every other check in the physical track asks "does this region look like the rest of the page", and all of them are fragile for the same reason — they measure content as much as source. The ghost is different in kind. It is *the same photograph printed twice*, so the check is whether two regions show the same face, and that question does not care how the document was printed, scanned or lit.

Measured on 24 generated passports and Aadhaar cards: genuine pairs correlate at median 0.991, minimum 0.952; a swapped portrait with the ghost left alone drops to median 0.732, maximum 0.884. At a cut of 0.90 — six percent below the lowest genuine score, chosen from the clean distribution alone (D26) — no genuine document is flagged and every swap is caught.

Both portraits are equalised before comparison. The ghost is printed lighter and softer by design, so comparing raw intensity would report every genuine document as a mismatch.

**The number is optimistic and is labelled as such.** Our generator makes the ghost a literal downscale of the same pixel array, so it correlates near-perfectly. A real ghost is separately halftone-printed at a different size; genuine agreement will be materially lower, and the threshold needs re-fitting on real captures before anyone quotes 100%.

**A missing ghost is a failure, not a gap.** If the detector found the main portrait on the same page and no ghost on a document type that carries one, the absence *is* the finding — not an absence of one.

---

## D40 — Passive liveness deployed, and the input contract is recorded rather than remembered

**Supersedes the "not deployed" half of D30.** The blockers were a licence read and a format conversion; both are done. Silent-Face-Anti-Spoofing is **Apache-2.0**, which permits redistribution with attribution, so `scripts/convert_liveness.py` fetches the `.pth`, loads it through upstream's own architecture file, and exports ONNX under `.venv-train` — torch goes in, ONNX comes out, and only the ONNX crosses back into the screening image.

**Rejected:** trusting the input contract that was written before the weights existed.

**Why:** it was a guess, and it was wrong twice. The module normalised to `[0, 1]` and swapped to RGB; the model wants **raw 0-255 BGR**, because upstream's `ToTensor` is not torchvision's — it transposes and calls `.float()`, with no scaling and no channel swap.

Neither mistake raises. The network returns three plausible probabilities for an image it was never trained on. With the division in place, **every genuine face scored 0.006 live and the check rejected 100% of real people** — a liveness check that fails every traveller and looks like it is working. Without it, 0.968 against 0.001 for a simulated spoof.

The export verified torch against onnxruntime on a **black frame**, which could not have caught it: zeros are invariant under scaling. The reference is a deterministic ramp now, and `colour_order` and `input_range` are in the sidecar so the assumption is checkable instead of remembered.

**What is still owed:** an actual printed photo and an actual phone screen on the demo camera. The simulated attacks establish direction and separation, not a rejection rate, and `data/FACE.md` says so in those words.

---

## D41 — Demographic disparity is recorded as unmeasured, not as absent

**Rejected:** shipping a face module with no statement about demographic performance, or with a reassuring one.

**Why:** NIST FRVT found demographic false-match differentials above an order of magnitude across algorithms. A system that has not measured its own is not a system without a disparity, and MODULES.md calls this a compliance item rather than a nice-to-have.

`scripts/eval_bias.py` is written and runs the moment either dataset is on disk. Neither can be fetched unattended here: FairFace ships its images through Google Drive, RFW requires signing a licence.

One thing worth knowing before anyone runs it, because it changes what the result can mean: **FairFace has one image per person.** With no identity labels there are no genuine pairs, so it yields a false *match* rate by group and cannot produce false rejection at all. RFW carries identities and gives both halves. The harness does whichever the data supports and prints which one it did.

So the honest line for a panel is "unmeasured, here is the harness and here is what each dataset can tell you" — not a number, and not silence.


---

## D42 — The machine-readable zone is read from where ICAO says it is, not from a detector box

**Rejected:** waiting for the field detector before reading any field on any document.

**Why:** the detector is the long pole — it trains on a GPU elsewhere, and until it lands `ctx.field_boxes` is empty, `ocr.run` never executes, and *nothing* is read off any document. But the MRZ does not need a learned detector to be found. ICAO 9303 fixes it at the foot of the data page, which makes it the only field on any of these six types whose position is given by an international standard rather than by a national design.

Reading it from that fixed band switches on all five ICAO check digits in Layer A and the whole VIZ↔MRZ cross-check in Layer C — both already written, tested, and previously unreachable. It costs about two seconds and is both cheaper and more accurate than asking Florence-2 for the same strip, which does not return it as a parseable 44-character line at all.

**The bug this uncovered.** The band catches the microtext strip beneath the MRZ, so the read arrived as four lines of 44/44/22/18. The geometry gate saw four lines, rejected the lot, and *a perfectly read MRZ was discarded because the crop was not tight*. `select_mrz_lines()` now picks the contiguous run matching a supported geometry. This does not weaken the gate — the selected lines must still be exactly the right width, still pass the charset check, and still satisfy the check digits. It also un-broke `apply_positional_charset`, which returns untouched unless given exactly two lines and had therefore been silently doing nothing whenever a stray row was present.

---

## D43 — On an untargeted read, the check digits test the reading, not the document

**Rejected:** handing every well-formed MRZ strip from the fixed-position read straight to Layer A.

**Why:** measured over 30 generated passports, that path is **70% character-exact**. The remaining 30% produce a well-formed 44-character strip with a wrong character in it, which fails a check digit — and a failed composite check digit is a hard fail. Roughly a fifth of *genuine* passports would have been detained on an OCR error, and the officer would have been told so with arithmetic certainty.

A confidence gate cannot save it. PP-OCR's confidence does not separate the cases: the misreads scored **higher** on average (0.791 median) than the exact reads (0.751 median, minimum 0.576). Upscaling the band moved accuracy 67% → 72%, which is not a fix either.

So on this path the ICAO check digits are used as a **self-test of the read** before the strip is stored. A strip whose own check digits disagree with its characters is reported as unreadable — *"could not be read reliably … re-capture at a higher resolution"* — because with a reader this accurate, a failure is far more likely a misread than a forgery. Measured after the change: **15 of 15 genuine passports AMBER, none RED.**

**The cost, stated plainly: this path can confirm a good machine-readable zone and can never report a tampered one.** That is a real loss of capability. It is smaller than the alternative, because before this nothing was read at all, and it is temporary: `_read_mrz_field`, the detector-fed path, deliberately keeps the geometry gate alone, so when a tight crop puts the reader in a different accuracy regime, forgery detection survives there.

---

## D44 — `ocr_lang` became live config; the Devanagari reader did not arrive

**Rejected:** leaving `extract.ocr_lang` as a declaration nothing reads.

**Why:** `aadhaar`, `voter_id` and `dl` all declare `ocr_lang: [en, hi]`, and no Python read the key. Measured, the bundled `ch_PP-OCRv4_rec_infer.onnx` returns an **empty string at confidence 0.00** on rendered Devanagari — not garbage, nothing. Empty is the safe failure, because it becomes `inconclusive` rather than a wrong value, but the officer was told only "could not be read", and would re-capture a document that reads the same way every time.

The key is now read, the recogniser is selected per profile, and the Devanagari pass is a **fallback rather than a switch**: every value on all six types is printed in Latin as well as Devanagari — the Hindi is a second rendering of the same field, not a field of its own — so Latin runs first, succeeds almost always, and costs nothing.

**The model is not deployed.** PaddleOCR publishes Devanagari as a Paddle inference model; every `paddle2onnx` on PyPI imports `paddle`, and the PaddlePaddle download timed out here. `scripts/fetch_ocr_models.py` does the fetch and conversion when the toolchain exists and otherwise says exactly what is missing. Until then the evidence string names the cause.

**Deliberately not built:** a Hindi-versus-Latin cross-script consistency check. It would be a real tamper signal and it needs transliteration; an approximate comparison feeding a mismatch signal is precisely the failure just fixed in Layers C and D.

---

## D45 — The VLM fallback yields to the machine-readable zone

**Rejected:** running Florence-2 whenever nothing was located, including on documents whose MRZ had just been read successfully.

**Why:** it spends the whole remaining budget re-reading fields we already hold, and holds better. A verified MRZ carries surname, given names, document number, nationality, date of birth, sex and expiry — every field the VLM could offer for a TD3 — each with its own ICAO check digit. That is `arithmetic` trust against the fallback's `unverified`, and it arrives in about two seconds rather than seven.

Measured over ten generated passports, full screening end to end:

| | median |
|---|---|
| MRZ read, fallback skipped (9 of 10) | **1,702 ms** |
| MRZ unread, fallback runs to its 8 s ceiling (1 of 10) | **9,634 ms** |

A 5.6× difference on the common path, and the documents it helps are precisely the ones that were sitting against the timeout.

**What it costs, stated rather than buried:** the few printed fields a TD3 does not carry. A passport prints the father's name; the MRZ does not. Those reads would have arrived `unverified`, which `COMPARABLE_SOURCES` already bars from contradicting the MRZ or a signed payload (D37) — so they were evidence, never verification. Seven seconds is too much to pay for that.

**The skip is announced, not silent.** `extraction.vlm.ratified` reports `not_applicable` saying the fallback was not needed because the zone supplied these fields with their own check digits. A check that quietly does not run is the thing this system spends most of its evidence strings avoiding.

**Where the fallback still earns its place:** documents with no MRZ — Aadhaar, PAN, Voter ID, DL — where it contributes correct dates and grounded regions and there is no better reader. The guard keys on `ctx.fields["mrz"]`, which `_mrz_from_its_fixed_position` sets only once the strip's own check digits agree, so it is a verified read and not merely a read.

---

## D46 — A near-match on the watchlist reports, it never detains

**Decision:** Layer E gained phonetic near-matching, and a near-match emits `inconclusive` — never `fail`.

**Why the second half matters more than the first.** `validation.watchlist.hit` is listed under `hard_fail` in all six profiles. A `fail` verdict from this layer is not a score contribution that fusion weighs against others; it is RED, detain, immediately. So the question was never "can we match more names" — it was "what is a fuzzy match allowed to do once it finds one".

A near-match is a guess about spelling. Letting a guess about spelling detain somebody at a border is the single worst thing this layer could do, and it would do it most often to exactly the names the transliteration is hardest for. So the three strengths of evidence are kept apart and given different verdicts:

| Match | Verdict | Confidence |
|---|---|---|
| Document number, exact | `fail` | 1.0 |
| Name key, exact | `fail` | 1.0 |
| Name, phonetic near-miss | `inconclusive` | 0.30 + 0.30 × ratio |

The evidence string says the spellings differ, names both, and asks for a manual check against the listed entry. That is a sentence an officer can act on; a detention triggered by a spell-checker is not.

**How it works, and why it is stdlib.** Soundex buckets the 8,256 loaded OFAC + UN entries by sound; `difflib.SequenceMatcher` then decides, on characters, within the handful of candidates a bucket holds. Soundex alone is far too loose to accuse anyone with — collapsing "Gharat" and "Ghorat" is the point, but it collapses plenty of genuinely different names too — so it only ever picks candidates, and the ratio makes the call. `jellyfish` and `rapidfuzz` both do this better and neither is worth a wheel in an image that installs offline from a locked requirements file.

**Measured on the loaded list:**

| | |
|---|---|
| Index build, once per process | 72 ms, 7,751 buckets, largest bucket 4 names |
| Lookup | p50 **0.06 ms**, p95 **0.11 ms** |
| Recall, 60 listed names with one vowel transliterated | **56 / 60** |
| False positives, 15 unrelated Indian names | **0** |

The floor sits at a 0.84 character ratio: "Prodeep Ghorat" against "Pradeep Gharat" scores 0.857.

**The ceiling, stated:** this catches vowel and transliteration drift. It does not catch a name written in a different script, a reversed patronymic, or a deliberate near-alias chosen to sit just outside the threshold. It is a better net than exact match, not a solved problem.

---

## D47 — Impossible transit fires only where transit can actually be observed

**Decision:** `screening_events` gained a `post_id` column and `config/posts.yaml` gained the network's geography, so the impossible-transit check now genuinely fires. Its default did not change: with `SCREENING_POST_ID` unset it still reports `not_applicable`.

**Why the default survived the implementation.** The reason this check was inert was never that the code was unwritten — it was that a single-post installation cannot observe transit. The only thing one machine can see is the same document twice at its own counter, which is what a re-capture and a secondary inspection both look like. An officer who is told "impossible transit" once, wrongly, stops reading the whole evidence list. That argument is unchanged by the column existing, so the `not_applicable` path is kept and tested.

**What changed:** where two posts write into the same audit store, a prior screening at a *different* post is compared on distance and elapsed time. `config/posts.yaml` holds published ICP coordinates and a 60 km/h ground-speed ceiling; distance is computed by haversine rather than typed into an N×N table that has to be re-typed every time a post is added.

**The threshold is deliberately generous.** 60 km/h is road travel through the Terai. A pair of crossings that beats it is not "suspicious" — it is physically impossible, which is the only claim worth making from two timestamps. The evidence names both posts, the distance, the time available and the time required, and offers the innocent explanation alongside the guilty one: either the document was duplicated, or one crossing was recorded against the wrong document.

**A post outside the table is `inconclusive`, not ignored.** The distance is unmeasurable and inventing one would be worse than saying so — but the officer is still told the document was presented somewhere else.

**The migration is additive and has to stay that way.** `screening_events` is the audit log; a verdict in it may be challenged months later (CONTEXT.md §3), so a migration that rewrites or drops a row destroys what the table is for. `ALTER TABLE ADD COLUMN` leaves the 13 existing events reading `post_id` NULL, which is the truthful answer for a machine that was not part of a network when it screened them.
