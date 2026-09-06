# Getting Started

For a developer joining the project, and for the Week 0 scaffold.

---

## Read in this order

1. `README.md` — what the project is (5 min)
2. `CLAUDE.md` — the hard rules (5 min)
3. `docs/CONTRACTS.md` — **the frozen interfaces you must build against** (15 min)
4. `docs/MODULES.md` — find your module's brief (10 min)
5. `docs/TECHNICAL-SPEC.md` — reference, read as needed

`docs/DECISIONS.md` answers "why is this weird thing like this."

---

## Environment

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d db minio
pytest                        # should pass against fixtures from day 0
uvicorn api.main:app --reload
```

Frontend:
```bash
cd ui && npm install && npm run dev
```

**Python 3.11.** ONNX Runtime CPU build. No `onnxruntime-gpu`, no `torch` with CUDA extras.

---

## Week 0 build order

The point of Week 0 is that weeks 1–8 can run in parallel. Nobody writes module logic yet.

### 1. Contracts (integration owner, day 1)

```
fusion/signal.py       Signal, Verdict, TrustClass
fusion/context.py      ScreeningContext, NormalizedField
fusion/finding.py      Finding
```

Copy them verbatim from `CONTRACTS.md`. Mark with a module docstring:

```python
"""FROZEN CONTRACT. See docs/CONTRACTS.md.
Changes require agreement from the integration owner and must update
docs/CONTRACTS.md and every implementation in the same commit."""
```

### 2. Profile loader and config (integration owner, day 1)

```
profiles/passport.yaml  visa.yaml  aadhaar.yaml  pan.yaml  voter_id.yaml  dl.yaml
config/reliability.yaml  thresholds.yaml  bands.yaml
core/profiles.py        loader + schema validation
```

Six profiles as stubs is fine. The schema must be final.

### 3. Fake signal fixtures (integration owner, day 2)

```
tests/fixtures/signals_green.json
tests/fixtures/signals_amber_coverage.json
tests/fixtures/signals_red_hardfail.json
tests/fixtures/signals_crossdoc_mismatch.json
```

Hand-write these. They are the contract made concrete, and they are how the UI gets built before any model exists.

### 4. Fusion against fixtures (integration owner, day 2–3)

```
fusion/findings.py     anchor binding, noisy-OR
fusion/score.py        hard fail, coverage, crypto precedence, weighted sum
fusion/evidence.py     card assembly and ordering
```

Property tests first:
- hard fail always returns RED regardless of score
- coverage below floor never returns GREEN
- crypto pass suppresses probabilistic findings on signed fields
- four correlated signals on one anchor produce one finding

### 5. API + WebSocket stub (integration owner, day 3)

```
api/main.py        POST /screen  -> session id
api/websocket.py   WS /screen/{id} -> streams signals then verdict
api/router.py      profile selection by doc_type
```

Streams the fixture signals with artificial delays matching the latency budget. The UI cannot tell the difference from the real thing.

### 6. Console against the stub (integration owner + anyone free, day 3–5)

Evidence cards, document view, face pair, FAR/FRR control. All fake data. Build the hard UI while the backend is still empty.

### 7. Module skeletons (everyone, day 4–5)

Each module owner creates their package with signature-correct stubs:

```python
def run(ctx: ScreeningContext) -> list[Signal]:
    """TODO. Returns [] for now."""
    return []
```

Wire them into the orchestrator behind a feature flag so real modules replace fixtures one at a time.

### 8. In parallel, day 1 (do not defer)

- [ ] **Schedule the face calibration capture session.** Book people. This has weeks of lead time.
- [ ] Start MIDV-2020 downloading (it is large)
- [ ] Create the Roboflow workspace and invite the team
- [ ] Start the first template vectorisation (passport)

---

## Week 0 exit gate

```bash
docker compose up
open http://localhost:5173
# load a fixture -> see evidence cards, verdict, timing
```

All fake. But every person now has a fixed target and can work without blocking anyone else.

---

## Your first real task, by role

**Extraction:** implement the MRZ parser. Pure function, no models, testable against ICAO 9303 published examples. It is the highest-value component in the system and needs nothing but a string.

**Validation:** implement Verhoeff, then the PAN structural rules. Twenty lines each, fully testable, and they are your Layer A backbone. The two are not equivalent: Aadhaar has a real, published check digit; PAN has published composition rules and nothing more. See `DECISIONS.md` D23 before you describe either one out loud.

**Tampering:** vectorise the passport template. Slow, unglamorous, blocks everything downstream in Module 3.

**Face:** book the calibration session, then wire InsightFace with a single detection pass and verify the embedding shape is 512.

**Integration:** the fixtures. Everything else depends on them.

---

## Definition of done for any PR

- [ ] Returns `list[Signal]`, nothing else
- [ ] Signal IDs registered in `CONTRACTS.md`
- [ ] `evidence` strings readable by a non-technical officer
- [ ] `latency_ms` populated
- [ ] `inconclusive` and `not_applicable` distinguished correctly
- [ ] Unit tests with a hand-built context, no on-disk fixtures for pure functions
- [ ] No network call, no GPU, no real document, no raw ID number
- [ ] `docker compose up` still works from clean

---

## If you are blocked

| Blocked on | Do this instead |
|---|---|
| A model that isn't trained yet | Stub it, return `inconclusive` signals, keep building the surrounding logic |
| The calibration set | Use a placeholder threshold with a loud `TODO`, but do not merge it to main |
| A contract that doesn't fit your case | Raise it. Do not edit the contract. |
| A dataset that turns out to be junk | Check `docs/DATA.md` §Verified problems first — it may already be documented |
| Not knowing whether something is allowed | `CLAUDE.md` hard rules. If still unclear, ask rather than assume. |
