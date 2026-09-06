/**
 * Fixture replay at the real latency budget.
 *
 * This is not a test hack. context/GETTING-STARTED.md §6 builds the console
 * against fixtures on day 3 of week 0, before any model exists, and
 * context/DEMO.md keeps a backup path for the day the webcam fails. The
 * timings come from context/TECHNICAL-SPEC.md §10, so the console *feels*
 * like the real thing: first verdict visible at roughly 450 ms, everything
 * settled inside a second.
 */
import type { ScreeningEvent, Signal } from "../contracts";

import green from "../fixtures/signals_green.json";
import red from "../fixtures/signals_red_hardfail.json";
import amber from "../fixtures/signals_amber_coverage.json";
import crossdoc from "../fixtures/signals_crossdoc_mismatch.json";

export const FIXTURES = {
  green,
  red,
  amber,
  crossdoc,
} as const;

export type FixtureName = keyof typeof FIXTURES;

export interface FixtureDoc {
  meta: Record<string, unknown> & { doc_type: string; scene: string; note: string };
  signals: Signal[];
  findings: ScreeningEvent extends { type: "findings"; findings: infer F } ? F : never;
  verdict: { band: "GREEN" | "AMBER" | "RED"; score: number; coverage: number; disclosure: string | null };
  face: { cosine: number | null; threshold: number };
  fields: {
    name: string; value: string; source: "ocr" | "mrz" | "qr" | "vlm";
    confidence: number; state: "pass" | "fail" | "inconclusive";
    region: [number, number, number, number] | null;
  }[];
}

export function fixture(name: FixtureName): FixtureDoc {
  return FIXTURES[name] as unknown as FixtureDoc;
}

/** Cumulative milliseconds at which each module's signals land. Taken straight
 *  from the latency budget so a pause on screen is a real pause, not a guess. */
const MODULE_AT: Record<Signal["module"], number> = {
  extraction: 185, //  decode 60 + segmentation 45 + type 15 + detection 110, overlapped
  validation: 235, //  MRZ / QR parse + all validation layers
  tamper: 420,     //  cheap physical forensics
  face: 640,       //  detect + embed x2 + passive liveness
};
const TIER2_EXTRA = 900;

export interface Replay {
  cancel: () => void;
}

/**
 * Emits the fixture as a stream of ScreeningEvents on a real clock.
 * Returns a handle so a screen that unmounts mid-run stops the timers.
 */
export function replayFixture(
  name: FixtureName,
  emit: (e: ScreeningEvent) => void,
  speed = 1,
): Replay {
  const doc = fixture(name);
  const timers: ReturnType<typeof setTimeout>[] = [];
  const at = (ms: number, fn: () => void) => {
    timers.push(setTimeout(fn, Math.max(0, ms / speed)));
  };

  at(0, () => emit({ type: "phase", phase: "decoding" }));
  at(60, () => emit({ type: "phase", phase: "tier1" }));

  let last = 0;
  const tier2 = doc.signals.some((s) => s.tier === 2);

  for (const s of doc.signals) {
    // Signals from one module arrive together but not in the same tick, so the
    // list visibly writes itself rather than appearing all at once.
    const base = MODULE_AT[s.module] + (s.tier === 2 ? TIER2_EXTRA : 0);
    const jitter = doc.signals.indexOf(s) * 6;
    const t = base + jitter;
    last = Math.max(last, t);
    at(t, () => emit({ type: "signal", signal: s }));
  }

  if (tier2) {
    at(MODULE_AT.tamper + 40, () => emit({ type: "phase", phase: "gate" }));
    at(MODULE_AT.tamper + 90, () => emit({ type: "phase", phase: "tier2" }));
  }

  at(last + 40, () => emit({ type: "phase", phase: "fusing" }));
  at(last + 45, () => emit({ type: "findings", findings: doc.findings }));
  at(last + 50, () =>
    emit({
      type: "verdict",
      band: doc.verdict.band,
      score: doc.verdict.score,
      coverage: doc.verdict.coverage,
      disclosure: doc.verdict.disclosure,
    }),
  );
  at(last + 55, () => emit({ type: "phase", phase: "done" }));

  return {
    cancel: () => {
      for (const t of timers) clearTimeout(t);
      timers.length = 0;
    },
  };
}
