# Frozen Contracts

**These interfaces are frozen.** Every module depends on them. Changing one breaks four people's work simultaneously.

Change process: raise it, get agreement from the integration owner, update this file *and* every implementation in the same commit. Do not change a contract to make one module's life easier.

---

## 1. `Signal` — the only thing that crosses module boundaries

```python
from dataclasses import dataclass
from typing import Literal, Optional

Verdict    = Literal["pass", "fail", "inconclusive", "not_applicable"]
TrustClass = Literal["cryptographic", "arithmetic", "probabilistic", "unverified"]

@dataclass(frozen=True)
class Signal:
    id: str                 # dotted, stable: "mrz.checkdigit.dob"
    module: str             # extraction | validation | tamper | face
    tier: int               # 1 = always runs, 2 = escalated only
    verdict: Verdict
    confidence: float       # 0.0-1.0. For deterministic checks use 1.0.
    trust_class: TrustClass
    hard_fail: bool         # True bypasses scoring entirely -> RED
    anchor: str             # "field:dob" | "region:x1,y1,x2,y2" | "document"
    evidence: str           # one line, shown verbatim to the officer
    region: Optional[tuple] = None   # (x1,y1,x2,y2) for UI overlay
    latency_ms: int = 0
```

### Rules

- Every module returns `list[Signal]`. Nothing else.
- No module imports another module's internals.
- `weight` is **not** on the Signal — it comes from the document profile at fusion time. Signals do not know their own importance.
- `evidence` must be readable by a border officer with no ML background. Good: `MRZ date of birth 1991-03-04 does not match printed 1991-08-04`. Bad: `viz_mrz_dob_mismatch=True`.
- `not_applicable` ≠ `inconclusive`. Aadhaar has no MRZ (`not_applicable`, excluded from coverage). A blurred MRZ that could not be read is `inconclusive` (counts against coverage).
- `unverified` trust class is reserved for VLM output with no checksum available. It can never contribute to a GREEN verdict alone.

### Signal ID namespace

Register new IDs here. They are stable strings used in weights, tests, and audit logs.

```
extraction.quality.blur              extraction.quality.resolution
extraction.quality.brightness
extraction.doctype.confidence        extraction.field.<name>.confidence
extraction.ocr.<field>.confidence    extraction.vlm.ratified
extraction.vlm.unratified

validation.signature.valid           validation.signature.issuer_trusted
validation.mrz.checkdigit.<field>    validation.mrz.checkdigit.composite
validation.verhoeff.aadhaar          validation.format.<doctype>.<field>
validation.crossfield.date_order     validation.crossfield.validity_period
validation.crossdoc.name_mismatch    validation.crossdoc.dob_mismatch
validation.signed.<field>_mismatch
validation.vizmrz.<field>_mismatch   validation.expiry.expired
validation.watchlist.hit             validation.history.impossible_transit

tamper.physical.ocrb_conformance     tamper.physical.guilloche_break
tamper.physical.ghost_missing        tamper.physical.layout_geometry
tamper.physical.halftone
tamper.stamp.duplicate               tamper.stamp.date_logic
tamper.stamp.count_mismatch
tamper.digital.ela                   tamper.digital.double_jpeg
tamper.digital.exif_software         tamper.digital.copy_move
tamper.digital.noise_residual

face.doc.detected                    face.doc.quality
face.live.detected                   face.live.quality
face.live.quality.blur               face.live.quality.resolution
face.live.quality.brightness
face.liveness.passive                face.liveness.active
face.match.cosine                    face.gallery.duplicate
```

`face.live.quality.{blur,resolution,brightness}` are the live-capture half of
`core/quality.py`, which builds them by f-string. The registry check in
`tests/test_contracts.py` skips f-strings, so they were emitted unregistered
until the face module landed. Registered now: an id an audit log can carry has
to be in this list whether or not the guard can see it.

### One check, one id

**No two checks may share a signal id, and no screening may emit an id twice.**
An id is the key a re-scoring reads years later, the key `reliability()` looks a
weight up under, and the key a profile names in `weights` and `hard_fail`.
Sharing one breaks all three quietly: the audit log cannot say which check
produced a verdict, the softer check borrows the harder one's weight, and both
land in the same anchor group so **both count against coverage** - the
correlated-signal double count D8 exists to prevent, committed inside one
pipeline instead of across two.

Two instances existed and are now guarded by `tests/test_signal_identity.py`.
`core/quality.py` filed brightness under the blur id, and under
`face.live.quality` - the face-crop gate's id - on the live path.
`modules/extraction/qr.py` emitted `validation.signature.valid` for a condition
Layer A already reported, so on a passport, where it is weighted 0.25, a missing
signature cost coverage twice. Neither looked wrong; both were one line.

A templated family - `extraction.field.<name>.confidence`,
`validation.mrz.checkdigit.<field>` - is fine, because the field name is in the
id and each instance is still unique.

---

## 2. `ScreeningContext` — shared state, passed by reference

```python
from dataclasses import dataclass, field
import numpy as np

@dataclass
class ScreeningContext:
    session_id: str
    image: np.ndarray                  # decoded ONCE. Never re-read from disk.
    doc_type: str                      # from the type classifier
    profile: dict                      # loaded YAML for this doc_type
    quad: np.ndarray | None = None     # 4x2 document corners
    warped: np.ndarray | None = None   # perspective-corrected image
    field_boxes: dict = field(default_factory=dict)   # {class_name: (x1,y1,x2,y2)}
    fields: dict = field(default_factory=dict)        # {field_name: NormalizedField}
    faces: dict = field(default_factory=dict)         # {'doc': ndarray, 'live': ndarray}
    embeddings: dict = field(default_factory=dict)    # {'doc': 512d, 'live': 512d}
    signals: list = field(default_factory=list)       # list[Signal]
    prior_docs: list = field(default_factory=list)    # other docs in this session
```

### Rules

- **Decode once.** The orchestrator builds `image`; nothing else opens a file.
- Modules read from context and append to `ctx.signals`. They never return images.
- `prior_docs` enables trust propagation: a signed Aadhaar in the same session validates an unsigned PAN's name and DOB.
- Never put a model object on the context. Models live in the registry, loaded once at startup.

```python
@dataclass
class NormalizedField:
    raw: str            # exactly what OCR returned
    value: str          # normalized (dates ISO-8601, names uppercase transliterated)
    source: str         # "ocr" | "mrz" | "qr" | "vlm"
    confidence: float
    box: tuple | None
```

---

## 3. `Finding` — produced by fusion, consumed by the console

```python
@dataclass
class Finding:
    anchor: str
    severity: float           # 0-1, noisy-OR over the group
    trust_class: TrustClass   # strongest class among members
    headline: str             # what the officer reads
    supporting: list          # list[Signal], collapsed by default in UI
    region: tuple | None
```

Signals are grouped into findings by `anchor`. Region-anchored signals resolve to a field anchor by IoU against `ctx.field_boxes`.

Severity within a group uses noisy-OR, not a sum:

```python
def group_severity(signals: list[Signal]) -> float:
    p = 1.0
    for s in signals:
        p *= (1 - s.confidence * RELIABILITY[s.id])
    return 1 - p
```

`RELIABILITY` lives in `config/reliability.yaml` and encodes how much each technique is actually worth. Indicative values:

```yaml
validation.signature.valid:        1.00
validation.mrz.checkdigit.composite: 1.00
validation.verhoeff.aadhaar:       1.00
validation.vizmrz.dob_mismatch:    0.90
validation.crossdoc.dob_mismatch:  0.90
tamper.digital.copy_move:          0.70
tamper.physical.ocrb_conformance:  0.65
tamper.digital.noise_residual:     0.50
tamper.physical.guilloche_break:   0.45
tamper.digital.ela:                0.30
```

---

## 4. Document profile schema

One YAML per document type in `profiles/`.

```yaml
doc_type: passport

extract:
  detector_classes: [mrz, person_photo, ghost_photo, name, dob, gender,
                     nationality, id_number, issue_date, expiry_date,
                     issuing_authority, signature]
  forbidden_classes: []          # presence of these is itself a signal
  ocr_lang: [en]
  mrz: { format: TD3, lines: 2, length: 44 }

verify:
  signature: reference_issuer     # or 'none'
  arithmetic: [mrz_checkdigits, date_order, validity_period]
  cross_document: [name, dob]     # fields usable for trust propagation

tamper:
  track: full                     # full | partial
  checks: [ocrb_conformance, guilloche, ghost_portrait, layout_geometry,
           stamp_duplicate, stamp_date_logic]

face:
  source_class: person_photo
  threshold_set: doc_live         # key into config/thresholds.yaml

hard_fail:
  - validation.mrz.checkdigit.composite
  - validation.expiry.expired
  - validation.watchlist.hit
  - validation.signature.valid          # when signature declared but invalid

weights:
  validation.signature.valid:      0.25
  validation.mrz.checkdigit.*:     0.25
  validation.vizmrz.*:             0.25
  face.match.cosine:               0.15
  tamper.*:                        0.10

disclosure: null                  # or a string shown in the console
```

For documents with no real integrity mechanism:

```yaml
doc_type: pan
verify:
  signature: reference_issuer
  arithmetic: [pan_format]
disclosure: "Signature verified against reference issuer (demonstration)"
```

Wildcards in `weights` and `hard_fail` match by prefix. Weights need not sum to 1; they are renormalised over signals that actually ran.

---

## 5. Risk gate policy

```yaml
gate:
  clear_immediately:
    all_of: [signature_valid_or_absent, no_arithmetic_failures,
             face_confident, tamper_score_below: 0.15]

  escalate_if_any:
    - no_crypto_anchor AND tamper_score_above: 0.25
    - any: [validation.vizmrz.*]
    - face.match.cosine in review_band
    - face.liveness.passive in uncertain_band
    - tamper.stamp.duplicate

  hard_fail_immediately:          # never escalate, straight to RED
    - validation.mrz.checkdigit.composite
    - validation.signature.valid == false
    - validation.expiry.expired
    - validation.watchlist.hit
    - validation.crossdoc.dob_mismatch    # when one side is signed
```

---

## 6. Scoring rules

```python
# 1. Hard fail wins outright
if any(s.hard_fail and s.verdict == "fail" for s in signals):
    return RED

# 2. Coverage floor — inconclusive is not pass
applicable = [s for s in signals if s.verdict != "not_applicable"]
ran        = [s for s in applicable if s.verdict != "inconclusive"]
coverage   = weight_sum(ran) / weight_sum(applicable)
if coverage < 0.70:
    return AMBER, "Insufficient evidence - re-capture required"

# 3. Cryptographic precedence
crypto = [f for f in findings if f.trust_class == "cryptographic"]
if crypto and all(f.severity == 0 for f in crypto):
    findings = [f for f in findings
                if not (f.trust_class == "probabilistic"
                        and f.anchor in signed_fields)]

# 4. Weighted sum over findings, weights renormalised over `ran`
score = sum(f.severity * profile_weight(f.anchor) for f in findings)

# 5. Bands (config/bands.yaml, operator-tunable)
#    < 0.20  GREEN   clear
#    < 0.60  AMBER   secondary inspection
#    >= 0.60 RED     detain / manual review
```

---

## 7. Evidence card ordering

```
1. Hard fails                         (always first, always visible)
2. Findings, sorted by trust class then severity descending
3. Coverage gaps ("could not evaluate X")
4. Passing cryptographic signals       (always visible - reassurance)
5. Collapsed count of passing probabilistic signals
```

Passing probabilistic signals are noise and collapse to "N checks passed". Passing cryptographic signals are the most reassuring thing an officer can see and always render.

---

## 8. Database schema (essentials)

```sql
CREATE TABLE screening_events (
  id              UUID PRIMARY KEY,
  session_id      UUID NOT NULL,
  doc_type        TEXT NOT NULL,
  doc_hash        TEXT NOT NULL,        -- SHA-256 of canonical fields
  id_number_hash  TEXT,                 -- salted hash. NEVER the raw number.
  id_number_last4 TEXT,
  verdict         TEXT NOT NULL,        -- GREEN | AMBER | RED
  score           NUMERIC(4,3),
  coverage        NUMERIC(4,3),
  signals         JSONB NOT NULL,       -- FULL signal list, for re-scoring
  model_versions  JSONB NOT NULL,
  officer_id      TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE trust_anchors (
  issuer_id   TEXT PRIMARY KEY,
  public_key  BYTEA NOT NULL,
  algorithm   TEXT NOT NULL,            -- 'ed25519'
  is_reference BOOLEAN NOT NULL,        -- true => show disclosure in UI
  valid_from  TIMESTAMPTZ,
  valid_until TIMESTAMPTZ
);

CREATE TABLE face_gallery (
  id          UUID PRIMARY KEY,
  event_id    UUID REFERENCES screening_events(id),
  embedding   vector(512) NOT NULL,     -- pgvector. NO raw images.
  created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON face_gallery USING hnsw (embedding vector_cosine_ops);

CREATE TABLE watchlist (
  id          SERIAL PRIMARY KEY,
  source      TEXT,                     -- 'OFAC' | 'UN' | 'synthetic'
  name        TEXT, aliases TEXT[],
  dob         DATE, nationality TEXT,
  doc_numbers TEXT[]
);
```

**Store the full signal list, not just the cards.** Cards are a view. If weights change you must be able to re-score historical cases without re-running inference.

**Never store:** raw ID numbers, raw face images beyond session TTL, unhashed personal data.
