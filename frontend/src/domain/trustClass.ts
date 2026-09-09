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
  /** Tailwind classes for a badge/pill/icon-square in this trust class's
   *  colour. One definition, reused by Legend, EvidenceList and Audit —
   *  those three used to hand-maintain their own near-identical copies of
   *  this exact map, which is exactly how a colour drifts between them. */
  badge: string;
}

export const TRUST_STYLE: Record<TrustClass, TrustStyle> = {
  cryptographic: {
    label: "cryptographic",
    gloss: "A signature verifies against a trusted key. Certain.",
    rule: "border-t-2 border-solid border-intaglio/30",
    rank: 0,
    badge: "bg-blue-50 text-blue-700 border border-blue-200",
  },
  arithmetic: {
    label: "arithmetic",
    gloss: "A deterministic check. No model, no key.",
    rule: "border-t border-solid border-intaglio/20",
    rank: 1,
    badge: "bg-slate-100 text-slate-600 border border-slate-200",
  },
  probabilistic: {
    label: "probabilistic",
    gloss: "Inference. It can be wrong.",
    rule: "border-t border-dotted border-iris",
    rank: 2,
    badge: "bg-probabilistic/10 text-probabilistic border border-probabilistic/30",
  },
  unverified: {
    label: "unverified",
    gloss: "No check was available. Not the same as passing.",
    rule: "border-t border-dashed border-iris",
    rank: 3,
    badge: "bg-orange-50 text-orange-600 border border-orange-200",
  },
};
