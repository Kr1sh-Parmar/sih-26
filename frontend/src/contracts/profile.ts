/** MIRRORS context/CONTRACTS.md §4 — the parts the console needs. */
export interface DocumentProfile {
  doc_type: string;
  hard_fail: string[];
  weights: Record<string, number>;
  /** Rendered verbatim when non-null. A reference-issuer verification must
   *  never look like a government one (DEMO.md Scene 3). */
  disclosure: string | null;
}
