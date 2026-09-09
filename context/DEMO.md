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

# Rehearsal record — 2026-09-09

Supersedes the 2026-09-08 record, kept below. Driven through the real pipeline:
real `registry.warm()`, the real trust anchor store from `var/screening.db`,
real fusion, and the actual demo documents in `var/demo/`. Not a mock of
anything.

**What changed since yesterday:** `field_detector_22cls` is deployed. The one
fact that shaped every line of the last two records — that nothing read printed
ink on any document — is no longer true. A new fact shapes this one.

```
health: loaded  = field_detector_22cls, face_detector, face_embedding,
                  face_liveness, ocr
        missing = (nothing, for the first time)
tests:  381 passed, 5 skipped        (baseline 379 / 7)
front:  4/4 gates, 34 tests
```

## The fact that shapes this record

The detector reads the documents it was trained on and not the ones the demo
uses. Measured through the real screening path by `data/tools/eval_detector.py`:

```
data/processed/fields/test     recall 0.926     Roboflow document photographs
data/processed/generated/*     recall 0.142     the renders the demo runs on
```

There are zero generated cards in the training split. The full reasoning, the
per-type breakdown and why retraining was declined are in D51. The consequence
for this page is that **the pipeline now reads printed ink, but only two to four
fields per generated card**, so coverage lands between 0.47 and 0.73 and most
demo documents stay AMBER on the coverage floor.

That is the safety property working (D9) — nothing was read, so nothing
disagreed, and that is not a pass. It is also the reading path being judged on
the domain it is weakest in.

## Scene by scene, measured

| Scene | Scripted | Actual | Runs as written? |
|---|---|---|---|
| 1 — clean pass | GREEN passport | **AMBER** 0.094, coverage 0.619, 3,566 ms. All five ICAO check digits verify. | **No** — coverage floor |
| 2 — the tamper | RED on a retyped date | **AMBER** 0.019, coverage 0.511 | **No** — see below |
| 3 — trust propagation | Signed Aadhaar vouches for a PAN | **GREEN** 0.010, coverage **0.820**, 381 ms, three cryptographic findings | **Yes** |
| 4 — face and liveness | MATCH, then a print rejected | not run — needs the calibration set and a person | **No** — human-blocked |
| 5 — the honest failure | AMBER, re-capture required | **AMBER** 0.447, coverage 0.113, "Insufficient evidence - re-capture required" | **Yes** |

### Scene 3, driven through the console in a browser

The table above is the pipeline called directly. This is the same scene as an
officer performs it — upload on the capture screen, through the containers, to
the evidence list — which is the form it will actually be shown in:

```
aadhaar   SECONDARY   65% coverage   698 ms
          signature verifies; its own payload confirms the printed name and DOB
pan       CLEAR       83% coverage
          [cryptographic] signed Aadhaar payload name RACHITA KUMER matches this PAN card
          [cryptographic] signed Aadhaar payload father's name GAVIN KUMER matches this PAN card
          [cryptographic] signed Aadhaar payload date of birth 1960-03-24 matches this PAN card
          [arithmetic]    PAN format valid, fifth character matches the surname KUMER
session   2 documents, 3 propagation edges - name, dob, father_name, all "confirms"
```

The session view draws each edge as *signed payload → confirms → printed on the
card*, with the reference-issuer disclosure underneath. **Three defects stood
between the endpoint being reachable and this working**, all found by driving a
browser rather than calling the API — every capture minted a new session and
switched propagation off; the console's own quality gate refused documents the
backend accepts; and the viewer drew a passport specimen while screening an
Aadhaar. D57.

**Running order for the demo.** Capture screen → Aadhaar card → upload → *Screen
this aadhaar card* → *Capture another document* → PAN card → upload → *Screen
this pan card* → Session tab. Do **not** press "New traveller" between the two;
that is the control that ends a session, and the propagation is the point.

### Scene 3 is the one that got better, and it is the headline

Yesterday the propagation findings compared a signed payload against *another
payload*. Today they compare it against **ink actually read off the PAN card**:

```
[cryptographic] The signed Aadhaar card payload name RACHITA KUMER matches this PAN card
[cryptographic] The signed Aadhaar card payload father's name GAVIN KUMER matches this PAN card
[cryptographic] The signed Aadhaar card payload date of birth 1960-03-24 matches this PAN card
```

Coverage on the PAN went 0.725 → 0.820 and the verdict is GREEN. This is the
first rehearsal in which the headline scene proves what the script says it
proves. The contradiction half of the scene — a PAN whose printed date
disagrees with the signed Aadhaar, producing a hard fail — is exercised by
`tests/test_api.py::test_the_headline_scene_over_the_real_socket`; the two demo
files in `var/demo/` are the agreeing pair, so **prepare the contradicting PAN
before the panel, or the scene shows the "matches" path only.**

### Scene 1 does not go GREEN, and the reason is now specific

Coverage 0.619 against the 0.70 floor. The detector locates `issue_date`,
`name` and `nationality` on a generated passport and nothing else, so the other
declared text fields report "could not be located". The MRZ is read from its
fixed ICAO position and all five check digits verify — the arithmetic anchor the
scene's script leans on is genuinely there. What is missing is breadth of
coverage, not correctness.

### Scene 2 does not go RED, and this is worth understanding before the panel

`mutate.retype` alters printed text, but the detector does not locate `dob` on a
generated passport, so the printed date is never read and there is nothing to
disagree with the MRZ. The forgery is not *missed* — the document is AMBER, it
never clears, and the layout check fires — but it is caught as "this document
cannot be evaluated" rather than as "these two dates differ", and those are
different claims. **Do not narrate Scene 2 as a caught forgery on a generated
card.** The VIZ/MRZ comparison itself is sound and tested; it is the reading of
the printed date that is missing.

Checked across five mutation families on a passport, none clears:

```
untouched    AMBER 0.094 cov 0.619      retype       AMBER 0.019 cov 0.511
photo_swap   AMBER 0.017 cov 0.571      splice       AMBER 0.049 cov 0.516
copy_move    AMBER 0.085 cov 0.617      recompress   AMBER 0.039 cov 0.571
```

The D48 fix survives the reading path arriving, which was the thing most at risk
in this session: a forged passport did not become clearable when documents
became readable.

## The container, and the two real bugs it was hiding

**Correction first.** The previous record said Docker "was never built here".
That was wrong, and the way it was wrong is worth keeping: `docker images` shows
`sih-screening-api:latest` built on this machine 40 hours earlier. The claim had
been inferred from `docker` not being on `PATH`, which is a different fact, and
nobody ran `docker images` to check.

The image existed. **It had never been run**, and that is where the value was.

### `import cv2` failed inside the image

`docker compose --profile verify run --rm verify` — the compose profile that
runs the test suite inside the image with `network_mode: none` — had never been
executed. The first run of it collected 12 errors:

```
ImportError: libGL.so.1: cannot open shared object file
```

`requirements.txt` pins `opencv-python-headless` precisely so that no X stack is
needed. But **`rapidocr-onnxruntime` declares a dependency on plain
`opencv-python`**, so pip installed both; they ship the same `cv2` module, the
plain build landed last and won, and it wants `libGL.so.1`, which
`python:3.11-slim` does not carry.

So the image built cleanly, reported success, and could not import the library
every module in the screening path depends on. **The API could not have started
in that container.** Fixed in the Dockerfile by uninstalling both and
reinstalling headless — not by `apt-get install libgl1`, which would have worked
and would have contradicted the comment three lines above it. The build now ends
with an explicit `import cv2` so this can never pass silently again.

### A test file could not be collected without the build-time dependencies

The same run surfaced `NameError: name 'DOC_TYPES' is not defined`.
`tests/test_generator.py` imports `DOC_TYPES` under `if HAVE_DEPS:` but
parametrises with it in a decorator, and decorators are evaluated at *collection*
time regardless of `pytestmark`. In the image, where `requirements-build.txt` is
deliberately not installed, the file failed to collect and took eleven others
with it. It now falls back to `core.profiles.DOC_TYPES`, with a test asserting
the two lists agree so the fallback cannot drift.

Neither bug is reachable from the host, where both the build-time dependencies
and a working `libGL` are present. Both were sitting in the shipping artefact.

### Two more, from the same run

**`/screen/replay/{name}` could not work in the container.** `api/main.py:38`
reads the four rehearsed signal sets from `frontend/src/fixtures/` at *run*
time, and `.dockerignore` excluded `frontend/` wholesale. Every replay in the
image failed with a `FileNotFoundError` — and that is the endpoint the console's
demo scenes drive, and the backup path this page relies on when the camera
fails. 68 KB of JSON, now re-included by exception.

**24 failures, of which one was a real bug.** The rest were tests whose inputs
are deliberately absent from the image failing where they should have skipped,
and that ratio is its own problem: noise on that scale hides the finding that
matters. The guards are fixed. The root cause of *those* was subtle — the
generator imports Faker and Pillow inside its functions, to keep them out of the
screening path's import graph, so `from data.generator import build` succeeds in
the image and fails only when called. Every guard built on that import reported
the generator as available in the one environment where it is not.

### The fifth bug, and the worst: the container could not screen a document

With `up` finally running, the first real document posted to the container came
back as an **error frame**, not a verdict:

```
Screening failed: Object of type float32 is not JSON serializable
```

Every document the detector could actually read. None of the tests, because
every socket test screened a blank image — the detector finds nothing there, so
no signal carries a `region` and the wire form is trivially serialisable.

The cause is the one worth carrying into any claim about this project's testing:
`requirements.txt` pinned every dependency exactly **except numpy**, which was a
range. This machine resolved 1.26.4; the image resolved 2.4.6. NumPy 2 keeps
`float32` through a division by a Python float where 1.x widened to `float64`,
so detector coordinates reached the socket as `np.float32` and `json.dumps`
refused them.

**A version range meant the suite and the shipping artefact were running
different code**, and a green suite therefore proved nothing about the
container. numpy is pinned, the coordinates are cast at source, and
`test_every_event_from_a_real_document_survives_json` now screens a real PAN
over the real socket and asserts every event survives `json.dumps`. D56.

### What is closed

| | |
|---|---|
| Engine starts, CLI on PATH | **closed** — it was a PATH problem, not an install problem |
| `models/` reaches the image | **closed** — `.dockerignore` keeps it, `COPY . .` picks the detector up |
| `import cv2` in the image | **closed** — was broken, now asserted at build time |
| Fixture replay in the image | **closed** — was broken, fixtures now shipped |
| Suite runs inside the image, offline | **closed** — `--profile verify` exits **0** with `network_mode: none` |
| `docker compose up` + `GET /health` | **closed** — `missing: []`, every model loaded, detector reporting its real hash |
| Screening a real document in the container | **closed** — was broken, see above |
| Console image builds | **closed** |
| Dev and image run the same dependencies | **closed** — numpy was a range; now pinned |

`GET /health` from the running container, for the record:

```
loaded  = field_detector_22cls, face_detector, face_embedding, face_liveness, ocr
missing = []
field_detector = field_detector_22cls@d8baab1d46ae
trust_anchors = 1, watchlist = 8256
```

**Phase 5's clean-build gate is closed.** What remains is the physical rehearsal
— the cable-out run, three timed run-throughs, the backup laptop — which needs
the demo box and a person, not this machine.

### Two notes about this machine, not about the repository

**The network is intermittent**, and the Docker VM's DNS failed independently of
the host's. `~/.docker/daemon.json` now sets `"dns": ["8.8.8.8", "1.1.1.1"]`
with the original kept beside it as `daemon.json.bak`. The pip layer also got a
BuildKit cache mount and longer retries after a dropped read discarded a
nine-minute layer twice.

**The C: drive filled to 100%** (2.8 MB free) during the last rebuild, which
corrupted Docker's containerd content store — `input/output error` on every
write, surviving an engine restart, with 18 GB of build cache that could not be
pruned because the prune itself needs to write. That is what stopped `up` and
`/health`, and it is a workstation problem: free space on the host, then expect
to need a Docker Desktop **Clean / Purge data** before the daemon is healthy
again. Nothing in the repository is implicated.

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

**Re-measured 2026-09-09, with the detector deployed.** The 2026-09-08 column
is kept because it is the honest before: it was taken with the reading path
short-circuited, and it was a floor for the passport and a ceiling for the rest.

| Document | n | p50 | p95 | before (no detector) | reading path taken |
|---|---|---|---|---|---|
| passport | 30 | **2,251 ms** | **7,130 ms** | 1,352 / 7,073 | MRZ read and verified on 28/30; 2/30 fell to Florence-2 |
| aadhaar | 12 | **481 ms** | **555 ms** | 6,596 / 7,924 | detector + OCR on 12/12, no fallback |
| pan | 12 | **443 ms** | **478 ms** | 6,006 / 6,355 | detector + OCR on 12/12, no fallback |
| voter_id | 12 | **483 ms** | **509 ms** | — | detector + OCR on 12/12, no fallback |
| dl | 12 | **551 ms** | **5,708 ms** | — | 2/12 fell to Florence-2 |
| visa | 12 | **1,238 ms** | **1,306 ms** | — | MRZ read and verified on 11/12; 1/12 fell to Florence-2 |

**Three of six now fit the 1,020 ms budget at p95, and the two that were worst
before improved by more than an order of magnitude** — Aadhaar 6,596 → 481 ms,
PAN 6,006 → 443 ms. Both spent their whole budget in a fallback that no longer
runs, which is exactly what the detector was for.

**The passport p50 went up, and that is not a regression to hide.** With no
detector it skipped field detection and every OCR crop; it now pays for both,
and the MRZ band read it always did is still the dominant cost. The three that
remain over budget are over for two named reasons and no others:

- **passport and visa: the untargeted MRZ read**, ~740–950 ms of the p50. The
  detector proposes an `mrz` box on 70% of the passports in its own test split
  and on none of the generated renders, so the fixed-position band read - the
  bottom quarter of the page, full width - is what actually runs. Tightening
  that crop is the identified next optimisation and it is not attempted here,
  because the crop is what the read accuracy rests on and changing it without
  re-measuring the read would trade a latency number for a correctness one.
- **dl: the Florence-2 tail on 2 of 12 runs.** Down from 5 of 12 (D53).

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

| Stage | budget | passport p50 | passport p95 | aadhaar p50 | |
|---|---|---|---|---|---|
| decode | 60 ms | 8 ms | 10 ms | 13 ms | ok |
| extraction | 250 ms | 1,077 ms | 5,577 ms | 124 ms | **over on passport** |
| validation | 15 ms | <1 ms | <1 ms | <1 ms | ok |
| tamper | 160 ms | 28 ms | 35 ms | 26 ms | ok |
| face | 320 ms | 5 ms | 6 ms | 5 ms | not a real number — see below |
| **Tier 1 total** | **1,020 ms** | **2,251 ms** | **7,130 ms** | **481 ms** | passport over, aadhaar **ok** |

**Extraction is the whole story on every document type.** Aadhaar's 124 ms
against a 250 ms budget is the shape the design intended; the passport's
1,077 ms is the MRZ band read, and its 5,577 ms p95 is the two runs whose MRZ
did not verify and fell to Florence-2.

Two things belong with these numbers rather than after them:

1. **The face number is still meaningless as printed.** There was no live
   frame, so `face.live.detected` and `face.match.cosine` returned
   `inconclusive` without running a model. The 320 ms face budget remains
   untested, and it will not be tested until the doc-vs-live calibration set
   exists.
2. **These are clean generated renders.** A printed, scanned document is larger
   and slower. Re-run on the demo box with the documents that will actually be
   scanned before quoting any of it.
4. ~~**The per-stage extraction row understates the VLM path.**~~ **Fixed.**
   The ratifier starts the clock the caller hands it rather than one of its
   own, so `extraction.vlm.ratified` now reports the whole fallback. On
   `gen_pan.png` the extraction stage went from **4 ms to 6,051 ms**, which
   agrees with the end-to-end row instead of contradicting it by three orders
   of magnitude. Every per-stage table above the VLM path was previously wrong
   on exactly the documents that blow the budget.

## Memory — measured, and the 500 MB claim does not survive

`python scripts/measure_memory.py`. Resident working set, one process, built in
the order the real one builds it. No new dependency: the script reads
`GetProcessMemoryInfo` on Windows and `/proc/self/status` in the image.

Re-measured 2026-09-09 with the detector deployed. The detector adds 10 MB of
int8 graph to the warm set and costs 16 MB resident.

| State | steady | high-water |
|---|---|---|
| bare interpreter | 18 MB | — |
| + imports (onnxruntime, cv2, api) | 57 MB | 57 MB |
| `registry.warm()` — warm and idle | **170 MB** | 410 MB |
| warm and working, no fallback (Florence-2 never loaded) | **~190 MB** | 768 MB |
| warm and working, once Florence-2 has loaded | **1,428 MB** | **1,997 MB** |

**Memory is bimodal and the transition is one-way.** A process sits near
190 MB until the first document that falls through to the fallback; Florence-2
then loads, and because sessions are cached for the life of the process
(`core/registry.py`, deliberately — a cold session per request is worse) it
stays at ~1.43 GB from then on. That is why the aadhaar and pan rows of the raw
harness output also read 1,425 MB: they were screened *after* a passport in the
same process, not because they load the VLM themselves.

**What the detector changed here is which documents cross that line.** Before,
every Aadhaar and every PAN loaded Florence-2 — so the 1.5 GB state was the
normal one. Now Aadhaar, PAN and voter ID never load it at all, and the
passport, DL and visa do so only on the runs whose reading path fails: 2/30,
2/12 and 1/12 respectively. A shift that never hits a fallback stays under
200 MB.

DEMO.md answered "Why not use a GPU?" with "the whole system runs in under
500 MB warm". The corrected answer, which is still a good one: **170 MB warm
and idle, about 190 MB screening a document it can read, on a CPU, with no GPU
anywhere in the process** — and a documented 1.43 GB ceiling on the minority of
documents that need the fallback reader. The high-water mark is 1,997 MB and
that is what a judge with Task Manager open will see if they screen a passport
whose MRZ does not read.

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
