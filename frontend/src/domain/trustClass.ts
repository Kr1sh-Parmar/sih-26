/**
 * Trust class is the whole thesis of this system, so it gets its own visual
 * channel: verdict owns COLOUR, trust class owns FORM. They can then never
 * collide, and neither depends on the officer distinguishing two hues.
 *
 * The marks are borrowed from security printing, which is what this system is
 * actually about, and the chain runs in the same direction as certainty:
 *
 *   engraved  ->  registered  ->  screened  ->  blank
 *   rosette       register        halftone      open circle
 *
 * frontend.md §1.3.
 */
import type { TrustClass } from "../contracts";

export interface TrustStyle {
  label: string;
  /** What the mark means, shown in the footer legend and on hover. */
  gloss: string;
  /** Tailwind classes for the rule drawn under an evidence row. */
  rule: string;
  /** Ordering weight — lower is more certain. */
  rank: number;
}

export const TRUST_STYLE: Record<TrustClass, TrustStyle> = {
  cryptographic: {
    label: "cryptographic",
    gloss: "A signature verifies against a trusted key. Certain.",
    rule: "border-t-2 border-solid border-intaglio",
    rank: 0,
  },
  arithmetic: {
    label: "arithmetic",
    gloss: "A deterministic check. No model, no key.",
    rule: "border-t border-solid border-intaglio",
    rank: 1,
  },
  probabilistic: {
    label: "probabilistic",
    gloss: "Inference. It can be wrong.",
    rule: "border-t border-dotted border-iris",
    rank: 2,
  },
  unverified: {
    label: "unverified",
    gloss: "No check was available. Not the same as passing.",
    rule: "border-t border-dashed border-iris",
    rank: 3,
  },
};
