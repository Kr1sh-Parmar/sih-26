/**
 * MIRRORS context/CONTRACTS.md §1. Nothing else in this app may define these
 * shapes. Drift between the Python dataclass and this file is the single most
 * expensive bug available in this project — four people build against it.
 */

/** A single check's outcome. Belongs to a Signal, NOT to the whole document. */
export type Verdict = "pass" | "fail" | "inconclusive" | "not_applicable";

/** The overall document band. Deliberately a different type from Verdict —
 *  conflating "this check passed" with "this traveller is cleared" is a real
 *  hazard, so the compiler is made to care. */
export type Band = "GREEN" | "AMBER" | "RED";

export type TrustClass =
  | "cryptographic"
  | "arithmetic"
  | "probabilistic"
  | "unverified";

export type ModuleName = "extraction" | "validation" | "tamper" | "face";

/** (x1, y1, x2, y2) in warped-image coordinates. */
export type Region = readonly [number, number, number, number];

export interface Signal {
  /** Stable dotted string registered in CONTRACTS.md §1, e.g. "mrz.checkdigit.dob". */
  id: string;
  module: ModuleName;
  /** 1 = always runs, 2 = escalated only. */
  tier: 1 | 2;
  verdict: Verdict;
  /** 0.0-1.0. Deterministic checks use 1.0. */
  confidence: number;
  trust_class: TrustClass;
  /** True bypasses scoring entirely -> RED. */
  hard_fail: boolean;
  /** "field:dob" | "region:x1,y1,x2,y2" | "document" */
  anchor: string;
  /** One line, shown verbatim to the officer. Never a debug string. */
  evidence: string;
  region?: Region | null;
  latency_ms: number;
}

/** Ordering used everywhere trust class is sorted or ranked.
 *  Runs in the same direction as certainty. */
export const TRUST_ORDER: readonly TrustClass[] = [
  "cryptographic",
  "arithmetic",
  "probabilistic",
  "unverified",
] as const;

export function trustRank(t: TrustClass): number {
  return TRUST_ORDER.indexOf(t);
}
