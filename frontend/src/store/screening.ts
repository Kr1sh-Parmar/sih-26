/**
 * The screening store. One reducer over the WebSocket event stream.
 *
 * The client never derives a verdict, score or coverage — fusion is
 * server-side and this store only records what arrived. `activeAnchor` is the
 * one piece of purely local state, and it is what links an evidence card to a
 * region on the document.
 */
import { create } from "zustand";
import type { Band, Finding, ScreeningEvent, Signal } from "../contracts";
import type { Phase } from "../contracts";
import type { FixtureDoc } from "../transport/mockSocket";

export interface ScreeningState {
  phase: Phase;
  signals: Signal[];
  findings: Finding[];
  band: Band | null;
  score: number | null;
  coverage: number | null;
  disclosure: string | null;
  error: { message: string; recoverable: boolean } | null;

  /** Presentation-only: the anchor currently hovered or focused, in either
   *  direction between the evidence list and the document overlay. */
  activeAnchor: string | null;

  /** Everything the mock fixture supplies that the live socket will supply
   *  through separate endpoints — document image, fields, face crops. */
  doc: FixtureDoc | null;

  apply: (e: ScreeningEvent) => void;
  setActiveAnchor: (anchor: string | null) => void;
  setDoc: (doc: FixtureDoc | null) => void;
  reset: () => void;
}

const EMPTY = {
  phase: "idle" as Phase,
  signals: [] as Signal[],
  findings: [] as Finding[],
  band: null,
  score: null,
  coverage: null,
  disclosure: null,
  error: null,
  activeAnchor: null,
  doc: null,
};

export const useScreening = create<ScreeningState>((set) => ({
  ...EMPTY,

  apply: (e) =>
    set((s) => {
      switch (e.type) {
        case "phase":
          return { phase: e.phase };
        case "signal":
          return { signals: [...s.signals, e.signal] };
        case "findings":
          // Fusion re-emits the whole set whenever it re-scores, so this
          // replaces rather than merges.
          return { findings: e.findings };
        case "verdict":
          return {
            band: e.band,
            score: e.score,
            coverage: e.coverage,
            disclosure: e.disclosure,
          };
        case "error":
          return { error: { message: e.message, recoverable: e.recoverable } };
        default:
          return {};
      }
    }),

  setActiveAnchor: (activeAnchor) => set({ activeAnchor }),
  setDoc: (doc) => set({ doc }),
  reset: () => set({ ...EMPTY }),
}));
