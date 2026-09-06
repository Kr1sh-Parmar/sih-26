# Officer Console — Frontend Design & Implementation Plan

**Goal:** Build `ui/` — the five-screen React officer console that renders a
document-screening verdict as *ordered, checkable evidence with its trust class
always visible*, streaming in from the FastAPI WebSocket.

**Architecture:** Vite + React 19 + TypeScript. Zustand for the screening
store, Tailwind v4 with a CSS-first token layer. The client **never computes a
verdict** — fusion is server-side and the console renders what it receives. The
only decision logic on the client is evidence-card *ordering* (`CONTRACTS.md`
§7), which is presentation. A first-class mock transport replays the
hand-written signal fixtures with the real latency budget, so the console is
built, demoed and rehearsed before a single model exists.

**Tech stack:** Vite · React 19 · TypeScript 5 · Tailwind CSS v4 · Zustand ·
Vitest · Playwright · self-hosted Archivo + DM Mono. No runtime network calls,
no CDN, no icon package.

**Specs this implements:** `CONTRACTS.md` (§1 Signal, §3 Finding, §4 profile,
§6 scoring, §7 card ordering) · `MODULES.md` "Officer console" · `DEMO.md`
Scenes 1–5 · `TECHNICAL-SPEC.md` §11–12 · `ROADMAP.md` Phase 4 ·
`GETTING-STARTED.md` §5–6.

---

## Context

Nothing exists under `ui/` yet. The data phase is finished — the merged field
dataset is built and verified (18/22 classes, 46,770 boxes) — and the backend
contracts are frozen. `GETTING-STARTED.md` §6 puts the console on **days 3–5 of
week 0**, built against fixture data, precisely because the hard UI must not
wait on models. `ROADMAP.md` Phase 4 sets the exit gate:

> *A person who has never seen the system can read a RED verdict and say why.*

That sentence is the whole brief. Everything below serves it.

Three constraints shape every decision:

1. **Offline is a hard rule** (`CLAUDE.md` #3). Zero network at runtime. No
   Google Fonts, no CDN, no icon package, no analytics. Fonts and every asset
   are committed and served by the local nginx.
2. **Trust class must never be flattened.** Collapsing a signature check and a
   texture heuristic into one number is the exact failure this project exists
   to avoid (`MODULES.md` pitfalls). Trust class is a *visual system*, not a
   text label.
3. **The officer has seconds and must justify a detention months later.** The
   verdict reads at 3 metres; the evidence reads at arm's length; the full
   signal list is stored and re-scorable.

## Global constraints

- Every runtime asset is local. CI greps the built bundle for `https://` and
  fails on a hit.
- `ui/src/contracts/` mirrors `CONTRACTS.md` §1–4 exactly. **No other file may
  define these shapes.** Renaming a field here breaks four people's work.
- The client never derives a verdict, score, or coverage figure. It renders
  what fusion sends. Changing the operating point calls `POST /rescore`.
- No bare percentage anywhere as a verdict. Score always appears with reasons.
- A reference-issuer verification must never look like a government one; the
  profile's `disclosure` string renders whenever it is non-null.
- Verdict is carried by **word + colour + mark** together, never colour alone.
- `not_applicable` and `inconclusive` render differently and are never merged.

---

## Part 1 — Design system

### 1.1 Why this palette fits the subject

The console is a document-examination table. Its subject matter is security
printing: guilloche lathe-work, intaglio ink, plate registration, halftone
screens, the Ashoka lion capital. The chosen palette is not arbitrary against
that world — an Indian passport data page is lilac and violet over buttery
guilloche; the Aadhaar PVC card is cream. **The interface is the colour of the
paper the officer is already holding.** Structural devices are borrowed from
security printing and every one of them encodes information rather than
decorating.

### 1.2 Colour tokens

Supplied palette, assigned by role:

| Token | Hex | Role |
|---|---|---|
| `--paper` | `#fff2cf` | Application ground. The examination surface. |
| `--guilloche` | `#f8de7e` | SECONDARY verdict band · focus ring · active state |
| `--bloom` | `#e7c9e8` | Evidence panel ground, one step lifted from paper · hover wash |
| `--iris` | `#b39bbe` | Hairline rules, marks, dividers — **decorative weight only** |
| `--intaglio` | `#3a2e45` | All primary text · chrome bars · document-viewer well |

**Contrast correction — required.** `--iris` on `--paper` is ~2.2:1 and fails
WCAG AA for text. It is for rules and marks only. Secondary text uses a
darkened sibling:

| Token | Hex | Contrast on `--paper` |
|---|---|---|
| `--iris-ink` | `#6E5C7A` | 5.6:1 — passes AA for body |
| `--intaglio` | `#3a2e45` | 11.8:1 — passes AAA |

**Semantic triad — added, and here is why.** The supplied palette contains no
green and no red. A border verdict of CLEAR / SECONDARY / DETAIN is
safety-critical and must be distinguishable at 3 metres by someone who may be
colour-blind. Three semantic colours are therefore added, each tuned to sit
inside the plum–lilac family rather than pulled from a default UI kit:

| Verdict | On paper | On plum well | Note |
|---|---|---|---|
| CLEAR | `#1F5D4C` verdigris | `#7FD1B0` | Deep, cool — sits under the lilac |
| SECONDARY | `#8A6A0F` ink on `--guilloche` band | `#f8de7e` | Free — the palette's own buttercup |
| DETAIN | `#A3123A` madder | `#FF7A94` | Warm carmine, shares the plum's undertone |

Colour is reinforcement only. The word does the work.

### 1.3 Trust class is form, not colour

Verdict owns colour. Trust class owns **mark and rule weight**, rendered in
intaglio ink regardless of verdict, so the two systems never collide. Each mark
is a 16px inline SVG drawn once in `components/marks/` (inline because there is
no icon CDN, and because these do not exist in any icon set).

| Trust class | Mark | Rule beneath the card | Metaphor |
|---|---|---|---|
| `cryptographic` | Filled guilloche **rosette** | 2px solid intaglio | Engraved. Unforgeable. |
| `arithmetic` | **Register cross** — plate-registration tick | 1px solid intaglio | Mechanical. Exact. |
| `probabilistic` | **Halftone cluster** — three graded dots | 1px dotted iris | Screened. Approximated. |
| `unverified` | **Open circle**, hairline | 1px dashed iris | Unknown. |

The metaphor chain — engraved → registered → screened → blank — runs in the
same direction as certainty. An officer learns it in one sighting and it is
genuinely informative, not ornamental. A persistent four-item legend sits in
the console footer.

This is the design's one bold idea. Everything else stays quiet.

### 1.4 Typography

Two families, both SIL OFL, both committed as woff2 under `ui/public/fonts/`.

| Face | Role |
|---|---|
| **Archivo** (variable, 400–700, normal + expanded width) | All UI, headings, evidence text |
| **DM Mono** | Machine-readable strings **only**: MRZ lines, ID numbers, hashes, check digits, cosine values |

Monospace here is functional, not stylistic. An MRZ line must be
character-aligned so the officer can count field positions and compare check
digits by eye. It is never used for small labels as decoration.

Scale — 1.25 minor third off a 17px base:

| Step | Size / face |
|---|---|
| Verdict word | 76px Archivo Expanded 700, tracking −0.02em |
| Screen heading | 27px Archivo 600 |
| Evidence headline | 19px Archivo 500 — deliberately above body; this is the line the officer must read |
| Body / supporting | 17px Archivo 400 |
| Label / meta | 14px Archivo 500, `--iris-ink` |
| Data | 16px DM Mono 400, `font-variant-numeric: tabular-nums` |

The verdict at 76px reads across the room. The evidence at 19px reads at the
officer's own distance. That split is intentional: **the verdict is for the
room, the evidence is for the officer.**

Line length capped at 68 characters on evidence text. Sentence case
everywhere — no tracked-out all-caps eyebrow labels above headings.

### 1.5 Surface rules

- **No shadows anywhere.** Separation is by hairline rule and ground tint.
- **Border radius 0** on every structural surface — documents have square
  corners and so does plate registration. The single exception is a 999px pill,
  reserved *only* for trust-class chips, so the shape itself means "this is a
  trust class".
- Spacing on a 4px base; panel gutter 32px; the evidence list breathes at 20px
  between findings, 8px within a finding's supporting lines.
- No middle-dot meta strings (`A · B · C`). Use a hairline separator or a line
  break.

### 1.6 Motion

One orchestrated moment, and it belongs to the streaming: **as each finding
arrives, its hairline rule draws left-to-right over 120 ms and the text sets
behind it.** It reads like a record being written. Nothing fades and slides up.

Everything else animates only in answer to something the officer did —
expanding supporting signals, dragging the operating point. Under
`prefers-reduced-motion` rules appear instantly and text does not stagger.

### 1.7 Screening screen layout

Left two-thirds is physical evidence — the document under glass in a deep-plum
well, face pair docked beneath. Right third is the written record. This mirrors
what the officer actually does: look at the document, then read the finding.
Everything is flush left, ragged right; nothing is centred, including the
verdict — a centred verdict reads like a marketing hero, not a record.

```
┌ Sashastra Seema Bal   Raxaul ICP │ 14:32 │ Officer 4471 ────────────┐  plum chrome
│                                                                      │
│ ┌────────────────────────────────┐   ┌────────────────────────────┐  │
│ │▓▓ plum well ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓│   │ DETAIN                     │  │ 76px expanded
│ │                                │   │ ████████████████████████   │  │ 6px madder band
│ │       [ warped document ]      │   │ Manual review required     │  │
│ │        ┌──────────┐            │   │ score 0.81   coverage 94%  │  │
│ │        │  region  │◀───────────┼───┤                            │  │ bidirectional
│ │        └──────────┘            │   │ ❋ Signature verifies       │  │ rosette
│ │                                │   │   Reference issuer —       │  │
│ └────────────────────────────────┘   │   demonstration only       │  │ disclosure
│   front   back   raw   warped        │ ━━━━━━━━━━━━━━━━━━━━━━━━━  │  │ 2px solid
│                                      │ ✛ Date of birth conflict   │  │ register cross
│ ┌───────────┬───────────┐            │   MRZ      1991-03-04      │  │ DM Mono
│ │ document  │   live    │            │   Printed  1991-08-04      │  │
│ │   face    │   face    │            │   3 supporting signals  ▸  │  │
│ └───────────┴───────────┘            │ ───────────────────────    │  │ 1px solid
│  cosine 0.41   +0.09 over 0.32       │ ⁙ Could not evaluate       │  │ halftone
│  ├─────────┼──────●─────┤            │   guilloche — image blur   │  │
│  no match   review   match           │ ⁙ 12 checks passed      ▸  │  │
│                                      │ ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈ │  │ 1px dotted
│  Extracted fields                    │                            │  │
│  ─────────────────────────           │                            │  │
│  name     MUHAMAD SABRI      ✓       │                            │  │
│  dob      1991-08-04         ✗       │                            │  │
│  number   E1009353           ✓       │                            │  │
│                                      └────────────────────────────┘  │
│ ❋ cryptographic  ✛ arithmetic  ⁙ probabilistic  ○ unverified         │  legend
└──────────────────────────────────────────────────────────────────────┘
```

**Hover or focus a finding → its region lights on the document, and vice
versa.** That link is the spine of the interaction and the thing that makes the
evidence *checkable by a human* rather than assertable by a model.

### 1.8 Face pair — never a percentage

`CLAUDE.md` and `MODULES.md` both forbid `((cos+1)/2)*100`, which maps a
stranger to 50. Render three things instead: the band (no match / review /
match), the raw cosine in DM Mono, and the **signed margin from the current
operating threshold** on a small scale with the threshold marked. The officer
sees how close the call was, which is the number that actually matters.

---

## Part 2 — File structure

```
ui/
├── index.html
├── vite.config.ts
├── vitest.config.ts
├── playwright.config.ts
├── public/fonts/               Archivo + DM Mono woff2, committed
└── src/
    ├── main.tsx
    ├── app/App.tsx             shell, router, legend footer
    ├── contracts/              ← MIRRORS CONTRACTS.md. Nothing else defines these.
    │   ├── signal.ts           Signal, Verdict, TrustClass, Band
    │   ├── finding.ts          Finding
    │   ├── events.ts           WS event discriminated union
    │   └── profile.ts          weights, hard_fail, disclosure
    ├── transport/
    │   ├── api.ts              POST /screen, POST /rescore, GET /events
    │   ├── useScreeningSocket.ts
    │   └── mockSocket.ts       replays fixtures at latency-budget delays
    ├── store/
    │   ├── screening.ts        phase, signals[], findings[], verdict, activeAnchor
    │   ├── session.ts          multi-document, trust propagation edges
    │   └── settings.ts         operating point, bands
    ├── domain/
    │   ├── ordering.ts         CONTRACTS §7 — pure, unit-tested
    │   ├── trustClass.ts       class → mark, rule, label, order
    │   └── faceMargin.ts       cosine → band + signed margin
    ├── components/
    │   ├── marks/              Rosette · RegisterCross · Halftone · OpenCircle
    │   ├── VerdictBand.tsx     CoverageMeter.tsx    DisclosureNotice.tsx
    │   ├── EvidenceList.tsx    EvidenceCard.tsx     SupportingSignals.tsx
    │   ├── DocumentViewer.tsx  RegionOverlay.tsx    FieldTable.tsx
    │   ├── FacePair.tsx        MarginGauge.tsx      StreamStatus.tsx
    │   └── OperatingPointControl.tsx
    ├── screens/
    │   ├── Capture.tsx  Screening.tsx  Session.tsx
    │   ├── OperatingPoint.tsx  Audit.tsx
    ├── styles/
    │   ├── tokens.css          palette, type scale, spacing as custom properties
    │   └── fonts.css           @font-face, local only
    └── fixtures/               copies of tests/fixtures/signals_*.json
```

**Why `contracts/` is its own directory and not co-located:** four people build
against these shapes. Drift between the Python dataclass and the TS interface
is the single most expensive bug available in this project, and a dedicated
directory makes the mirror obvious to a reviewer.

---

## Part 3 — Tasks

### Task 1 — Scaffold, tokens, fonts, offline guard

**Files:** create `ui/` per structure above; `src/styles/tokens.css`,
`src/styles/fonts.css`, `public/fonts/*.woff2`, `vite.config.ts`.

- [ ] `npm create vite@latest ui -- --template react-ts`; add
      `tailwindcss@4`, `@tailwindcss/vite`, `zustand`, `vitest`,
      `@playwright/test`.
- [ ] Download Archivo and DM Mono woff2 **now, at build-setup time**, commit
      them to `public/fonts/`, and write `@font-face` pointing at those local
      files. No `@import` from fonts.googleapis.com — that would violate
      `CLAUDE.md` #3 the moment the cable is pulled.
- [ ] Write `tokens.css` with every value from §1.2 and §1.4 as custom
      properties under `@theme` so Tailwind v4 exposes them as utilities.
- [ ] Add `scripts/check-offline.sh`: builds, then greps `dist/` for any
      non-localhost `http(s)://` and exits non-zero on a hit. Wire into
      `npm run verify`.
- [ ] Commit: `feat(ui): scaffold with offline-safe token and font layer`

### Task 2 — Contracts mirror

**Files:** create `src/contracts/{signal,finding,events,profile}.ts`,
`src/contracts/__tests__/mirror.test.ts`.

**Produces:** `Signal`, `Finding`, `Verdict`, `Band`, `TrustClass`,
`ScreeningEvent`.

- [ ] Transcribe `CONTRACTS.md` §1 and §3 field-for-field. `Verdict` is
      `"pass" | "fail" | "inconclusive" | "not_applicable"` and belongs to a
      *signal*; the overall band is a separate type
      `Band = "GREEN" | "AMBER" | "RED"`. These are different things and
      conflating them is a real hazard.
- [ ] Define the WS event union:

```ts
export type ScreeningEvent =
  | { type: "phase";    phase: "decoding"|"tier1"|"gate"|"tier2"|"fusing"|"done" }
  | { type: "signal";   signal: Signal }
  | { type: "findings"; findings: Finding[] }
  | { type: "verdict";  band: Band; score: number; coverage: number;
                        disclosure: string | null }
  | { type: "error";    message: string; recoverable: boolean };
```

- [ ] Write a test that loads each `tests/fixtures/signals_*.json` and asserts
      every object parses into `Signal` with no unknown keys. This is the drift
      alarm — it fails the day the Python side changes a field name.
- [ ] Commit: `feat(ui): mirror frozen contracts as TypeScript types`

### Task 3 — Card ordering (`CONTRACTS.md` §7)

**Files:** create `src/domain/ordering.ts`,
`src/domain/__tests__/ordering.test.ts`.

**Produces:** `orderEvidence(findings, signals): EvidenceRow[]`

This is the only decision logic the client owns. Write the tests first — one
per rule in §7:

- [ ] Hard fails come first and are never collapsed.
- [ ] Findings sort by trust class (`cryptographic` → `arithmetic` →
      `probabilistic` → `unverified`), then by severity descending.
- [ ] Coverage gaps (`inconclusive`) render as their own group, and
      `not_applicable` signals never appear in it.
- [ ] Passing cryptographic signals always render — they are the most
      reassuring thing an officer sees.
- [ ] Passing probabilistic signals collapse to a single count row.
- [ ] Run against all four fixtures; assert the rendered order by signal ID.
- [ ] Commit: `feat(ui): evidence card ordering per contract §7`

### Task 4 — Mock transport

**Files:** create `src/transport/mockSocket.ts`, `src/transport/api.ts`,
`src/transport/useScreeningSocket.ts`.

**Consumes:** `ScreeningEvent` from Task 2.

- [ ] `mockSocket` replays a fixture as a sequence of `ScreeningEvent`s with
      delays taken from `TECHNICAL-SPEC.md` §10 — decode 60 ms, detection
      110 ms, OCR 280 ms, face 320 ms, fusion 5 ms. The console must *feel*
      like the real thing before the real thing exists.
- [ ] `useScreeningSocket` picks mock or live from
      `import.meta.env.VITE_TRANSPORT` and exposes the same interface either
      way. No component knows which is running.
- [ ] Reconnect with backoff; on give-up emit
      `{type:"error", recoverable:false}`.
- [ ] Commit: `feat(ui): fixture-replaying mock transport at real latency`

### Task 5 — Store

**Files:** create `src/store/{screening,session,settings}.ts`.

- [ ] `screening`: `phase`, `signals[]`, `findings[]`, `band`, `score`,
      `coverage`, `disclosure`, `activeAnchor`. The reducer appends signals and
      replaces findings wholesale when fusion re-emits.
- [ ] `activeAnchor` is the hover/focus link between an evidence card and a
      document region — one field, read by both `EvidenceCard` and
      `RegionOverlay`.
- [ ] `settings`: operating point, persisted to `localStorage`, wrapped in
      try/catch (a kiosk browser may block storage).
- [ ] Commit: `feat(ui): screening, session and settings stores`

### Task 6 — Trust-class marks and the verdict band

**Files:** create `src/components/marks/*`, `src/domain/trustClass.ts`,
`src/components/VerdictBand.tsx`, `src/components/CoverageMeter.tsx`.

- [ ] Draw the four marks as inline SVG per §1.3 at a 16px box. No icon
      library — these do not exist in one, and adding a package would be a
      network dependency at build time and a bundle cost at runtime.
- [ ] `VerdictBand` renders word + band rule + score + coverage. The word is
      the primary carrier; assert in a test that the component renders the word
      text with colour stripped.
- [ ] Commit: `feat(ui): trust-class marks and verdict band`

### Task 7 — Evidence list

**Files:** create
`src/components/{EvidenceList,EvidenceCard,SupportingSignals,DisclosureNotice}.tsx`.

- [ ] `EvidenceCard` shows mark + headline + the finding's own values on their
      own lines in DM Mono. Scene 2 requires the card to **name both values** —
      one finding, not four bullets.
- [ ] Supporting signals sit behind a disclosure triangle, collapsed by
      default.
- [ ] `DisclosureNotice` renders whenever `disclosure` is non-null, in a
      visually distinct treatment from a real trust anchor. Scene 3 fails if a
      reference verification looks like a government one.
- [ ] Rule-draw animation per §1.6, gated on `prefers-reduced-motion`.
- [ ] Commit: `feat(ui): evidence list with trust class and disclosure`

### Task 8 — Document viewer and region overlay

**Files:** create
`src/components/{DocumentViewer,RegionOverlay,FieldTable}.tsx`.

- [ ] Image in the plum well; SVG overlay layer maps `Signal.region`
      `(x1,y1,x2,y2)` from warped-image coordinates to rendered coordinates.
      Keep that mapping in one function — it is the thing that silently breaks
      when the viewer is resized.
- [ ] Bidirectional highlight through `activeAnchor`.
- [ ] Zoom and pan; tab switcher for front / back / raw / warped.
- [ ] `FieldTable`: value, source (`ocr|mrz|qr|vlm`), confidence, validation
      state. A `vlm`-sourced field is `unverified` and must show the open
      circle.
- [ ] Commit: `feat(ui): document viewer with linked region overlay`

### Task 9 — Face pair and margin gauge

**Files:** create `src/components/{FacePair,MarginGauge}.tsx`,
`src/domain/faceMargin.ts`, `src/domain/__tests__/faceMargin.test.ts`.

- [ ] Test first: `faceMargin(0.41, 0.32)` returns
      `{band:"match", margin:+0.09}`; assert no code path produces a 0–100
      figure.
- [ ] Three bands with the threshold marked on the scale.
- [ ] Explicit "no face found" state — never fail silently.
- [ ] Commit: `feat(ui): face pair with margin from threshold`

### Task 10 — Screening screen

**Files:** create `src/screens/Screening.tsx`,
`src/components/StreamStatus.tsx`.

- [ ] Assemble the §1.7 layout. Reserve space for every panel so nothing shifts
      as signals stream — layout shift at 450 ms is what makes a fast system
      feel slow.
- [ ] `StreamStatus` shows which modules have reported, so a pause reads as
      progress rather than a hang.
- [ ] Commit: `feat(ui): screening screen`

### Task 11 — Capture screen

**Files:** create `src/screens/Capture.tsx`.

- [ ] Scanner / file / webcam sources. Live quality readout for blur,
      resolution and glare before submit — an AMBER "re-capture required" is
      far cheaper to prevent than to explain at the counter.
- [ ] Webcam failure falls back to file upload with a plain message saying what
      happened and what to do next.
- [ ] Commit: `feat(ui): capture screen with pre-submit quality gates`

### Task 12 — Session screen (Scene 3, the headline)

**Files:** create `src/screens/Session.tsx`.

- [ ] Documents in the session as a row; the signed one carries the rosette.
- [ ] Draw the propagation explicitly: the signed Aadhaar's DOB links to the
      PAN's DOB with the contradiction rendered on the edge itself. The claim
      being demonstrated is *"the signature verifies, so this date is proven,
      and that document contradicts it"* — the UI has to show the "so".
- [ ] Commit: `feat(ui): multi-document session with trust propagation`

### Task 13 — Operating point

**Files:** create `src/screens/OperatingPoint.tsx`,
`src/components/OperatingPointControl.tsx`.

- [ ] FAR/FRR curve with a draggable operating point. **Load the `dataviz`
      skill before writing this chart.**
- [ ] State the consequence in passengers, not rates: "at 5,000 crossings a
      day, about 100 secondary inspections". That framing is the point of
      Scene 4.
- [ ] Moving the handle calls `POST /rescore`; the client does not recompute.
- [ ] Commit: `feat(ui): FAR/FRR operating point control`

### Task 14 — Audit and re-score

**Files:** create `src/screens/Audit.tsx`.

- [ ] Event list from `GET /events`; open one and see its stored signals.
- [ ] Re-score with changed weights via `POST /rescore`, showing old and new
      side by side. This is the Phase 4 exit-gate item and the answer to
      "decisions get challenged months later".
- [ ] Never render a raw ID number — last four digits only, per `CLAUDE.md` #5.
- [ ] Commit: `feat(ui): audit trail with re-scoring from stored signals`

---

## Verification

**Unit (Vitest):** `ordering.ts` against all four fixtures; `faceMargin.ts`;
the contracts mirror test.

**End-to-end (Playwright, mock transport):**

- `signals_red_hardfail.json` → the word DETAIN renders, and the evidence card
  names **both** DOB values.
- `signals_crossdoc_mismatch.json` → the disclosure string is present.
- `signals_amber_coverage.json` → AMBER with "re-capture required", and no
  GREEN path is reachable.
- Hovering an evidence card highlights the matching document region.

**Manual, before the demo:**

- Legibility of the verdict word from 3 metres on the demo monitor.
- Full keyboard pass with a visible focus ring.
- `prefers-reduced-motion: reduce` — rules appear, nothing staggers.
- Deuteranopia simulation — every verdict still readable from word and mark.
- `npm run build && npx serve dist`, DevTools offline, hard reload. Fonts and
  every asset still load. Then pull the actual cable and repeat.

---

## What this plan deliberately does not do

- **No design-system package, no Storybook.** Fourteen components used once
  each in one application. A catalogue would cost more than it returns.
- **No i18n layer.** Single deployment, English console; Hindi is not in scope
  in any spec document. Adding the machinery now is speculative.
- **No client-side fusion.** Two implementations of the scoring rules would
  drift, and the divergence would surface in front of a panel.
- **No chart library until Task 13**, where one chart genuinely needs it.
