/** MIRRORS context/CONTRACTS.md §3. Produced by server-side fusion. */
import type { Region, Signal, TrustClass } from "./signal";

export interface Finding {
  anchor: string;
  /** 0-1, noisy-OR over the group. Never rendered as a bare percentage. */
  severity: number;
  /** Strongest class among the group's members. */
  trust_class: TrustClass;
  /** What the officer reads. */
  headline: string;
  /** Collapsed behind a disclosure triangle by default. */
  supporting: Signal[];
  region?: Region | null;
}
