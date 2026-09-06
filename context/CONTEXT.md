# Project Context

Background reading. If you are writing code, read `CLAUDE.md` and `CONTRACTS.md` first — this file explains *why*, not *what*.

---

## 1. The problem as stated

Border checkpoints process thousands of identity documents daily. Manual verification is slow, inconsistent between officers, and cannot reliably catch sophisticated forgery.

Threats named in PS 26188:

- Fake passports and visas
- Altered photographs
- Modified dates of birth
- Tampered visa stamps
- Identity impersonation
- Multiple identities used by the same person
- Expired or blacklisted travel documents
- High passenger volume causing delays

## 2. Who actually uses this

Sashastra Seema Bal guards the **India–Nepal (1,751 km)** and **India–Bhutan (699 km)** borders. Both are open borders — under the respective friendship treaties, Nepali and Bhutanese citizens do not need a passport or visa to enter India.

This changes the document mix materially. The officer at Raxaul or Sunauli is far more likely to be looking at an Aadhaar card or a Nepali citizenship certificate than a third-country passport with a visa in it.

**Design consequence:** we build the ICAO passport pipeline because it demonstrates standards rigour and because the MRZ is our strongest real anchor. But the demo narrative is about Indian domestic documents, because that is what SSB inspects.

**Note for the pitch:** verify the current border arrangement before putting it on a slide. Treaty arrangements change.

## 3. The operating environment

| Reality | Design consequence |
|---|---|
| Border posts have unreliable or no internet | Fully offline. Zero network calls at inspection. |
| No GPUs on checkpoint hardware | CPU-only. Every model ONNX int8. |
| Officer has seconds, not minutes, per traveller | Sub-second Tier 1, streamed results |
| Officer must justify a detention | Evidence list, not a score |
| Passenger volume is high | False rejections are expensive — 2% FRR at 5,000/day is 100 secondary inspections |
| Decisions get challenged months later | Full audit trail, re-scorable from stored signals |

## 4. What we can and cannot access

**Cannot access — and the architecture does not depend on any of it:**

- UIDAI APIs, certificates, keys, or databases
- Aadhaar authentication or eKYC
- Interpol SLTD
- Passport Seva / MEA databases
- Any government verification endpoint
- ePassport NFC chips (no reader hardware)

**Can access, and do use:**

- **ICAO Doc 9303** — free public PDF. MRZ layout and check-digit algorithm. This is our one genuine external standard and it needs nobody's permission.
- **PRADO** (EU Council register of authentic documents) — published specimen images
- **OFAC SDN** and **UN Consolidated List** — real, free, downloadable sanctions lists with realistic name-matching problems
- **ISO 3166-1** country codes
- Public research datasets (MIDV, SIDTD, CelebA-Spoof, etc. — see `DATA.md`)
- Roboflow Universe for annotation and training (build-time only, never runtime)

## 5. The reference issuer, and why it exists

Four of six Indian identity documents — PAN, Voter ID, Driving Licence, and in our build Aadhaar too — carry **no cryptographic integrity whatsoever**. A verifier has no technical means to confirm the document is genuine; they have to trust the producer.

That is a real national gap, not a limitation of this project.

So we built a **reference issuance authority**: an offline tool that canonicalises document data, hashes it, signs it with Ed25519, and encodes the signature into a QR. The screening system verifies against public keys held in a local trust anchor store.

**How to frame this honestly:**

> "Most Indian identity documents have no cryptographic integrity today. We built a reference issuer to demonstrate signed verification end to end, and validated our verification path against the one real public standard available to us — ICAO 9303 machine-readable zones. Where genuine signatures exist in production, the trust anchor store takes a different key and the verification code is unchanged."

**How not to frame it:** do not imply our signatures are government signatures. The officer console must label reference-issued verifications distinctly from arithmetic ones. This is in the profile schema as the `disclosure` field.

**Architecturally:** the reference issuer sits outside the screening path entirely. It deposits public keys into the trust anchor store during setup and is never called at inspection time — exactly how a real issuing authority relates to a checkpoint.

## 6. The three trust classes

Everything in this system carries one of three labels. It determines how much weight a signal gets and how it is presented to the officer.

| Class | Meaning | Examples |
|---|---|---|
| **Cryptographic** | Mathematically certain given a trusted key | Ed25519 signature over canonical payload |
| **Arithmetic** | Deterministic, no ML, no key needed | MRZ check digits, Verhoeff, PAN check character, date logic |
| **Probabilistic** | Inference. Can be wrong. | Tamper heuristics, face match, OCR confidence |

**Precedence rule:** when a cryptographic signal passes, probabilistic signals disputing the *signed fields* are suppressed. An ELA hotspot over a signed date of birth is a false positive, and fusion knows it.

## 7. Non-goals

Things we deliberately do not do:

- **We are not an issuing authority.** No document creation in the screening product.
- **We do not store traveller PII.** Screening events reference a document hash, not a person record.
- **We do not decide.** GREEN/AMBER/RED is a recommendation with reasons.
- **We do not claim to detect professional forgery.** Our test set is synthetic. We say so.
- **We do not do biometric identification against a national database.** 1:N is against our own prior screening events only.

## 8. Known limitations to state before a judge does

Saying these first is worth more than a higher accuracy number.

1. **Our forgery test set is synthetic.** We report accuracy on it and label it as such. We have not tested against professionally produced forgeries because those are not obtainable.
2. **Physical-track tampering detection is template-dependent.** Implemented fully for passport and Aadhaar only; the other four get partial coverage.
3. **ELA is a weak signal.** It is a useful officer-facing visualisation but any global recompression flattens it. Weighted accordingly.
4. **Metadata forensics only fires on uploaded files.** At a live counter the scanner writes the file, so EXIF is always clean by construction.
5. **Face recognition has documented demographic accuracy disparities** (see NIST FRVT). We measure ours on FairFace/RFW and report the gap.
6. **Our signatures are ours.** See section 5.

## 9. Glossary

| Term | Meaning |
|---|---|
| **MRZ** | Machine Readable Zone — two 44-char lines on a passport, with five check digits |
| **VIZ** | Visual Inspection Zone — the human-readable printed fields |
| **VIZ↔MRZ mismatch** | Our highest-value tamper signal. Forgers edit one and forget the other. |
| **Trust class** | cryptographic / arithmetic / probabilistic |
| **Signal** | One atomic check result. The only thing crossing module boundaries. |
| **Finding** | A group of correlated signals about one anchor (a field or region) |
| **Anchor** | What a signal is *about*: `field:dob`, `region:photo`, `document` |
| **Risk gate** | The single branch point: clear, escalate, or hard fail |
| **Hard fail** | A condition that bypasses scoring entirely and returns RED |
| **Coverage** | Fraction of applicable checks that actually executed. Low coverage forces AMBER. |
| **Guilloche** | Fine security background pattern; must be continuous under text |
| **Ghost portrait** | Faint secondary photo, a standard security feature |
| **OCR-B** | The font the MRZ is printed in. Deviation is a tamper signal. |
