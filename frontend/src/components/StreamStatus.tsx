/**
 * Which modules have reported.
 */
import type { Phase, Signal } from "../contracts";
import { cn } from "../lib/utils";

const MODULES = [
  { key: "extraction", label: "Read", icon: "📄" },
  { key: "validation", label: "Validate", icon: "✓" },
  { key: "tamper", label: "Tamper", icon: "🔍" },
  { key: "face", label: "Face", icon: "👤" },
] as const;

const PHASE_LABEL: Record<Phase, string> = {
  idle: "Ready",
  decoding: "Decoding…",
  tier1: "Fast checks",
  gate: "Risk gate",
  tier2: "Deep forensics",
  fusing: "Weighing evidence",
  done: "Complete",
};

const PHASE_COLOR: Record<Phase, string> = {
  idle: "text-iris-ink bg-bloom",
  decoding: "text-blue-700 bg-blue-50",
  tier1: "text-blue-700 bg-blue-50",
  gate: "text-amber-700 bg-amber-50",
  tier2: "text-violet-700 bg-violet-50",
  fusing: "text-violet-700 bg-violet-50",
  done: "text-emerald-700 bg-emerald-50",
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
    <div className="flex flex-wrap items-center gap-2">
      {MODULES.map((m) => {
        const done = reported.has(m.key);
        return (
          <span
            key={m.key}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-label font-medium border transition-all",
              done
                ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                : "bg-bloom border-iris/40 text-iris-ink",
            )}
          >
            <span className={cn(
              "h-2 w-2 rounded-full transition-colors",
              done ? "bg-emerald-500" : "bg-iris/40",
            )} />
            {m.label}
          </span>
        );
      })}

      <span className="ml-auto inline-flex items-center gap-2">
        <span className={cn("rounded-full px-3 py-1.5 text-label font-medium", PHASE_COLOR[phase])}>
          {PHASE_LABEL[phase]}
        </span>
        {elapsedMs !== null && phase === "done" && (
          <span className="rounded-full bg-emerald-50 border border-emerald-200 px-3 py-1.5 text-label font-medium text-emerald-700">
            <span className="data">{elapsedMs}</span> ms
          </span>
        )}
      </span>
    </div>
  );
}
