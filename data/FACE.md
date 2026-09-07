# Face verification — measured record

What Module 4 does, what it is worth, and the one number that is still missing.

Models are fetched at build time by `scripts/fetch_face_models.py`; nothing is
downloaded at inspection time.

---

## What is deployed

| | Model | Size | Latency (CPU) |
|---|---|---|---|
| Detection | SCRFD `det_500m` (insightface `buffalo_sc`) | 2.5 MB | **4 ms** |
| Embedding | ArcFace `w600k_mbf`, 512-d | 13.6 MB | **4 ms** |
| Passive liveness | MiniFASNet | — | **not deployed** |

Two faces plus margin is about **15 ms of the 320 ms** Tier 1 budget
(TECHNICAL-SPEC.md §2, L6).

### Why `buffalo_sc` and not `buffalo_l`

TECHNICAL-SPEC §4 budgets `buffalo_l` at 160 ms per face. Two faces is 320 ms —
the entire Tier 1 face budget, before liveness runs. `buffalo_sc` is the same
pipeline at 16 MB against 289 MB and lands twenty times inside the budget.

It is a real accuracy trade and it is written down rather than hidden. `python
scripts/fetch_face_models.py --pack buffalo_l` measures the other side of it. On
the separation below there is no headroom being bought: the mbf recogniser
already separates by a factor of forty.

### Why not the `insightface` package

`FaceAnalysis` downloads its own weights on first use, into a home directory, at
whatever moment the first traveller arrives — the runtime network call CLAUDE.md
rule 3 forbids, and invisible in a demo until the cable comes out. So the two
ONNX files are taken out of the pack and run on the ONNX Runtime session already
in the process. Cost: about a hundred lines of SCRFD decode and a five-point
alignment.

---

## Separation, 2026-09-07

40 synthetic identities (SFHQ, CC0, no real person). Each rendered onto a card
and compared against its own source frame.

| | |
|---|---|
| Genuine pairs | 40 — median **0.890**, minimum 0.757 |
| Impostor pairs | 1,560 — median **0.019**, maximum 0.291 |
| At threshold 0.32 | FRR 0.0%, FAR 0.000% |

**This is not the number that matters.** It says the pipeline is wired
correctly — a broken alignment still produces plausible embeddings, it just
moves genuine pairs apart faster than impostor pairs, which looks like a
threshold problem rather than a bug. Clean separation by a factor of forty means
the similarity transform and the reference landmarks are right.

It says nothing useful about a border checkpoint. Both halves of every pair here
are clean synthetic renders. A real document photo is printed, halftone
screened, overprinted with a security pattern, sub-300 dpi once scanned, and up
to ten years old.

---

## The threshold is not calibrated, and the system says so

`config/thresholds.yaml` carries `threshold: 0.32` with `calibrated: false`, and
**every face signal repeats that in the sentence the officer reads**:

> Document and live face match at cosine 0.51, against a 0.32 threshold, 0.19
> above it. That threshold is not yet calibrated on document-to-live pairs, so
> treat the margin as indicative

Published buffalo operating points are live-to-live. The genuine doc-vs-live
distribution is shifted down against them and the impostor distribution is not,
so an LFW threshold rejects real travellers — wrong in the direction that causes
queues and teaches an officer to override the machine (D11).

`data/tools/calibrate_face.py` is written and ships unused. It wants ≥500
genuine pairs from ≥30 people, prints the full FAR/FRR curve, and **refuses
`--apply` on a smaller set** rather than letting `calibrated: true` become a
claim nobody measured.

---

## Two bugs this module surfaced

**No profile gave `face.*` any weight.** Only `face.match.cosine` had a pattern,
so `face.doc.detected`, `face.live.quality`, `face.liveness.passive` and
`face.gallery.duplicate` all resolved to weight 0.0 — rendered as evidence,
invisible to both coverage and the score. A liveness check correctly rejecting a
printed photo held to the camera would have scored exactly zero. That is Scene 4
of the demo. `face.*: 0.10` is now in all six profiles, and a test asserts it.

**`confidence` was carrying the score, not the certainty.** The risk gate read
it as a cosine to test the review band; fusion's noisy-OR reads it as certainty.
Both cannot be true, and the consequence ran the wrong way: a *confident*
impostor — cosine 0.10 against a 0.32 threshold — arrived at fusion as
confidence 0.10 and moved the score by 0.001. Measured end to end, a genuine
pair scored 0.130 and an impostor 0.129.

`confidence` is certainty now, as the contract always said, scaled so that
anything inside the configured review band comes out below 1.0 — an exact
translation of the band test, which the gate now expresses as "escalate when the
check is not sure". The same pair now scores 0.130 and **0.274**.

It is the D10 failure one layer down: a scale that reads plausibly and is wrong
in the direction that admits fraudsters.

---

## Not deployed: passive liveness

MiniFASNet ships from Silent-Face-Anti-Spoofing as PyTorch `.pth`. The ONNX
mirrors found need an account; converting the `.pth` needs torch — which lives
only in `.venv-train` and must never enter the screening process — plus the
model class from that repository, whose licence needs reading before it goes in
a submission. That is a decision, not an afternoon.

Everything except the weights is written. `modules/face/liveness.py` carries the
full inference path, `core/registry.py` already warms `face_liveness` and already
reports it in the audit log; dropping `models/face_liveness.onnx` and its sidecar
in place starts it returning verdicts with no other change.

Until then the signal is **`inconclusive`, and costs coverage**:

> Whether the person at the camera is live was not checked — the passive
> liveness model is not deployed. Confirm visually.

A spoof check that has not run must never look like one that passed. At a manned
counter the officer is the liveness check, and the console has to say the machine
is not helping with this one.

**Scene 4 of the demo cannot be run as written** until those weights land.

---

## Also not done

- **Active liveness** (blink EAR) needs a frame sequence the API does not carry;
  it reports that rather than a verdict. Cut-list item 2.
- **Bias evaluation** on FairFace / RFW. Phase 3, and a compliance item rather
  than a nice-to-have — NIST FRVT demographic disparities are real and the gap
  has to be reported, not discovered by a panel.
- **Spoof testing** against an actual printed photo and an actual phone screen.
  Blocked on liveness weights. Untested liveness is theatre.
- **1:N gallery at scale.** It works and is tested, but `store.search_faces` is
  an O(n) scan — fine at demo scale, and it carries its own note about when that
  stops being true.

---

## Log

| Date | Event |
|---|---|
| 2026-09-07 | `buffalo_sc` fetched; SCRFD decode and ArcFace alignment written against the raw ONNX |
| 2026-09-07 | 40-identity separation measured: genuine 0.890 median, impostor 0.019 |
| 2026-09-07 | `face.*` weight gap found and fixed in all six profiles |
| 2026-09-07 | `confidence` corrected from score to certainty; gate updated to match |
| 2026-09-07 | Face-crop sharpness made scale-invariant — the raw Laplacian variance penalised close-up captures |
