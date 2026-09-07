/**
 * The audit trail, and re-scoring.
 *
 * "Decisions get challenged months later" (context/CONTEXT.md §3). So the full
 * signal list is stored as JSONB, not just the cards — cards are a view. When a
 * weight changes, a historical event can be re-scored from what was recorded
 * without re-running a single model, which is the only way two verdicts months
 * apart stay comparable.
 *
 * The re-score is a server call. This screen used to reimplement the scorer in
 * TypeScript, labelled honestly as a demonstration, and that was the right
 * placeholder while `POST /rescore` did not exist. It exists now, so the local
 * copy is gone: two implementations of a verdict drift, and the one in the
 * browser would end up disagreeing with the audit log it is meant to explain.
 *
 * Never shows a raw identity number. Salted hash plus last four digits, per
 * CLAUDE.md hard rule #5 — and the API does not return one either, because the
 * database does not store one.
 */
import { useEffect, useMemo, useState } from "react";
import type { Band } from "../contracts";
import {
  fetchEvents,
  rescoreEvent,
  type AuditEvent,
  type RescoreResult,
} from "../transport/socket";
import { fixture, FIXTURES, type FixtureName } from "../transport/mockSocket";
import { useMode } from "../transport/mode";
import { useSettings } from "../store/settings";
import { ModeBadge } from "../components/ModeBadge";
import { TrustMark } from "../components/marks/TrustMark";
import { docLabel } from "../domain/docType";
import { cn } from "../lib/utils";

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

/**
 * Rehearsed events, for when there is no backend.
 *
 * Shaped exactly like `GET /events` so the table has one code path. These
 * carry no re-score: without the server there is no scorer, and inventing one
 * here is the thing this screen just stopped doing.
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
    : at.toLocaleTimeString("en-IN", {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
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
  // per event, which is honest rather than clever: the server is the only
  // thing allowed to produce a verdict.
  // ponytail: N requests for N rows against a localhost process. Batch them
  // into one POST if this ever pages past a few dozen events.
  useEffect(() => {
    if (mode !== "live" || !events?.length) return;
    let alive = true;
    const bands = {
      green_below: amberAt,
      amber_below: redAt,
      coverage_floor: coverageFloor,
    };
    Promise.all(
      events.map((e) =>
        rescoreEvent(e.id, bands).catch(() => null),
      ),
    ).then((results) => {
      if (!alive) return;
      const next: Record<string, RescoreResult> = {};
      for (const r of results) if (r) next[r.event_id] = r;
      setRescored(next);
    });
    return () => {
      alive = false;
    };
  }, [mode, events, amberAt, redAt, coverageFloor]);

  const open = events?.find((e) => e.id === openId) ?? null;
  const changed = Object.values(rescored).filter((r) => r.changed);

  return (
    <div className="mx-auto w-full max-w-6xl px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-[length:var(--text-screen)] font-semibold">Audit trail</h1>
        <ModeBadge mode={mode} />
      </div>
      <p className="mt-1 max-w-[44rem] text-iris-ink">
        Every screening keeps its complete signal list, not just the cards it
        produced. Change a band on the operating point screen and every event
        here re-scores from what was recorded — no model runs again.
      </p>

      {problem && (
        <p className="mt-6 border-l-2 border-detain bg-detain/10 px-4 py-3">
          {problem}
        </p>
      )}

      {mode === "fixtures" && (
        <p className="mt-6 border-l-2 border-secondary-ink bg-guilloche/25 px-4 py-3">
          These are rehearsed cases read from local fixtures. Re-scoring needs
          the screening service, because the verdict is only ever produced
          server-side — there is no second scorer in this console.
        </p>
      )}

      {changed.length > 0 && (
        <p className="mt-6 border-l-2 border-guilloche bg-guilloche/25 px-4 py-3">
          The current bands would change{" "}
          <span className="data">{changed.length}</span> of these{" "}
          <span className="data">{events?.length ?? 0}</span> verdicts.
        </p>
      )}

      {events === null ? (
        <p className="mt-8 text-iris-ink">Reading the audit trail…</p>
      ) : events.length === 0 ? (
        <p className="mt-8 text-iris-ink">
          Nothing has been screened on this workstation yet.
        </p>
      ) : (
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
              const re = rescored[e.id];
              return (
                <tr
                  key={e.id}
                  className={cn(
                    "border-b border-iris/50",
                    openId === e.id && "bg-bloom/60",
                  )}
                >
                  <td className="py-3 data">{clockOf(e.created_at)}</td>
                  <td className="py-3">{docLabel(e.doc_type)}</td>
                  <td className="py-3 data text-iris-ink">
                    ••••{e.id_number_last4 ?? "————"}
                    {e.id_number_hash && (
                      <span className="ml-2 text-label">
                        sha256:{e.id_number_hash.slice(0, 8)}
                      </span>
                    )}
                  </td>
                  <td className={cn("py-3 font-medium", BAND_INK[e.band])}>
                    {BAND_WORD[e.band]}
                  </td>
                  <td className="py-3">
                    {re ? (
                      <>
                        <span className={cn("font-medium", BAND_INK[re.rescored.band])}>
                          {BAND_WORD[re.rescored.band]}
                        </span>
                        {re.changed && (
                          <span className="ml-2 text-label text-iris-ink">changed</span>
                        )}
                        {re.rescored.reason && (
                          <span className="ml-2 text-label text-iris-ink">
                            {re.rescored.reason}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-label text-iris-ink">
                        {mode === "live" ? "re-scoring…" : "needs the service"}
                      </span>
                    )}
                  </td>
                  <td className="py-3 data text-iris-ink">{e.officer_id ?? "—"}</td>
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
      )}

      {open && (
        <section className="mt-10 border-t-2 border-intaglio pt-6">
          <h2 className="text-[length:var(--text-evidence)]">
            Stored signals — {docLabel(open.doc_type)}, {clockOf(open.created_at)}
          </h2>
          <p className="mt-1 text-label text-iris-ink">
            {open.signals.length} signals. This is the record a re-score reads;
            nothing here is recomputed from the image.
          </p>

          <ul className="mt-5">
            {open.signals.map((s, i) => (
              <li
                key={`${s.id}-${i}`}
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
        {mode === "live" ? (
          <>
            {events?.length ?? 0} of <span className="data">{total}</span> recorded
            screenings, from <span className="data">GET /events</span>. Re-scoring
            calls <span className="data">POST /rescore</span>, the same endpoint the
            operating point screen uses.
          </>
        ) : (
          <>
            Reading {Object.keys(FIXTURES).length} rehearsed cases from local
            fixtures. Against a live backend this list comes from{" "}
            <span className="data">GET /events</span> and re-scoring from{" "}
            <span className="data">POST /rescore</span>.
          </>
        )}
      </p>
    </div>
  );
}
