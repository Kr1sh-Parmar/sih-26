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

**Watch for:** the first verdict should appear at ~450 ms. Let the panel see it stream in.

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
| "Why not use a GPU?" | Border posts don't have one. Everything is ONNX int8 on CPU, and the whole system runs in under 500 MB warm. |
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
