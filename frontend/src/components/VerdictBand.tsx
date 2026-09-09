/**
 * The verdict.
 * Word carries the verdict. Colour reinforces it.
 */
import { motion, useReducedMotion } from "motion/react";
import type { Band } from "../contracts";
import { cn } from "../lib/utils";

const BAND = {
  GREEN: {
    word: "CLEAR",
    action: "No further inspection required",
    ink: "text-emerald-700",
    bg: "bg-emerald-50",
    border: "border-emerald-200",
    bar: "bg-emerald-500",
    dot: "bg-emerald-500",
    badge: "bg-emerald-100 text-emerald-800",
  },
  AMBER: {
    word: "SECONDARY",
    action: "Send for secondary inspection",
    ink: "text-amber-700",
    bg: "bg-amber-50",
    border: "border-amber-200",
    bar: "bg-amber-500",
    dot: "bg-amber-500",
    badge: "bg-amber-100 text-amber-800",
  },
  RED: {
    word: "DETAIN",
    action: "Detain for manual review",
    ink: "text-red-600",
    bg: "bg-red-50",
    border: "border-red-200",
    bar: "bg-red-500",
    dot: "bg-red-500",
    badge: "bg-red-100 text-red-800",
  },
} as const;

interface Props {
  band: Band | null;
  score: number | null;
  coverage: number | null;
  coverageFloor?: number;
}

export function VerdictBand({ band, score, coverage, coverageFloor = 0.7 }: Props) {
  const reduce = useReducedMotion();

  if (!band) {
    return (
      <div className="rounded-[var(--radius-lg)] border border-iris/30 bg-bloom/40 p-6">
        <div className="flex items-center gap-3 mb-4">
          <span className="flex h-3 w-3 items-center justify-center">
            <span className="animate-ping absolute inline-flex h-3 w-3 rounded-full bg-iris/40" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-iris/60" />
          </span>
          <span className="text-label font-medium text-iris-ink">Analysing document…</span>
        </div>
        <div
          className="text-[length:var(--text-verdict)] leading-[0.92] font-bold text-iris/30 select-none"
          style={{ fontStretch: "125%" }}
        >
          ——
        </div>
        <div className="mt-4 h-1.5 w-full rounded-full bg-iris/20 overflow-hidden">
          <motion.div
            className="h-full rounded-full bg-iris/40"
            animate={{ x: ["-100%", "200%"] }}
            transition={{ repeat: Infinity, duration: 1.4, ease: "easeInOut" }}
            style={{ width: "40%" }}
          />
        </div>
        <p className="mt-3 text-iris-ink text-label">Checks are still running.</p>
      </div>
    );
  }

  const b = BAND[band];
  const short = coverage !== null && coverage < coverageFloor;

  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25 }}
      className={cn("rounded-[var(--radius-lg)] border p-6", b.bg, b.border)}
    >
      {/* Status dot + action label */}
      <div className="flex items-center gap-2 mb-3">
        <span className={cn("h-2.5 w-2.5 rounded-full", b.dot)} />
        <span className={cn("text-label font-medium", b.ink)}>
          {short ? "Insufficient evidence" : b.action}
        </span>
      </div>

      {/* The big verdict word */}
      <div
        className={cn("text-[length:var(--text-verdict)] leading-[0.88] font-bold tracking-[-0.03em]", b.ink)}
        style={{ fontStretch: "125%" }}
      >
        {b.word}
      </div>

      {/* Progress bar */}
      <motion.div
        className="mt-4 h-1 w-full rounded-full bg-black/10 overflow-hidden"
        initial={false}
      >
        <motion.div
          className={cn("h-full rounded-full origin-left", b.bar)}
          initial={reduce ? false : { scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.3, ease: [0.2, 0, 0, 1] }}
        />
      </motion.div>

      {/* Score & coverage row */}
      <div className="mt-4 flex items-center gap-3 flex-wrap">
        <span className={cn("inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-label font-medium", b.badge)}>
          <span className="opacity-70">score</span>
          <span className="data">{score?.toFixed(2) ?? "—"}</span>
        </span>
        <span className={cn(
          "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-label font-medium",
          short ? "bg-red-100 text-red-700" : b.badge,
        )}>
          <span className="opacity-70">coverage</span>
          <span className="data">{coverage !== null ? `${Math.round(coverage * 100)}%` : "—"}</span>
        </span>
      </div>
    </motion.div>
  );
}
