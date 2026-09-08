# Demo Script and Rehearsal Checklist

The demo is not a feature tour. It is four scenes that each prove one claim, plus one honest failure.

Total target: **7 minutes**.

---

## The claim you are proving

> We verify identity documents at three levels of certainty — cryptographic, arithmetic, probabilistic — and we tell the officer which level each verdict came from. It runs on a commodity CPU with the network cable unplugged.

Every scene proves part of that sentence.

---

## Scene 1 — The clean pass (60 s)

**Do:** scan a genuine synthetic passport. Officer sees a GREEN verdict with the evidence list.

**Say:** "Five MRZ check digits, verified arithmetically against ICAO Doc 9303 — a public international standard. No network, no database, no external key. This is the same check every e-gate in the world performs."

**Proves:** the pipeline works, latency is real, and you have one genuine external anchor.

**Watch for:** measured 2026-09-08, the verdict lands at **~1,390 ms** on this machine, not the ~450 ms this line used to claim — and only if a throwaway document has already been screened. See the rehearsal record.

---

## Scene 2 — The tamper (90 s)

**Do:** take the same passport, alter the printed date of birth (pre-prepared forgery), scan it. RED.

**Say:** "The forger edited the printed date and left the machine-readable zone alone. The two disagree. That's not a model output — it's two fields being different, and the officer can read both."

**Proves:** the highest-value tamper signal, and that your evidence is checkable by a human.

**Watch for:** the evidence card must name both values. One finding, not four bullets.

---

## Scene 3 — Cross-document trust propagation (120 s) — **the headline**

**Do:** scan a signed Aadhaar and a PAN card in the same session. The signed Aadhaar payload says DOB 1996. The PAN prints 1998. Hard fail.

**Say:** "Four of six Indian identity documents carry no cryptographic integrity today. When one document *is* signed, its payload becomes ground truth for the others presented alongside it. The signature verifies, so the date of birth is proven — and the PAN contradicts it. No machine learning, cryptographic certainty."

**Then, before they ask:** "These are our signatures, from a reference issuer we built — we have no government keys. The trust anchor store is keyed by issuer; where real signatures exist in production, it takes a different key and the verification code is unchanged."

**Proves:** the trust-class architecture, and that you understand the real national gap.

**Watch for:** the console must render the `disclosure` string. Do not let a reference verification look like a government one.

---

## Scene 4 — Live face and liveness (90 s)

**Do:** a teammate stands at the camera holding their document. MATCH. Then hold a printed photo of them to the camera — liveness rejects it.

**Say:** "Threshold calibrated on 500 document-to-live pairs we captured ourselves, on this camera. Published benchmarks are live-to-live; a passport photo is printed, screened, and up to ten years old — different domain, different threshold."

**Then show the FAR/FRR control:** "At 5,000 passengers a day, a 2% false rejection rate is 100 secondary inspections. The checkpoint commander sets this, not us."

**Proves:** you understand operating points, not just accuracy.

---

## Scene 5 — The honest failure (45 s)

**Do:** show a document your system does *not* flag, or one where coverage is insufficient and the verdict is AMBER "re-capture required".

**Say:** "Our forgery test set is synthetic — real forged passports aren't obtainable, for obvious reasons. We report accuracy on our own generated set and label it as such. This document is one we don't catch."

**Proves:** you know your limits. This buys more credibility than any number.

---

## Closing (30 s)

Unplug the network cable. Run Scene 1 again.

"No internet. No GPU. Eight-core CPU. That's what a border post at Raxaul actually has."

---

## Pre-demo checklist

### 72 hours before
- [ ] Full offline run: cable physically out, three consecutive clean passes
- [ ] Latency measured on the actual demo machine, p50 and p95 recorded
- [ ] All demo documents printed and scanned (do not demo digital renders)
- [ ] Forgery samples pre-prepared and tested
- [ ] Liveness tested against a printed photo **and** a phone screen
- [ ] Backup video recorded of the full flow

### 24 hours before
- [ ] `docker compose down -v && docker compose up` from clean — works
- [ ] Webcam tested in the actual demo lighting
- [ ] Screen resolution and console legibility checked from 3 metres
- [ ] Three full rehearsals, timed

### On the day
- [ ] Machine on mains power, sleep disabled
- [ ] Backup laptop with the same image
- [ ] Documents in scan order, in a folder
- [ ] Backup video on a USB stick
- [ ] Provenance/licence slide loaded

---

## Questions you will be asked

| Question | Answer |
|---|---|
| "Where did your training data come from?" | Every document is synthetic, generated from published specimens with checksum-valid identity numbers. No real government ID is in our dataset. Provenance slide, with licences. |
| "Those are your own signatures — how is that verification?" | Correct, and we say so in the UI. Four of six documents have no cryptographic integrity in reality. We demonstrate signed verification end to end and validated our path against ICAO 9303, which is real. Swapping in a real issuer key changes no code. |
| "What's your accuracy?" | On our synthetic tamper set, [X]. Trained on one mutation family, tested on another — [Y] on the harder set. Untested against professional forgery; we can't obtain it. |
| "Does this work on a scanned e-visa PDF?" | Yes — that path enables the digital forensics track (EXIF, double-JPEG). At a live counter those are useless because the scanner writes the file, which is why the physical track is primary. |
| "What about bias in face recognition?" | Measured on FairFace and RFW. Our disparity is [X]. It's a known issue with real consequences at a border, which is why the officer decides and we show the margin from threshold. |
| "Why not use a GPU?" | Border posts don't have one. Everything is ONNX int8 on CPU. Measured on our box: **154 MB warm and idle, 185 MB screening a document it can read**. The Florence-2 fallback is the exception — when it loads, the process reaches 1.5 GB, and today it loads on every document the field detector should have read. Numbers and method in the rehearsal record. |
| "Can it be fooled?" | Yes. Professional forgery with matched materials would likely pass our physical checks. That's why the system assists rather than decides, and why the evidence list matters more than the score. |

---

## Things that will break the demo

| Risk | Mitigation |
|---|---|
| Webcam autofocus hunting → blurred frames → inconclusive | Take sharpest of N frames; test in demo lighting |
| A model tries to download at runtime | Verified by pulling the cable in rehearsal |
| VLM fallback hangs | 8-second hard timeout, falls through to re-capture |
| Scanner not available at the venue | Phone camera fallback tested; capture flow works either way |
| Judge asks for a document type you cut deep coverage on | Know your tiering table; answer with the trade-off, not an apology |
| Latency spike from a cold session | Warm all models at startup; do one throwaway inference before the demo starts |

---

# Rehearsal record — 2026-09-08

Supersedes the 2026-09-07 record, kept below. Driven through the real pipeline:
real lifespan warm-up, the real trust anchor store from `var/screening.db`, real
fusion, and the actual demo documents in `var/demo/`. Not a mock of anything.
What follows includes the parts that did not work, and one part that works in a
way that is worse than not working — DEMO.md's own Scene 5 argues that knowing
your limits buys more credibility than any number, and that applies hardest to
this page.

**The one fact that still shapes every line below:** `field_detector_22cls` is
not deployed. Training moved to an external GPU (`MODEL-TRAINING.md`). Without it
`ctx.field_boxes` is empty, `ocr.run` never fires, and **nothing reads printed
ink on any document**.

```
health: loaded  = face_detector, face_embedding, face_liveness, ocr
        missing = field_detector_22cls
```

## Correction to yesterday's record, and the hole it exposed

Yesterday this page said every verdict is AMBER because nothing printed can be
read. That was overstated, and chasing the overstatement found a real hole.

`gen_passport.png` **used to score GREEN, coverage ~0.75**, clear of the 0.70
floor, without reading one printed character:

- the MRZ is read from its ICAO fixed position and **all five check digits
  verify** - `document_number`, `dob`, `expiry`, `optional`, `composite`;
- the Ed25519 signature on the QR verifies against the reference issuer, so
  `validation.signature.valid` and `issuer_trusted` are cryptographic passes;
- `seed_from_payload` then fills the remaining fields from the signed payload.

**That last line was the hole.** Every field except the MRZ had `source=qr`, and
`COMPARABLE_SOURCES` contained `qr` - so `validation.vizmrz.*` compared the
*signed payload* against the MRZ, two artefacts the issuer produced together
from one record, and reported six arithmetic passes. The evidence string read
"MRZ date of birth 1960-03-24 matches printed 1960-03-24" when no printed value
existed anywhere in the comparison. Wrong, and wrong in the reassuring
direction.

Measured consequence, before and after the fix:

| Document | Before | After |
|---|---|---|
| `gen_passport.png`, untouched | **GREEN** 0.752 | AMBER 0.496 |
| `mutate.retype` - print band wiped and reprinted | **GREEN** 0.752 | AMBER 0.496 |
| `mutate.photo_swap` - portrait replaced | **GREEN** 0.752 | AMBER 0.496 |
| `mutate.splice` | AMBER 0.447 | AMBER 0.496 |

**A forged passport was being cleared.** Yesterday's blanket AMBER had been
concealing the missing reading path behind a safety property; once signature and
MRZ alone could clear the floor, the concealment went with it.

`PRINTED_SOURCES` now separates ink from payload: `ocr`, `mrz` and `vlm` are
read off the page, `qr` never touched it. The six checks report "could not be
read" and cost coverage, so the passport is AMBER "re-capture required" again -
this time for the honest reason. Layer D is deliberately untouched: comparing a
signed payload against *another* document is trust propagation, and there the
payload not being on this card is the whole point.

**Say this plainly if asked:** the fix does not *detect* the retype. It declines
to clear it. Detection returns with the detector, when there is real ink to
compare. A system that cannot read a document must not clear it, and that is now
true again.

**Scene 1 still cannot be run as a clean pass until the detector lands** - but
because the passport correctly reads AMBER, not because it wrongly reads GREEN.

## Scene by scene, as measured today

| Scene | Runs today? | What actually happened |
|---|---|---|
| 1 — clean pass | **No** | AMBER, coverage 0.496, "insufficient evidence — re-capture required". The MRZ is read and all five check digits verify, and the signature verifies — but nothing printed is read, so the six VIZ/MRZ checks are `inconclusive` and coverage cannot clear 0.70. This is the correct behaviour and it is not a demoable clean pass. |
| 2 — the tamper | **No** | The premise is that a forger edits the *printed* date and the MRZ disagrees. Nothing reads the printed date, so `validation.vizmrz.dob_mismatch` is `inconclusive` — it no longer compares the signature against the MRZ and calls that a pass. No tier-1 tamper check fired on `retype` either, so the gate did not escalate and tier-2 forensics never ran (D6). |
| 3 — trust propagation | **Half**, unchanged | The signed Aadhaar verifies `AUTHENTIC` against `SIH-REF-01`, the disclosure string renders, and Layer D reaches the cross-document check — then reports `inconclusive` on the PAN's fields, which cannot be read. `gen_pan.png` carries no signature at all (`verification: None`). AMBER, coverage 0.250. |
| 4 — face and liveness | Not rehearsed | Needs a live camera and a person. The models load; `face.doc.detected` and `face.doc.quality` pass on all three documents. |
| 5 — the honest failure | **Yes, fully** | `gen_pan.png`: AMBER, coverage 0.250, every unread field named. `gen_aadhaar.png`: AMBER, coverage 0.49–0.52. This scene works end to end, and today it has more to say than it did yesterday. |

## Latency — measured, first time end to end

`python scripts/measure_latency.py`, on this machine: Intel, 16 logical cores,
Windows 11, onnxruntime 1.29 pinned to 4 intra-op threads
(`SCREENING_ORT_THREADS`). Generated documents, warm sessions. p95 rather than
mean, because a checkpoint queue is served by its slow tail.

| Document | n | p50 | p95 | reading path taken |
|---|---|---|---|---|
| passport | 30 | **1,352 ms** | **7,073 ms** | MRZ read and verified on 28/30; 2/30 fell to Florence-2 |
| aadhaar | 12 | **6,596 ms** | **7,924 ms** | Florence-2 on 12/12 |
| pan | 12 | **6,006 ms** | **6,355 ms** | Florence-2 on 12/12 |

The passport total is bimodal, not noisy: a document whose MRZ reads lands near
1.3 s, one that does not falls to Florence-2 and lands against its 8 s ceiling.
At n=30 the p95 sits exactly on those two runs, so treat 7,073 ms as "the tail
is the VLM ceiling" rather than as a stable third decimal place.

On the actual demo files, warm, five runs each: passport p50 1,386 ms, aadhaar
4,781 ms, pan 4,836 ms. The first document of a session costs roughly double
(2,769 / 6,673 / 6,031 ms) because Florence-2 is deliberately held out of
`warm()` and loads on the first document that needs it. **Screen one throwaway
Aadhaar before the panel walks in**, or the first document they see pays it.

Against `TECHNICAL-SPEC.md` §10, which budgets 1,020 ms for Tier 1 (passport,
n=30):

| Stage | budget | p50 | p95 | |
|---|---|---|---|---|
| decode | 60 ms | 7 ms | 13 ms | ok |
| extraction | 250 ms | 1,014 ms | 1,628 ms | **over** |
| validation | 15 ms | <1 ms | <1 ms | ok |
| tamper | 160 ms | 25 ms | 29 ms | ok |
| face | 320 ms | 5 ms | 6 ms | not a real number — see below |
| **Tier 1 total** | **1,020 ms** | **1,352 ms** | **7,073 ms** | **over** |

**It does not fit, on any document type, at p50 or at p95.** Four things belong
with that number rather than after it:

1. **This is a floor for the passport and a ceiling for the rest, not the
   shipping number.** With no detector the passport skips field detection and
   ~10 OCR crops entirely — 390 ms of budgeted work it is never charged for — so
   the real passport figure will come in *higher* than 1,352 ms. Aadhaar and PAN
   conversely spend nearly all their time in a fallback that should not run at
   all once fields are readable; their figure should collapse toward the budget.
2. **The extraction overrun is the untargeted MRZ read.** `read_mrz` is handed
   the bottom quarter of the page instead of a tight crop, which is the price of
   having no detector to aim with.
3. **The face number is meaningless as printed.** There was no live frame, so
   `face.live.detected` and `face.match.cosine` returned `inconclusive` without
   running a model. The 320 ms face budget is untested.
4. **The per-stage extraction row understates the VLM path.** The ratifier's
   signals carry no `latency_ms`, so on Aadhaar and PAN the stage table reports
   single-digit milliseconds while the end-to-end total says 6 s. Trust the
   end-to-end row on those two.

## Memory — measured, and the 500 MB claim does not survive

`python scripts/measure_memory.py`. Resident working set, one process, built in
the order the real one builds it. No new dependency: the script reads
`GetProcessMemoryInfo` on Windows and `/proc/self/status` in the image.

| State | steady | high-water |
|---|---|---|
| bare interpreter | 18 MB | — |
| + imports (onnxruntime, cv2, api) | 57 MB | 58 MB |
| `registry.warm()` — warm and idle | **154 MB** | 394 MB |
| warm and working, MRZ path (Florence-2 never loaded) | **185 MB** | **768 MB** |
| warm and working, Florence-2 resident | **1,556 MB** | **1,582 MB** |

DEMO.md answered "Why not use a GPU?" with "the whole system runs in under
500 MB warm". **That holds only for the idle process, and only until the first
document that cannot be read.** Florence-2 is four graphs held out of `warm()`
on purpose (`core/registry.py`), and today *every* Aadhaar and *every* PAN loads
it — after which the process sits at 1.5 GB and stays there for the life of the
process. Even on the clean MRZ path the high-water mark is 768 MB, and the
high-water mark is what a judge with Task Manager open is looking at.

The answer in the question table above has been corrected to match. The honest
version is still a good answer: 154 MB warm and idle, 185 MB screening a
document it can read, on a CPU, with no GPU anywhere in the process.

## What does work end to end

- **The cryptographic half.** A generated Aadhaar's QR decodes, its Ed25519
  signature verifies against the reference issuer in the trust anchor store, and
  the `disclosure` string renders so the verification cannot be mistaken for a
  government one (D1).
- **The arithmetic half on a passport.** Five ICAO check digits, Verhoeff on
  Aadhaar, date ordering, validity period, expiry, watchlist — all passing, all
  deterministic, not one of them a model output.
- **The coverage floor, on the documents it still governs.** Aadhaar and PAN are
  AMBER because of it. A system that cannot read a document says so.
- **The audit trail.** `GET /events` returns recorded screenings with their full
  signal lists and no raw identity number — checked, not assumed. `POST /rescore`
  and `POST /rescore/batch` re-score stored events without re-running a model.
- **The console.** `npm run verify` passes all four gates.

## What to say if asked on the day

> "The deterministic and cryptographic path is complete and you can see it
> working. The reading path is waiting on one model that trains on a GPU we
> don't have in the room — and we would rather show you what that costs than
> hide it. Without it a passport still clears our coverage floor on its
> signature and its machine-readable zone alone, including a passport whose
> printed fields we altered ourselves. That is the gap, we measured it, and it
> closes when the detector lands."

## What has to happen before this page can be rewritten

1. **Field detector weights into `models/`** (`MODEL-TRAINING.md`). Unblocks
   Scenes 1, 2 and the payoff of 3 — and closes the `retype` hole above, which
   is the first thing to re-test when they land.
2. **Re-run both measurement scripts.** Every number on this page moves when the
   detector lands: the passport gets slower, Aadhaar and PAN get much faster,
   and the memory ceiling drops as Florence-2 stops firing.
3. **Print and rescan the generated documents.** Everything above is a clean
   render; `context/DATA.md` is right that a model trained on clean renders
   falls apart on a scanner.
4. **Doc-vs-live calibration pairs**, for Scene 4 and for a face number that
   means anything.

---

<details>
<summary>Superseded — rehearsal record of 2026-09-07, kept for the record</summary>

### Rehearsal record — 2026-09-07

Driven through the real FastAPI app: real websocket, real lifespan, real fusion
engine, real generated documents. Not a mock of anything. What follows is what
actually happened, including the parts that did not work — DEMO.md's own Scene 5
argues that knowing your limits buys more credibility than any number, and that
applies to this page too.

**The one fact that shapes every line below:** `field_detector_22cls` is not
deployed. Training moved to an external GPU (`MODEL-TRAINING.md`). Without it
nothing reads a printed field, so coverage cannot clear the 0.70 floor and
**every verdict is AMBER "re-capture required"**. That is the safety property
working exactly as designed (D9) — but it means three of the five scenes cannot
be run as scripted today.

```
health: loaded  = face_detector, face_embedding, face_liveness, ocr
        missing = field_detector_22cls
```

| Scene | Runs today? | What actually happened |
|---|---|---|
| 1 — clean pass | **No** | AMBER, coverage 0.44. The signature verifies and two cryptographic passes render, but nothing printed can be read, so it cannot reach GREEN. |
| 2 — the tamper | **No** | `validation.vizmrz.dob_mismatch` is `inconclusive`. The highest-value tamper signal compares the *printed* date against the MRZ, and there is no printed date without the detector. No tier-1 tamper check caught the splice either; the gate did not escalate, so the tier-2 forensics never ran (D6). |
| 3 — trust propagation | **Half** | The signed Aadhaar verifies `AUTHENTIC`, the disclosure string renders, and Layer D reaches the cross-document check — then reports `inconclusive` on all three fields because the PAN's printed values could not be read. `GET /sessions` returns 2 documents and **0 propagation edges**, correctly: there is nothing proven to draw. |
| 4 — face and liveness | Not rehearsed | Needs a live camera and a person. The models load. |
| 5 — the honest failure | **Yes, fully** | AMBER, coverage 0.19, 16 named coverage gaps, each saying which field could not be read and why. This scene works end to end today. |

## What does work end to end

- **The cryptographic half.** A generated Aadhaar's QR decodes, its Ed25519
  signature verifies against the reference issuer in the trust anchor store, and
  the `disclosure` string renders so the verification cannot be mistaken for a
  government one (D1).
- **The coverage floor.** Every scene above is AMBER because of it. A system that
  cannot read a document says so instead of clearing it.
- **The audit trail.** `GET /events` returns 13 recorded screenings with their
  full signal lists. The response body carries no raw identity number —
  checked, not assumed. `POST /rescore` re-scores a stored event under different
  bands without re-running a model.
- **The console.** `npm run verify` passes all four gates: `tsc -b`, 31 vitest
  tests, the production build, and `check-offline.sh` — nothing in `dist/`
  fetches an external resource.

## What to say if asked on the day

> "The deterministic and cryptographic path is complete and you can see it
> working. The reading path is waiting on one model that trains on a GPU we
> don't have in the room. Until it lands the system refuses to clear anything,
> which is the behaviour we want from it — an unreadable document is not a
> cleared document."

## What has to happen before this page can be rewritten

1. Field detector weights into `models/` (`MODEL-TRAINING.md`). Unblocks Scenes 1, 2 and the payoff of 3.
2. Print and rescan the generated documents. Everything above is a clean render; `context/DATA.md` is right that a model trained on clean renders falls apart on a scanner.
3. Doc-vs-live calibration pairs, for Scene 4.


</details>
