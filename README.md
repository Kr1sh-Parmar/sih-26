# AI-Based Fake Identity & Document Screening System

**SIH Problem Statement:** 26188
**Organisation:** Ministry of Home Affairs
**Department:** Sashastra Seema Bal (SSB), Police II Division
**Category:** Software

---

## What this is

An offline, CPU-only document screening platform for border checkpoints. An officer places an identity document under a scanner and points a camera at the person holding it. In about one second the system returns a colour-coded verdict with a list of specific, checkable reasons.

It is not a fraud classifier. It is an **evidence engine** — it tells the officer *what is wrong and how confident that finding is*, and the officer decides.

## The one-sentence pitch

> We verify identity documents at three levels of certainty — cryptographic where a signature exists, arithmetic where a checksum exists, and probabilistic only where neither does — and we show the officer which level each verdict came from.

That distinction is the core design idea. A conventional system flattens a signature check and a texture heuristic into one confidence number. This one does not.

## Documents supported

| Document | Signature | Checksum | Deep tampering |
|---|---|---|---|
| Indian Passport | Reference issuer | **MRZ check digits (ICAO 9303)** | Full |
| Visa | Reference issuer | MRV MRZ digits where present | Partial |
| Aadhaar | Reference issuer | Verhoeff (12-digit) | Full |
| PAN | Reference issuer | Format + structural rules | Partial |
| Voter ID (EPIC) | Reference issuer | EPIC format | Partial |
| Driving Licence | Reference issuer | State + RTO code | Partial |

Plus **live face capture** for 1:1 verification and 1:N duplicate-identity search.

## Four modules plus fusion

| Module | Does |
|---|---|
| 1 — Extraction | Locate and read every field; parse MRZ and QR |
| 2 — Validation | Six layers of checks, from cryptographic to behavioural |
| 3 — Tampering | Two tracks: physical artifact forensics and digital file forensics |
| 4 — Face | 1:1 doc-to-live verification, liveness, 1:N duplicate search |
| Fusion | Group correlated signals into findings, score by trust class, produce evidence cards |

## Hard constraints

- **CPU only.** No GPU anywhere in the system.
- **Fully offline.** No network call at inspection time. Verified by pulling the cable.
- **No UIDAI.** No government API, certificate, database, or key. All signing is our own reference issuer.
- **All data synthetic.** No real government identity documents in any dataset, repo, or demo. Only real biometric is team faces for threshold calibration, with consent.
- **Human in the loop.** The system assists; it never decides.

## Performance targets

| Metric | Target |
|---|---|
| Tier 1 (every document) | < 1.0 s |
| First verdict on screen | ~450 ms (WebSocket streaming) |
| Escalated path | < 2.5 s total |
| Warm model footprint | < 500 MB |
| Hardware floor | 8-core CPU, 8 GB RAM, no GPU |

## Documentation map

| File | Purpose |
|---|---|
| `README.md` | This file — project identity |
| `CLAUDE.md` | Instructions for Claude Code. Read first when coding. |
| `context/CONTEXT.md` | Problem domain, SSB operating reality, non-goals |
| `context/TECHNICAL-SPEC.md` | Full architecture, models, schemas, latency budget |
| `context/CONTRACTS.md` | **Frozen interfaces.** Change requires team agreement. |
| `context/ROADMAP.md` | Phase-wise plan, owners, cut list |
| `context/MODULES.md` | Per-module briefs with acceptance criteria |
| `context/DATA.md` | Datasets, synthetic generation, licensing |
| `context/DECISIONS.md` | Why things are the way they are |
| `context/DEMO.md` | Demo script and rehearsal checklist |

## Quick start

```bash
pip install -r requirements.txt
python -m issuer.cli init                        # reference keypair -> trust anchor store
python data/tools/load_watchlist.py --seed-demo  # OFAC + UN into the local table
python -m uvicorn api.main:app                   # http://localhost:8000
cd frontend && npm install && npm run dev        # http://localhost:5173
```

`pytest` should pass from a clean checkout. On Debian-based images the QR
decoder needs `apt-get install -y libzbar0`.

Nothing above touches the network at inspection time, and no model is
downloaded at runtime.

### What is built so far

The deterministic spine: contracts, profiles, fusion, the risk gate, the
FastAPI + WebSocket server, the Ed25519 reference issuer, and validation
layers A to F. Everything that needs no trained model.

The learned modules - field detector, OCR, face, both tamper tracks - are
signature-correct stubs that return `inconclusive`. That is deliberate and it
is why an unsigned document screens AMBER today: coverage, not evidence, is
what is missing, and the system says so rather than clearing it.

```bash
python -m issuer.cli mint var/demo/aadhaar.json  # sign a payload, write its QR
python scripts/demo_scene3.py                    # Scene 3 against a running server
```
