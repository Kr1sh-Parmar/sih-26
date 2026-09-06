/**
 * The verdict.
 *
 * Three rules, all from context/MODULES.md and context/CLAUDE.md:
 *   - Never a bare percentage. Score appears with reasons or not at all.
 *   - The WORD carries the verdict. Colour reinforces it. An officer with
 *     deuteranopia, or a projector with bad gamma, still reads it.
 *   - Coverage is shown beside the score, because a low-coverage AMBER means
 *     something completely different from a low-score AMBER.
 *
 * The band names are what the officer does next, not the colour of a light.
 */
import { motion, useReducedMotion } from "motion/react";
import type { Band } from "../contracts";
import { cn } from "../lib/utils";

const BAND = {
  GREEN: {
    word: "CLEAR",
    action: "No further inspection required",
    ink: "text-clear",
    rule: "bg-clear",
  },
  AMBER: {
    word: "SECONDARY",
    action: "Send for secondary inspection",
    ink: "text-secondary-ink",
    rule: "bg-guilloche",
  },
  RED: {
    word: "DETAIN",
    action: "Detain for manual review",
    ink: "text-detain",
    rule: "bg-detain",
  },
} as const;

interface Props {
  band: Band | null;
  score: number | null;
  coverage: number | null;
  /** Set when fusion returned AMBER because coverage fell below the floor,
   *  rather than because the score was middling. Different problem, different
   *  instruction to the officer. */
  coverageFloor?: number;
}

export function VerdictBand({ band, score, coverage, coverageFloor = 0.7 }: Props) {
  const reduce = useReducedMotion();

  if (!band) {
    return (
      <div className="min-h-[8.5rem]">
        <div
          className="text-[length:var(--text-verdict)] leading-[0.92] font-bold text-iris/60"
          style={{ fontStretch: "125%" }}
        >
          READING
        </div>
        <div className="mt-3 h-1.5 w-full bg-iris/25" />
        <p className="mt-3 text-iris-ink">Checks are still running.</p>
      </div>
    );
  }

  const b = BAND[band];
  const short = coverage !== null && coverage < coverageFloor;

  return (
    <div className="min-h-[8.5rem]">
      <div
        className={cn(
          "text-[length:var(--text-verdict)] leading-[0.92] font-bold tracking-[-0.02em]",
          b.ink,
        )}
        style={{ fontStretch: "125%" }}
      >
        {b.word}
      </div>

      <motion.div
        className={cn("mt-3 h-1.5 w-full origin-left", b.rule)}
        initial={reduce ? false : { scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.24, ease: [0.2, 0, 0, 1] }}
      />

      <p className="mt-3 text-[length:var(--text-evidence)]">
        {short ? "Not enough evidence. Re-capture the document." : b.action}
      </p>

      <p className="mt-1 text-label text-iris-ink">
        <span className="data">{score?.toFixed(2) ?? "—"}</span> score
        <span className="mx-2 inline-block h-3 w-px translate-y-0.5 bg-iris" />
        <span className={cn("data", short && "text-detain")}>
          {coverage !== null ? `${Math.round(coverage * 100)}%` : "—"}
        </span>{" "}
        of the applicable checks ran
      </p>
    </div>
  );
}
