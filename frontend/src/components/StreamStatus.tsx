/**
 * Which modules have reported.
 *
 * A pause during Tier 2 escalation is real work, not a hang, and the officer
 * needs to be able to tell the difference. This also makes the tiering visible
 * during a demo: the gate fires, and only then does deep forensics run.
 */
import type { Phase, Signal } from "../contracts";
import { cn } from "../lib/utils";

const MODULES = [
  { key: "extraction", label: "Read" },
  { key: "validation", label: "Validate" },
  { key: "tamper", label: "Tamper" },
  { key: "face", label: "Face" },
] as const;

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Ready",
  decoding: "Decoding the capture",
  tier1: "Running the fast checks",
  gate: "Risk gate — deciding whether to escalate",
  tier2: "Escalated: deep forensics",
  fusing: "Weighing the evidence",
  done: "Complete",
};

export function StreamStatus({
  phase,
  signals,
  elapsedMs,
}: {
  phase: Phase;
  signals: Signal[];
  elapsedMs: number | null;
}) {
  const reported = new Set(signals.map((s) => s.module));

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      {MODULES.map((m) => {
        const done = reported.has(m.key);
        return (
          <span key={m.key} className="inline-flex items-center gap-2 text-label">
            <span
              className={cn(
                "h-2 w-2",
                done ? "bg-intaglio" : "border border-iris bg-transparent",
              )}
            />
            <span className={done ? "text-intaglio" : "text-iris-ink"}>{m.label}</span>
          </span>
        );
      })}

      <span className="ml-auto text-label text-iris-ink">
        {PHASE_LABEL[phase]}
        {elapsedMs !== null && phase === "done" && (
          <>
            <span className="mx-2 inline-block h-3 w-px translate-y-0.5 bg-iris" />
            <span className="data">{elapsedMs} ms</span>
          </>
        )}
      </span>
    </div>
  );
}
