/**
 * The audit trail, and re-scoring.
 *
 * "Decisions get challenged months later" (context/CONTEXT.md §3). So the full
 * signal list is stored as JSONB, not just the cards — cards are a view. When a
 * weight changes, a historical event can be re-scored from what was recorded
 * without re-running a single model, which is the only way two verdicts months
 * apart stay comparable.
 *
 * The re-score is a server call, `POST /rescore`. This screen must not carry
 * its own copy of the scoring rules: two implementations of a verdict drift,
 * and the one in the browser would end up disagreeing with the audit log it
 * is meant to explain.
 *
 * Never shows a raw identity number. Salted hash plus last four digits — the
 * API does not return one either, because the database does not store one.
 */
import { useEffect, useMemo, useState } from "react";
import type { Band } from "../contracts";
import {
  fetchEvents,
  rescoreEvents,
  type AuditEvent,
  type RescoreResult,
} from "../transport/socket";
import { fixture, FIXTURES, type FixtureName } from "../transport/mockSocket";
import { useMode } from "../transport/mode";
import { useSettings } from "../store/settings";
import { ModeBadge } from "../components/ModeBadge";
import { TrustMark, OpenCircle } from "../components/marks/TrustMark";
import { CrossIcon } from "../components/marks/Icon";
import { docLabel } from "../domain/docType";
import { TRUST_STYLE } from "../domain/trustClass";
import { cn } from "../lib/utils";

const BAND_WORD: Record<Band, string> = {
  GREEN: "CLEAR",
  AMBER: "SECONDARY",
  RED: "DETAIN",
};

const BAND_PILL: Record<Band, string> = {
  GREEN: "bg-clear/10 text-clear border border-clear/30",
  AMBER: "bg-secondary-ink/10 text-secondary-ink border border-secondary-ink/30",
  RED: "bg-detain/10 text-detain border border-detain/30",
};

/**
 * Rehearsed events, for when there is no backend.
 *
 * Shaped exactly like `GET /events` so the table has one code path. These
 * carry no re-score: without the server there is no scorer, and inventing one
 * here is the thing this screen must not do.
 */
function fixtureEvents(): AuditEvent[] {
  const base = Date.now() - 1000 * 60 * 47;
  const order: FixtureName[] = ["green", "red", "crossdoc", "amber", "green", "green"];
  return order.map((key, i) => {
    const doc = fixture(key);
    const number = doc.fields.find((f) => f.name === "id_number")?.value ?? "00000000";
    return {
      id: `${(base + i * 421_000).toString(36)}`,
      session_id: "rehearsal",
      doc_type: doc.meta.doc_type,
      created_at: new Date(base + i * 421_000).toISOString(),
      band: doc.verdict.band,
      score: doc.verdict.score,
      coverage: doc.verdict.coverage,
      id_number_hash: null,
      id_number_last4: number.slice(-4),
      officer_id: "4471",
      model_versions: {},
      signed: doc.signals.some(
        (s) => s.id === "validation.signature.valid" && s.verdict === "pass",
      ),
      signals: doc.signals,
    };
  });
}

function clockOf(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? iso
    : at.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function VerdictPill({ band, label }: { band: Band; label?: string }) {
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-bold tracking-wide", BAND_PILL[band])}>
      {label ?? BAND_WORD[band]}
    </span>
  );
}

export function Audit() {
  const mode = useMode();
  const { amberAt, redAt, coverageFloor } = useSettings();

  const [events, setEvents] = useState<AuditEvent[] | null>(null);
  const [total, setTotal] = useState(0);
  const [rescored, setRescored] = useState<Record<string, RescoreResult>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  const fallback = useMemo(fixtureEvents, []);

  useEffect(() => {
    if (mode === "probing") return;
    if (mode === "fixtures") {
      setEvents(fallback);
      setTotal(fallback.length);
      return;
    }
    let alive = true;
    fetchEvents(25)
      .then((page) => {
        if (!alive) return;
        setEvents(page.events);
        setTotal(page.total);
      })
      .catch((error: Error) => alive && setProblem(error.message));
    return () => {
      alive = false;
    };
  }, [mode, fallback]);

  // Re-score the listed page whenever the operating point moves. One request
  // for the whole page — the server is still the only thing allowed to
  // produce a verdict. Results are keyed by their own `event_id`, never by
  // array position, so a page the server returns short does not silently
  // relabel the rows beneath the missing one. Debounced, because those three
  // numbers are on sliders and a drag would otherwise fire one request per
  // animation frame.
  useEffect(() => {
    if (mode !== "live" || !events?.length) return;
    let alive = true;
    const bands = {
      green_below: amberAt,
      amber_below: redAt,
      coverage_floor: coverageFloor,
    };
    const ids = events.map((e) => e.id);
    const timer = setTimeout(() => {
      rescoreEvents(ids, bands)
        .then((results) => {
          if (!alive) return;
          const next: Record<string, RescoreResult> = {};
          for (const r of results) next[r.event_id] = r;
          setRescored(next);
        })
        .catch(() => {
          // The table still shows the recorded verdict, which is the one that
          // was actually acted on at the counter. A failed re-score must leave
          // that standing rather than blank the page.
        });
    }, 150);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [mode, events, amberAt, redAt, coverageFloor]);

  const open = events?.find((e) => e.id === openId) ?? null;
  const changed = Object.values(rescored).filter((r) => r.changed);

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-8">
      {/* Page header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-[length:var(--text-screen)] font-semibold tracking-[-0.02em]">Audit trail</h1>
          <p className="mt-1 max-w-[44rem] text-iris-ink">
            Every screening keeps its complete signal list, not just the cards it
            produced. Change a band on the operating point screen and every event
            here re-scores from what was recorded — no model runs again.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ModeBadge mode={mode} />
          <div className="shrink-0 rounded-[var(--radius-md)] border border-iris/40 bg-bloom/60 px-4 py-3 text-center">
            <p className="data text-[length:var(--text-screen)] font-bold leading-none text-intaglio">{events?.length ?? 0}</p>
            <p className="mt-1 text-label text-iris-ink">events</p>
          </div>
        </div>
      </div>

      {problem && (
        <div className="mt-6 flex items-center gap-3 rounded-[var(--radius-md)] border border-red-200 bg-red-50 px-5 py-3.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-500 text-white">
            <CrossIcon size={11} />
          </span>
          <p className="text-red-800">{problem}</p>
        </div>
      )}

      {mode === "fixtures" && (
        <div className="mt-6 flex items-center gap-3 rounded-[var(--radius-md)] border border-amber-200 bg-amber-50 px-5 py-3.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center text-amber-600">
            <OpenCircle size={16} />
          </span>
          <p className="text-amber-800">
            These are rehearsed cases read from local fixtures. Re-scoring needs
            the screening service, because the verdict is only ever produced
            server-side — there is no second scorer in this console.
          </p>
        </div>
      )}

      {changed.length > 0 && (
        <div className="mt-6 flex items-center gap-3 rounded-[var(--radius-md)] border border-amber-200 bg-amber-50 px-5 py-3.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-500 text-white text-xs font-bold">!</span>
          <p className="text-amber-800">
            The current bands would change{" "}
            <span className="font-bold">{changed.length}</span> of these{" "}
            <span className="font-bold">{events?.length ?? 0}</span> verdicts.
          </p>
        </div>
      )}

      {events === null ? (
        <p className="mt-8 text-iris-ink">Reading the audit trail…</p>
      ) : events.length === 0 ? (
        <p className="mt-8 text-iris-ink">Nothing has been screened on this workstation yet.</p>
      ) : (
        <div className="mt-8 rounded-[var(--radius-lg)] border border-iris/40 overflow-hidden" style={{ boxShadow: "var(--shadow-md)" }}>
          <table className="w-full">
            <thead>
              <tr className="bg-bloom/80 border-b border-iris/40 text-left text-label text-iris-ink">
                <th className="py-3.5 pl-5 font-semibold">Time</th>
                <th className="py-3.5 font-semibold">Document</th>
                <th className="py-3.5 font-semibold">Number</th>
                <th className="py-3.5 font-semibold">Recorded</th>
                <th className="py-3.5 font-semibold">Re-scored now</th>
                <th className="py-3.5 font-semibold">Officer</th>
                <th className="py-3.5 pr-5" />
              </tr>
            </thead>
            <tbody>
              {events.map((e) => {
                const re = rescored[e.id];
                return (
                  <tr
                    key={e.id}
                    className={cn(
                      "border-t border-iris/20 transition-colors",
                      openId === e.id ? "bg-guilloche/5" : "hover:bg-bloom/50",
                    )}
                  >
                    <td className="py-4 pl-5">
                      <span className="data text-[length:var(--text-body)] font-medium">{clockOf(e.created_at)}</span>
                    </td>
                    <td className="py-4">
                      <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-label font-medium text-slate-600">
                        {docLabel(e.doc_type)}
                      </span>
                    </td>
                    <td className="py-4">
                      <span className="data text-iris-ink">••••{e.id_number_last4 ?? "————"}</span>
                      {e.id_number_hash && (
                        <span className="ml-2 font-mono text-[11px] text-iris/70">sha256:{e.id_number_hash.slice(0, 8)}</span>
                      )}
                    </td>
                    <td className="py-4">
                      <VerdictPill band={e.band} />
                    </td>
                    <td className="py-4">
                      {re ? (
                        <div className="flex flex-wrap items-center gap-2">
                          <VerdictPill band={re.rescored.band} />
                          {re.changed && (
                            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700 border border-amber-200">
                              changed
                            </span>
                          )}
                          {re.rescored.reason && (
                            <span className="text-label text-iris-ink">{re.rescored.reason}</span>
                          )}
                        </div>
                      ) : (
                        <span className="text-label text-iris-ink">
                          {mode === "live" ? "re-scoring…" : "needs the service"}
                        </span>
                      )}
                    </td>
                    <td className="py-4">
                      <span className="data text-label text-iris-ink">{e.officer_id ?? "—"}</span>
                    </td>
                    <td className="py-4 pr-5 text-right">
                      <button
                        type="button"
                        onClick={() => setOpenId(openId === e.id ? null : e.id)}
                        className={cn(
                          "rounded-[var(--radius-sm)] px-3 py-1.5 text-label font-medium transition-all",
                          openId === e.id
                            ? "bg-guilloche text-white"
                            : "bg-bloom text-iris-ink hover:bg-guilloche/10 hover:text-guilloche border border-iris/40",
                        )}
                      >
                        {openId === e.id ? "Close" : "Open"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {open && (
        <section className="mt-8 rounded-[var(--radius-lg)] border border-iris/40 bg-white p-6" style={{ boxShadow: "var(--shadow-md)" }}>
          <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
            <div>
              <h2 className="text-[length:var(--text-evidence)] font-semibold">Stored signals</h2>
              <p className="mt-0.5 text-label text-iris-ink">
                {docLabel(open.doc_type)} · {clockOf(open.created_at)} · {open.signals.length} signals
              </p>
            </div>
            <span className="text-label text-iris-ink bg-bloom rounded-full px-3 py-1">
              Nothing here is recomputed from the image
            </span>
          </div>

          <ul className="space-y-1.5">
            {open.signals.map((s, i) => (
              <li
                key={`${s.id}-${i}`}
                className="grid grid-cols-[2rem_1fr_5rem_2fr] items-baseline gap-3 rounded-[var(--radius-sm)] border border-iris/20 bg-bloom/30 px-4 py-3 hover:bg-bloom/60 transition-colors"
              >
                <span className={cn("flex h-5 w-5 items-center justify-center rounded", TRUST_STYLE[s.trust_class].badge)}>
                  <TrustMark trust={s.trust_class} size={11} />
                </span>
                <span className="data text-label text-iris-ink font-mono">{s.id}</span>
                <span
                  className={cn(
                    "inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium",
                    s.verdict === "fail"
                      ? "bg-red-100 text-red-700"
                      : s.verdict === "inconclusive"
                        ? "bg-amber-100 text-amber-700"
                        : s.verdict === "not_applicable"
                          ? "bg-slate-100 text-slate-500"
                          : "bg-emerald-100 text-emerald-700",
                  )}
                >
                  {s.verdict}
                </span>
                <span className="text-iris-ink text-label">{s.evidence}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <p className="mt-10 text-label text-iris-ink">
        {mode === "live" ? (
          <>
            {events?.length ?? 0} of <span className="font-semibold">{total}</span> recorded
            screenings, from{" "}
            <code className="rounded bg-bloom px-1.5 py-0.5 font-mono text-[12px]">GET /events</code>. Re-scoring
            calls <code className="rounded bg-bloom px-1.5 py-0.5 font-mono text-[12px]">POST /rescore</code>, the
            same endpoint the operating point screen uses.
          </>
        ) : (
          <>
            Reading {Object.keys(FIXTURES).length} rehearsed cases from local
            fixtures. Against a live backend this list comes from{" "}
            <code className="rounded bg-bloom px-1.5 py-0.5 font-mono text-[12px]">GET /events</code> and re-scoring
            from <code className="rounded bg-bloom px-1.5 py-0.5 font-mono text-[12px]">POST /rescore</code>.
          </>
        )}
      </p>
    </div>
  );
}
