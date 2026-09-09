/**
 * The pipeline stepper.
 *
 * Five stages, in order: Read, Validate, Tamper, Face, Complete. A stage is
 * "reached" the instant its first signal arrives — same rule the old boolean
 * pills used — but now rendered as one connected bar with real elapsed time
 * per stage, ticking live while the run is in progress.
 *
 * The timestamps come from `Screening.tsx`'s `stageTimes` ref, recorded at
 * the moment each event actually arrives over the wire. That is real,
 * honest wall-clock time — not the isolated compute cost of that module
 * alone (queueing, decode, and tier1's other three modules all bleed into
 * it), so the copy says "reached", never "took".
 */
import { useEffect, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import type { ModuleName, Phase, Signal } from "../contracts";
import { CheckIcon } from "./marks/Icon";
import { cn } from "../lib/utils";

type StageKey = ModuleName | "done";

const STAGES: { key: StageKey; label: string }[] = [
  { key: "extraction", label: "Read" },
  { key: "validation", label: "Validate" },
  { key: "tamper", label: "Tamper" },
  { key: "face", label: "Face" },
  { key: "done", label: "Complete" },
];

function seconds(ms: number): string {
  return (ms / 1000).toFixed(1);
}

export function StreamStatus({
  phase,
  signals,
  stageTimes,
  runStartedAt,
}: {
  phase: Phase;
  signals: Signal[];
  stageTimes: Partial<Record<StageKey, number>>;
  runStartedAt: number;
}) {
  const reduce = useReducedMotion();
  const running = phase !== "idle" && phase !== "done";

  // Live tick, local to this component only — a ticking total up in
  // Screening.tsx would re-render the whole screen 10x/sec for nothing.
  const [, tick] = useState(0);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => tick((n) => n + 1), 100);
    return () => clearInterval(id);
  }, [running]);

  const reached = (key: StageKey) => stageTimes[key] !== undefined;
  const activeIndex = phase === "idle" ? -1 : STAGES.findIndex((s) => !reached(s.key));
  const liveMs = stageTimes.done ?? (phase === "idle" ? 0 : performance.now() - runStartedAt);
  const escalated = signals.some((sig) => sig.tier === 2);

  return (
    <div className="flex w-full flex-wrap items-center gap-x-6 gap-y-3">
      <div className="flex flex-1 items-start min-w-[280px]">
        {STAGES.map((stage, i) => {
          const isReached = reached(stage.key);
          const isActive = i === activeIndex && running;
          const nextReached = i < STAGES.length - 1 && reached(STAGES[i + 1].key);
          return (
            <div
              key={stage.key}
              className="flex items-start"
              style={{ flex: i < STAGES.length - 1 ? "1 1 0%" : "0 0 auto" }}
            >
              <div className="flex flex-col items-center">
                <div className="relative flex h-[18px] w-[18px] shrink-0 items-center justify-center">
                  {isActive && !reduce && (
                    <span className="absolute inline-flex h-[18px] w-[18px] animate-ping rounded-full bg-guilloche/30" />
                  )}
                  <span
                    className={cn(
                      "relative flex h-[18px] w-[18px] items-center justify-center rounded-full transition-colors duration-300",
                      isReached ? "bg-clear" : isActive ? "bg-guilloche" : "bg-iris/30",
                    )}
                  >
                    {isReached ? (
                      <motion.span
                        initial={reduce ? false : { scale: 0.4, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ type: "spring", stiffness: 420, damping: 22 }}
                        className="text-white"
                      >
                        <CheckIcon size={10} />
                      </motion.span>
                    ) : (
                      <span className={cn("h-1.5 w-1.5 rounded-full", isActive ? "bg-white" : "bg-white/70")} />
                    )}
                  </span>
                </div>
                <span
                  className={cn(
                    "mt-1.5 whitespace-nowrap text-label font-medium",
                    isReached ? "text-intaglio" : isActive ? "text-guilloche" : "text-iris-ink",
                  )}
                >
                  {stage.label}
                </span>
                <span className="data whitespace-nowrap text-[11px] text-iris-ink" aria-hidden={!isReached}>
                  {isReached ? `reached ${seconds(stageTimes[stage.key]!)}s` : " "}
                </span>
              </div>

              {i < STAGES.length - 1 && (
                <div className="relative mx-2 mt-[8px] h-[2px] flex-1 overflow-hidden rounded-full bg-iris/20">
                  <motion.div
                    className="h-full rounded-full bg-clear"
                    style={{ transformOrigin: "left" }}
                    initial={false}
                    animate={{ scaleX: nextReached ? 1 : 0 }}
                    transition={{ duration: reduce ? 0 : 0.3, ease: [0.2, 0, 0, 1] }}
                  />
                  {isActive && !reduce && (
                    <motion.div
                      className="absolute inset-0 bg-gradient-to-r from-transparent via-guilloche/60 to-transparent"
                      animate={{ x: ["-100%", "200%"] }}
                      transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
                    />
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="flex shrink-0 items-center gap-2">
        {escalated && (
          <span className="rounded-full border border-probabilistic/30 bg-probabilistic/10 px-2.5 py-1 text-label font-medium text-probabilistic">
            Escalated
          </span>
        )}
        <span className="rounded-full bg-bloom border border-iris/40 px-3 py-1.5 text-label font-medium text-intaglio">
          <span className="data">{seconds(liveMs)}s</span>{" "}
          <span
            className="text-iris-ink"
            aria-live={phase === "done" ? "polite" : undefined}
          >
            {phase === "done" ? (escalated ? "total · escalated" : "total") : "elapsed"}
          </span>
        </span>
      </div>
    </div>
  );
}
