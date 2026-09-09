/**
 * The evidence list — the exit gate for the whole project.
 */
import { useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import type { Finding, Signal } from "../contracts";
import { orderEvidence, type EvidenceRow } from "../domain/ordering";
import { TRUST_STYLE } from "../domain/trustClass";
import { TrustMark } from "./marks/TrustMark";
import { ChevronIcon } from "./marks/Icon";
import { useScreening } from "../store/screening";
import { cn } from "../lib/utils";

const PAIR = /^(.*?)\s([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Z0-9<]{6,})\s(.*?)\s([0-9]{4}-[0-9]{2}-[0-9]{2}|[A-Z0-9<]{6,})(.*)$/;

function EvidenceText({ text }: { text: string }) {
  const m = PAIR.exec(text);
  if (!m) return <span>{text}</span>;
  const [, lead, a, mid, b, tail] = m;
  return (
    <>
      <span>{lead}</span>
      <span className="mt-1 block">
        <span className="data rounded bg-slate-100 px-1.5 py-0.5 text-sm">{a}</span>
      </span>
      <span className="block text-iris-ink text-sm">{mid}</span>
      <span className="block">
        <span className="data rounded bg-slate-100 px-1.5 py-0.5 text-sm">{b}</span>
      </span>
      {tail.trim() ? <span className="block">{tail.trim()}</span> : null}
    </>
  );
}

function Row({ row, index }: { row: EvidenceRow; index: number }) {
  const reduce = useReducedMotion();
  const [open, setOpen] = useState(false);
  const setActiveAnchor = useScreening((s) => s.setActiveAnchor);
  const activeAnchor = useScreening((s) => s.activeAnchor);

  const { trust, anchor, mark, body, supporting, emphatic } = describe(row);
  const style = TRUST_STYLE[trust];
  const isActive = anchor !== null && activeAnchor === anchor;

  return (
    <motion.li
      initial={reduce ? false : { opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: reduce ? 0 : Math.min(index * 0.05, 0.4) }}
      className={cn(
        "group rounded-[var(--radius-md)] border border-transparent px-4 py-4 transition-all",
        isActive ? "border-guilloche/20 bg-guilloche/5" : "hover:bg-bloom/60 hover:border-iris/30",
      )}
      onMouseEnter={() => anchor && setActiveAnchor(anchor)}
      onMouseLeave={() => setActiveAnchor(null)}
      onFocus={() => anchor && setActiveAnchor(anchor)}
      onBlur={() => setActiveAnchor(null)}
    >
      <div className="flex gap-3">
        {/* Trust mark in a small rounded icon container */}
        <span
          className={cn(
            "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-sm)]",
            TRUST_STYLE[mark].badge,
          )}
          title={style.gloss}
        >
          <TrustMark trust={mark} size={14} />
        </span>

        <div className="min-w-0 flex-1">
          <p className={cn("leading-snug text-[length:var(--text-body)]", emphatic && "font-semibold text-intaglio")}>
            {body}
          </p>

          <div className="mt-1.5 flex items-center gap-2">
            <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium", TRUST_STYLE[trust].badge)}>
              {style.label}
            </span>
          </div>

          {supporting.length > 0 && (
            <>
              <button
                type="button"
                onClick={() => setOpen((v) => !v)}
                aria-expanded={open}
                className="mt-2 inline-flex items-center gap-1 text-label text-guilloche font-medium hover:underline underline-offset-4"
              >
                <motion.span
                  className="inline-flex h-3 w-3 items-center justify-center rounded-full border border-guilloche/50"
                  animate={{ rotate: open ? 90 : 0 }}
                  transition={{ duration: reduce ? 0 : 0.15 }}
                >
                  <ChevronIcon size={7} />
                </motion.span>
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
                    className="mt-3 overflow-hidden space-y-1"
                  >
                    {supporting.map((s) => (
                      <li key={s.id} className="flex gap-2 rounded-[var(--radius-sm)] bg-bloom/50 px-3 py-2 text-iris-ink">
                        <span className="mt-0.5 shrink-0">
                          <TrustMark trust={s.trust_class} size={12} />
                        </span>
                        <span className="text-label">{s.evidence}</span>
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
        supporting: (row.finding?.supporting ?? []).filter((s) => s.id !== row.signal.id),
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

export function EvidenceList({ findings, signals }: { findings: Finding[]; signals: Signal[] }) {
  const rows = orderEvidence(findings, signals);

  if (rows.length === 0) {
    return (
      <div className="mt-4 rounded-[var(--radius-md)] border border-iris/30 bg-bloom/40 px-5 py-8 text-center">
        <p className="text-iris-ink">Nothing to report yet. Checks are still running.</p>
      </div>
    );
  }

  return (
    <ul className="mt-3 -mx-4 divide-y divide-iris/20">
      {rows.map((row, i) => (
        <Row key={row.key} row={row} index={i} />
      ))}
    </ul>
  );
}
