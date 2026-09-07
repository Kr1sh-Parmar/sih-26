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
| Passive liveness | MiniFASNet V2, 2.7 / 80x80 | 1.7 MB | **7 ms** |

A full Tier 1 face pass — detect and embed both faces, plus passive liveness —
measures **p50 103 ms, p95 143 ms** against the 320 ms budget
(TECHNICAL-SPEC.md §2, L6). The three model calls are ~15 ms of that; the rest
is the fallback chain and the crops.

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

## Passive liveness — deployed 2026-09-07

Converted from the Silent-Face-Anti-Spoofing `.pth` by
`scripts/convert_liveness.py`, which runs under `.venv-train` because it needs
torch and torch must never enter the screening process. **Apache-2.0**, so the
weights redistribute with attribution; the sidecar carries the source, both
upstream hashes and the licence.

D30 said this was blocked on a licence read and a conversion. Both are done.

### The preprocessing was wrong, and silently

`modules/face/liveness.py` was written before the weights existed, so its input
contract was a guess. Both halves of the guess were wrong:

| | Guessed | Actual |
|---|---|---|
| Colour order | RGB | **BGR** |
| Input range | `/ 255.0` | **raw 0-255, not normalised** |

Upstream feeds `cv2.imread` output through *their own* `ToTensor`, which is not
torchvision's: it transposes HWC to CHW and calls `.float()`, with no channel
swap and no scaling.

Neither error raises. The network returns three plausible probabilities either
way — for an image it was never trained on. Measured on 60 faces, with the
division in place **every genuine face scored 0.006 live and the check rejected
100% of real people**. Without it, 0.968.

The export's own verification could not have caught this: it compared torch and
onnxruntime on a **black frame**, and zeros are invariant under scaling. The
reference is a deterministic ramp now, so it varies with the input range.

### Direction check against simulated attacks

`python scripts/eval_liveness.py --limit 120`. 120 SFHQ faces, each also
rendered as a simulated print and a simulated phone screen — tone compression,
halftone, paper grain and a paper edge for the print; RGB subpixel stripe,
moiré, glare and a bezel for the screen. MiniFASNet crops at 2.7x the face box
because the giveaways live in that margin, so the margin is where the artefacts
are drawn.

| Condition | n | median live probability | passes as live |
|---|---|---|---|
| genuine | 120 | **0.973** | 83.3% |
| simulated print | 120 | **0.001** | 1.7% |
| simulated screen | 120 | **0.001** | 3.3% |

At the configured `passive_pass: 0.60` — FRR 16.7%, FAR 2.5%.

**This is not a spoof-rejection rate and must not be quoted as one.** A
synthesised halftone is not a print and a synthesised moiré is not a phone
screen. What it establishes is that the model is wired correctly and separates
by three orders of magnitude; it is the test that caught the `/255`.

Two further caveats that both push the same way:

- **The "genuine" faces are synthetic.** SFHQ is StyleGAN output, not a camera
  capture. A liveness model may reasonably find generated faces odd, so the
  16.7% false rejection is probably pessimistic — and it is measured on the
  wrong domain either way.
- **The threshold was not re-fitted on this data** and should not be. Following
  D26, an operating point chosen against simulated attacks would measure the
  simulator. `passive_pass` stays at its configured 0.60 until real captures
  exist.

**Still owed, and it is the real test:** an actual printed photo and an actual
phone screen, on the demo camera, per MODULES.md.

## Also not done

- **Active liveness** (blink EAR) is not built. It needs a *sequence* of frames
  and the API accepts one live image, so the work is an API and console change
  rather than a face-module one. `face.liveness.active` reports that rather
  than a verdict. Cut-list item 2, and passive liveness — now deployed — is the
  one that covers the realistic threat at a manned counter.
- **Bias evaluation: UNMEASURED.** Not "small" — unmeasured. `scripts/eval_bias.py`
  is written and runs the moment either dataset is on disk, but FairFace ships
  its images through Google Drive and RFW requires signing a licence, so neither
  can be fetched unattended here.

  Worth knowing before anyone runs it: **FairFace has one image per person.** No
  identity labels means no genuine pairs, so it yields a false *match* rate by
  group and cannot produce false rejection at all. RFW carries identities and
  gives both halves. The harness does whichever the data supports and says which.

  NIST FRVT found demographic false-match differentials above an order of
  magnitude across algorithms. An unmeasured system is not a system without a
  disparity, and that sentence is the honest answer to the question.
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
| 2026-09-07 | Passive liveness converted from Apache-2.0 weights and deployed |
| 2026-09-07 | Liveness preprocessing corrected: BGR, and no `/255` — the guess had been rejecting 100% of genuine faces |
| 2026-09-07 | Export reference changed from a black frame to a ramp; zeros could not catch a scaling error |
| 2026-09-07 | 1:1 verified against generated documents: genuine median 0.866, impostor max 0.229 |
| 2026-09-07 | Bias harness written; disparity recorded as unmeasured |
