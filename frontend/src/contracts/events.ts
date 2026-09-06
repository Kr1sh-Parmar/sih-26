/** The WebSocket protocol. api/websocket.py streams these in this order. */
import type { Band, Signal } from "./signal";
import type { Finding } from "./finding";

export type Phase =
  | "idle"
  | "decoding"
  | "tier1"
  | "gate"
  | "tier2"
  | "fusing"
  | "done";

export type ScreeningEvent =
  | { type: "phase"; phase: Phase }
  | { type: "signal"; signal: Signal }
  | { type: "findings"; findings: Finding[] }
  | {
      type: "verdict";
      band: Band;
      score: number;
      coverage: number;
      disclosure: string | null;
    }
  | { type: "error"; message: string; recoverable: boolean };
