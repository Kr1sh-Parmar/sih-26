/**
 * Evidence card ordering — context/CONTRACTS.md §7.
 *
 * This is the ONLY decision logic on the client. Everything else (verdict,
 * score, coverage) is computed by server-side fusion and rendered as received;
 * two implementations of the scoring rules would drift, and the divergence
 * would surface in front of a panel.
 *
 * The contract order:
 *   1. Hard fails                        always first, always visible
 *   2. Findings, by trust class then severity descending
 *   3. Coverage gaps                     "could not evaluate X"
 *   4. Passing cryptographic signals     always visible — reassurance
 *   5. Collapsed count of passing probabilistic signals
 *
 * Passing probabilistic signals are noise and collapse to a count. Passing
 * cryptographic signals are the most reassuring thing an officer can see and
 * always render.
 */
import type { Finding, Signal } from "../contracts";
import { trustRank } from "../contracts";

export type EvidenceRow =
  /** `finding` carries the corroboration for the same anchor, so an altered
   *  date of birth is one card with its supporting checks folded in, not a
   *  hard-fail card followed by a finding card restating it. */
  | { kind: "hard_fail"; key: string; signal: Signal; finding?: Finding }
  | { kind: "finding"; key: string; finding: Finding }
  | { kind: "gap"; key: string; signal: Signal }
  | { kind: "crypto_pass"; key: string; signal: Signal }
  | { kind: "passed"; key: string; count: number; signals: Signal[] };

export function orderEvidence(
  findings: readonly Finding[],
  signals: readonly Signal[],
): EvidenceRow[] {
  const rows: EvidenceRow[] = [];
  // Anything already on screen — as its own row, or collapsed inside a
  // rendered finding — must not appear again further down.
  const shown = new Set<string>();
  // Only a hard-fail row may suppress a finding. Two findings can legitimately
  // share an anchor ("document"), and letting the first one's supporting set
  // swallow the second cost us the five-MRZ-check-digits card in Scene 1 —
  // which is the entire claim that scene exists to prove.
  const hardFailed = new Set<string>();

  // 1. Hard fails. A failing hard_fail signal ends the screening outright, so
  //    it leads regardless of severity or weight.
  //
  //    DEMO.md Scene 2: "One finding, not four bullets." A finding on the same
  //    anchor is corroboration for this hard fail, not a separate story, so it
  //    is folded in here and skipped below.
  const folded = new Set<Finding>();
  for (const s of signals) {
    if (!s.hard_fail || s.verdict !== "fail") continue;
    const corroborating = findings.find(
      (f) => f.anchor === s.anchor && f.severity > 0 && !folded.has(f),
    );
    if (corroborating) folded.add(corroborating);
    rows.push({
      kind: "hard_fail",
      key: `hf:${s.id}`,
      signal: s,
      finding: corroborating,
    });
    shown.add(s.id);
    hardFailed.add(s.id);
    for (const sup of corroborating?.supporting ?? []) shown.add(sup.id);
  }

  // 2. Findings. Ordering is by decision impact: trust class first, because a
  //    signature check and a texture heuristic are not comparable quantities,
  //    then severity within a class.
  const ordered = [...findings].sort(
    (a, b) =>
      trustRank(a.trust_class) - trustRank(b.trust_class) ||
      b.severity - a.severity,
  );
  for (const f of ordered) {
    if (folded.has(f)) continue;
    // A finding whose whole story is already told by a hard-fail row above is
    // not repeated.
    const supporting = f.supporting ?? [];
    const toldByHardFail =
      supporting.length > 0 && supporting.every((s) => hardFailed.has(s.id));
    if (toldByHardFail) continue;

    rows.push({ kind: "finding", key: `f:${f.trust_class}:${f.anchor}:${f.headline}`, finding: f });
    for (const s of supporting) shown.add(s.id);
  }

  // 3. Coverage gaps. `inconclusive` means the check ran and could not decide,
  //    which counts against coverage. `not_applicable` means the check does not
  //    exist for this document (Aadhaar has no MRZ) and is excluded entirely —
  //    conflating the two is how a blurry photo produces a GREEN verdict.
  for (const s of signals) {
    if (s.verdict === "inconclusive" && !shown.has(s.id)) {
      rows.push({ kind: "gap", key: `gap:${s.id}`, signal: s });
      shown.add(s.id);
    }
  }

  // 4. Passing cryptographic signals.
  for (const s of signals) {
    if (
      s.trust_class === "cryptographic" &&
      s.verdict === "pass" &&
      !shown.has(s.id)
    ) {
      rows.push({ kind: "crypto_pass", key: `cp:${s.id}`, signal: s });
      shown.add(s.id);
    }
  }

  // 5. Everything else that passed, as a single count.
  const passed = signals.filter(
    (s) => s.verdict === "pass" && !shown.has(s.id),
  );
  if (passed.length > 0) {
    rows.push({
      kind: "passed",
      key: "passed",
      count: passed.length,
      signals: passed,
    });
  }

  return rows;
}
