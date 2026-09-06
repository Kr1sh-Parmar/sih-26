/**
 * The audit trail, and re-scoring.
 *
 * "Decisions get challenged months later" (context/CONTEXT.md §3). So the full
 * signal list is stored as JSONB, not just the cards — cards are a view. When a
 * weight changes, a historical event can be re-scored from what was recorded
 * without re-running a single model, which is the only way two verdicts months
 * apart stay comparable.
 *
 * Never shows a raw identity number. Salted hash plus last four digits, per
 * CLAUDE.md hard rule #5 — and that applies to fixtures too.
 */
import { useMemo, useState } from "react";
import type { Band, Signal } from "../contracts";
import { fixture, FIXTURES, type FixtureName } from "../transport/mockSocket";
import { useSettings } from "../store/settings";
import { TrustMark } from "../components/marks/TrustMark";
import { cn } from "../lib/utils";

interface AuditEvent {
  id: string;
  at: string;
  docType: string;
  last4: string;
  hash: string;
  band: Band;
  score: number;
  coverage: number;
  signals: Signal[];
  officer: string;
}

const BAND_WORD: Record<Band, string> = {
  GREEN: "CLEAR",
  AMBER: "SECONDARY",
  RED: "DETAIN",
};
const BAND_INK: Record<Band, string> = {
  GREEN: "text-clear",
  AMBER: "text-secondary-ink",
  RED: "text-detain",
};

/** Stand-in for GET /events. The shape matches screening_events in
 *  context/CONTRACTS.md §8, minus the columns the console must never render. */
function buildEvents(): AuditEvent[] {
  const base = Date.now() - 1000 * 60 * 47;
  const order: FixtureName[] = ["green", "red", "crossdoc", "amber", "green", "green"];
  return order.map((key, i) => {
    const doc = fixture(key);
    const idNumber =
      doc.fields.find((f) => f.name === "id_number")?.value ?? "00000000";
    return {
      id: `${(base + i * 421_000).toString(36)}`,
      at: new Date(base + i * 421_000).toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }),
      docType: doc.meta.doc_type,
      last4: idNumber.slice(-4),
      // A salted hash is computed server-side; this is a stable stand-in so the
      // column exists and nobody is tempted to put the real number here later.
      hash: `sha256:${(idNumber + key).split("").reduce((a, c) => (a * 33 + c.charCodeAt(0)) >>> 0, 5381).toString(16).padStart(8, "0")}`,
      band: doc.verdict.band,
      score: doc.verdict.score,
      coverage: doc.verdict.coverage,
      signals: doc.signals,
      officer: "4471",
    };
  });
}

/**
 * Re-score from the stored signals alone.
 *
 * This is a demonstration of the mechanism, not the scorer: real fusion lives
 * in fusion/score.py and is the only thing allowed to produce a verdict. What
 * this shows is that the stored record is sufficient — every input the scorer
 * needs was written down.
 */
function rescore(
  e: AuditEvent,
  bands: { amberAt: number; redAt: number; coverageFloor: number },
): { band: Band; reason: string } {
  const hard = e.signals.find((s) => s.hard_fail && s.verdict === "fail");
  if (hard) return { band: "RED", reason: `hard fail — ${hard.id}` };
  if (e.coverage < bands.coverageFloor)
    return {
      band: "AMBER",
      reason: `coverage ${Math.round(e.coverage * 100)}% is below the ${Math.round(bands.coverageFloor * 100)}% floor`,
    };
  if (e.score >= bands.redAt) return { band: "RED", reason: `score ${e.score.toFixed(2)}` };
  if (e.score >= bands.amberAt)
    return { band: "AMBER", reason: `score ${e.score.toFixed(2)}` };
  return { band: "GREEN", reason: `score ${e.score.toFixed(2)}` };
}

export function Audit() {
  const { amberAt, redAt, coverageFloor } = useSettings();
  const events = useMemo(buildEvents, []);
  const [openId, setOpenId] = useState<string | null>(null);

  const open = events.find((e) => e.id === openId) ?? null;
  const changed = events.filter(
    (e) => rescore(e, { amberAt, redAt, coverageFloor }).band !== e.band,
  );

  return (
    <div className="mx-auto w-full max-w-6xl px-8 py-8">
      <h1 className="text-[length:var(--text-screen)] font-semibold">Audit trail</h1>
      <p className="mt-1 max-w-[44rem] text-iris-ink">
        Every screening keeps its complete signal list, not just the cards it
        produced. Change a band on the operating point screen and every event
        here re-scores from what was recorded — no model runs again.
      </p>

      {changed.length > 0 && (
        <p className="mt-6 border-l-2 border-guilloche bg-guilloche/25 px-4 py-3">
          The current bands would change{" "}
          <span className="data">{changed.length}</span> of these{" "}
          <span className="data">{events.length}</span> verdicts.
        </p>
      )}

      <table className="mt-8 w-full">
        <thead>
          <tr className="border-b border-intaglio text-left text-label text-iris-ink">
            <th className="py-2 font-medium">Time</th>
            <th className="py-2 font-medium">Document</th>
            <th className="py-2 font-medium">Number</th>
            <th className="py-2 font-medium">Recorded</th>
            <th className="py-2 font-medium">Re-scored now</th>
            <th className="py-2 font-medium">Officer</th>
            <th className="py-2" />
          </tr>
        </thead>
        <tbody>
          {events.map((e) => {
            const re = rescore(e, { amberAt, redAt, coverageFloor });
            const differs = re.band !== e.band;
            return (
              <tr
                key={e.id}
                className={cn(
                  "border-b border-iris/50",
                  openId === e.id && "bg-bloom/60",
                )}
              >
                <td className="py-3 data">{e.at}</td>
                <td className="py-3">{e.docType}</td>
                <td className="py-3 data text-iris-ink">
                  ••••{e.last4}
                  <span className="ml-2 text-label">{e.hash}</span>
                </td>
                <td className={cn("py-3 font-medium", BAND_INK[e.band])}>
                  {BAND_WORD[e.band]}
                </td>
                <td className="py-3">
                  <span className={cn("font-medium", BAND_INK[re.band])}>
                    {BAND_WORD[re.band]}
                  </span>
                  {differs && (
                    <span className="ml-2 text-label text-iris-ink">changed</span>
                  )}
                  <span className="ml-2 text-label text-iris-ink">{re.reason}</span>
                </td>
                <td className="py-3 data text-iris-ink">{e.officer}</td>
                <td className="py-3 text-right">
                  <button
                    type="button"
                    onClick={() => setOpenId(openId === e.id ? null : e.id)}
                    className="text-label text-iris-ink underline-offset-4 hover:underline"
                  >
                    {openId === e.id ? "Close" : "Open"}
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {open && (
        <section className="mt-10 border-t-2 border-intaglio pt-6">
          <h2 className="text-[length:var(--text-evidence)]">
            Stored signals — {open.docType}, {open.at}
          </h2>
          <p className="mt-1 text-label text-iris-ink">
            {open.signals.length} signals. This is the record a re-score reads;
            nothing here is recomputed from the image.
          </p>

          <ul className="mt-5">
            {open.signals.map((s) => (
              <li
                key={s.id}
                className="grid grid-cols-[1.25rem_16rem_5rem_1fr] items-baseline gap-3 border-b border-iris/40 py-2"
              >
                <span
                  className={
                    s.trust_class === "cryptographic" ? "text-intaglio" : "text-iris-ink"
                  }
                >
                  <TrustMark trust={s.trust_class} size={13} />
                </span>
                <span className="data text-label">{s.id}</span>
                <span
                  className={cn(
                    "text-label",
                    s.verdict === "fail" && "text-detain font-medium",
                    s.verdict === "inconclusive" && "text-secondary-ink",
                    s.verdict === "not_applicable" && "text-iris-ink",
                  )}
                >
                  {s.verdict}
                </span>
                <span className="text-iris-ink">{s.evidence}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="mt-10 text-label text-iris-ink">
        Reading {Object.keys(FIXTURES).length} rehearsed cases from local
        fixtures. Against a live backend this list comes from{" "}
        <span className="data">GET /events</span> and re-scoring from{" "}
        <span className="data">POST /rescore</span>, which is the same endpoint
        the operating point screen calls.
      </p>
    </div>
  );
}
