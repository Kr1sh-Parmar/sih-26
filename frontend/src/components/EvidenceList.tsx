/**
 * The evidence list — the exit gate for the whole project:
 *
 *   "A person who has never seen the system can read a RED verdict and say
 *    why."  (context/ROADMAP.md, Phase 4)
 *
 * Order comes from domain/ordering.ts, which implements CONTRACTS.md §7.
 * Trust class is carried by a mark and the weight of the rule beneath each
 * row, never by colour — colour belongs to the verdict.
 *
 * The one motion moment in the app lives here: as each row arrives its rule
 * draws left to right and the text sets behind it, so the list reads as a
 * record being written rather than a page appearing.
 */
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { Finding, Signal } from "../contracts";
import { orderEvidence, type EvidenceRow } from "../domain/ordering";
import { TRUST_STYLE } from "../domain/trustClass";
import { TrustMark } from "./marks/TrustMark";
import { useScreening } from "../store/screening";
import { cn } from "../lib/utils";

/** Pull the two compared values out of an evidence string so they can be set
 *  in mono on their own lines. Scene 2 requires the officer to read both. */
const PAIR = /^(.*?)\s([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Z0-9<]{6,})\s(.*?)\s([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Z0-9<]{6,})(.*)$/;

function EvidenceText({ text }: { text: string }) {
  const m = PAIR.exec(text);
  if (!m) return <span>{text}</span>;
  const [, lead, a, mid, b, tail] = m;
  return (
    <>
      <span>{lead}</span>
      <span className="mt-1 block">
        <span className="data">{a}</span>
      </span>
      <span className="block text-iris-ink">{mid}</span>
      <span className="block">
        <span className="data">{b}</span>
      </span>
      {tail.trim() ? <span className="block">{tail.trim()}</span> : null}
    </>
  );
}

function Row({
  row,
  index,
}: {
  row: EvidenceRow;
  index: number;
}) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const setActiveAnchor = useScreening((s) => s.setActiveAnchor);
  const activeAnchor = useScreening((s) => s.activeAnchor);

  const { trust, anchor, mark, body, supporting, emphatic } = describe(row);
  const style = TRUST_STYLE[trust];
  const isActive = anchor !== null && activeAnchor === anchor;

  return (
    <motion.li
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.18, delay: reduce ? 0 : Math.min(index * 0.04, 0.4) }}
      className={cn(
        "group relative pt-4 pb-4",
        style.rule,
        isActive && "bg-bloom/70",
      )}
      onMouseEnter={() => anchor && setActiveAnchor(anchor)}
      onMouseLeave={() => setActiveAnchor(null)}
      onFocus={() => anchor && setActiveAnchor(anchor)}
      onBlur={() => setActiveAnchor(null)}
    >
      {/* the rule draws itself */}
      {!reduce && (
        <motion.span
          aria-hidden
          className="absolute -top-px left-0 h-px bg-paper"
          initial={{ width: "100%" }}
          animate={{ width: "0%" }}
          transition={{ duration: 0.12, delay: Math.min(index * 0.04, 0.4) }}
        />
      )}

      <div className="flex gap-3">
        <span
          className={cn("mt-1 shrink-0", mark === "cryptographic" ? "text-intaglio" : "text-iris-ink")}
          title={style.gloss}
        >
          <TrustMark trust={mark} />
        </span>

        <div className="min-w-0 flex-1">
          <p
            className={cn(
              "text-[length:var(--text-evidence)] leading-snug",
              emphatic && "font-semibold",
            )}
          >
            {body}
          </p>

          <p className="mt-1 text-label text-iris-ink">{style.label}</p>

          {supporting.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                className="mt-2 text-label text-iris-ink underline-offset-4 hover:underline"
              >
                {open ? "Hide" : "Show"} {supporting.length} supporting{" "}
                {supporting.length === 1 ? "check" : "checks"}
              </button>
              <AnimatePresence initial={false}>
                {open && (
                  <motion.ul
                    initial={reduce ? false : { height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="mt-2 overflow-hidden"
                  >
                    {supporting.map((s) => (
                      <li key={s.id} className="flex gap-2 py-1 text-iris-ink">
                        <span className="mt-0.5 shrink-0">
                          <TrustMark trust={s.trust_class} size={12} />
                        </span>
                        <span>{s.evidence}</span>
                      </li>
                    ))}
                  </motion.ul>
                )}
              </AnimatePresence>
            </>
          )}
        </div>
      </div>
    </motion.li>
  );
}

function describe(row: EvidenceRow) {
  switch (row.kind) {
    case "hard_fail":
      return {
        trust: row.signal.trust_class,
        mark: row.signal.trust_class,
        anchor: row.signal.anchor,
        body: <EvidenceText text={row.signal.evidence} />,
        // Corroboration for the same anchor rides along under the triangle.
        supporting: (row.finding?.supporting ?? []).filter(
          (s) => s.id !== row.signal.id,
        ),
        emphatic: true,
      };
    case "finding":
      return {
        trust: row.finding.trust_class,
        mark: row.finding.trust_class,
        anchor: row.finding.anchor,
        body: <span>{row.finding.headline}</span>,
        supporting: row.finding.supporting ?? [],
        emphatic: row.finding.severity > 0,
      };
    case "gap":
      return {
        trust: row.signal.trust_class,
        mark: "unverified" as const,
        anchor: row.signal.anchor,
        body: <span>Could not evaluate — {row.signal.evidence}</span>,
        supporting: [] as Signal[],
        emphatic: false,
      };
    case "crypto_pass":
      return {
        trust: "cryptographic" as const,
        mark: "cryptographic" as const,
        anchor: row.signal.anchor,
        body: <span>{row.signal.evidence}</span>,
        supporting: [] as Signal[],
        emphatic: false,
      };
    case "passed":
      return {
        trust: "probabilistic" as const,
        mark: "probabilistic" as const,
        anchor: null,
        body: (
          <span>
            {row.count} further {row.count === 1 ? "check" : "checks"} passed
          </span>
        ),
        supporting: row.signals,
        emphatic: false,
      };
  }
}

export function EvidenceList({
  findings,
  signals,
}: {
  findings: Finding[];
  signals: Signal[];
}) {
  const rows = orderEvidence(findings, signals);

  if (rows.length === 0) {
    return (
      <p className="pt-4 text-iris-ink">
        Nothing to report yet. Checks are still running.
      </p>
    );
  }

  return (
    <ul className="mt-6">
      {rows.map((row, i) => (
        <Row key={row.key} row={row} index={i} />
      ))}
    </ul>
  );
}
