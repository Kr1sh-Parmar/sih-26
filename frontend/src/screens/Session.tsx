/**
 * The session view — cross-document trust propagation.
 *
 * This is the headline claim (context/DEMO.md Scene 3). Four of six Indian
 * identity documents carry no cryptographic integrity today. When one document
 * in a session *is* signed, its payload becomes ground truth for the others
 * presented alongside it.
 *
 * The claim has three parts, and the screen has to show all three:
 *   the signature verifies  ->  so this date is proven  ->  and that document
 *   contradicts it.
 *
 * The middle arrow is the part a table would lose, so the propagation is drawn
 * as edges between the two documents rather than listed as rows.
 */
import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "motion/react";
import { useSession, type PropagationEdge } from "../store/session";
import { fixture } from "../transport/mockSocket";
import { fetchSession } from "../transport/socket";
import { useMode } from "../transport/mode";
import { docLabel } from "../domain/docType";
import { TRUST_STYLE } from "../domain/trustClass";
import { ModeBadge } from "../components/ModeBadge";
import { TrustMark } from "../components/marks/TrustMark";
import { DisclosureNotice } from "../components/DisclosureNotice";
import { cn } from "../lib/utils";

const FIELD_LABEL: Record<string, string> = {
  name: "Name",
  dob: "Date of birth",
  father_name: "Father's name",
  address: "Address",
};

function DocumentCard({
  label,
  docType,
  signed,
  band,
  active,
}: {
  label: string;
  docType: string;
  signed: boolean;
  band: string | null;
  active: boolean;
}) {
  const bandInk =
    band === "RED" ? "text-detain" : band === "AMBER" ? "text-secondary-ink" : "text-clear";
  const bandWord = band === "RED" ? "DETAIN" : band === "AMBER" ? "SECONDARY" : "CLEAR";

  return (
    <div
      className={cn(
        "border p-5 transition-colors",
        active ? "border-intaglio bg-bloom/60" : "border-iris bg-paper",
      )}
    >
      <div className="flex items-baseline gap-3">
        <span className={signed ? "text-intaglio" : "text-iris-ink"}>
          <TrustMark trust={signed ? "cryptographic" : "unverified"} size={18} />
        </span>
        <span className="text-[length:var(--text-evidence)] font-medium">{label}</span>
        <span className="ml-auto text-label text-iris-ink">{docType}</span>
      </div>

      <p className="mt-3 text-label text-iris-ink">
        {signed
          ? "Carries a signature that verifies. Its payload is ground truth for this session."
          : "No signature payload. Nothing on this card proves itself."}
      </p>

      {band && (
        <p className={cn("mt-4 text-[length:var(--text-screen)] font-bold", bandInk)}>
          {bandWord}
        </p>
      )}
    </div>
  );
}

function Edge({ edge, index }: { edge: PropagationEdge; index: number }) {
  const reduce = useReducedMotion();
  const setActiveField = useSession((s) => s.setActiveField);
  const activeField = useSession((s) => s.activeField);
  const active = activeField === edge.field;

  return (
    <motion.li
      initial={reduce ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, delay: index * 0.1 }}
      onMouseEnter={() => setActiveField(edge.field)}
      onMouseLeave={() => setActiveField(null)}
      className={cn(
        "grid grid-cols-[1fr_auto_1fr] items-center gap-4 border-t py-5",
        edge.agrees ? "border-iris" : "border-detain",
        active && "bg-bloom/50",
      )}
    >
      <div className="text-right">
        <p className="text-label text-iris-ink">{FIELD_LABEL[edge.field] ?? edge.field}</p>
        <p className="data mt-1 text-[length:var(--text-evidence)]">
          {edge.fromValue ?? <span className="text-iris-ink">no longer held</span>}
        </p>
        <p className="text-label text-iris-ink">signed payload</p>
      </div>

      {/* the "so" — the part a table would lose */}
      <div className="flex w-40 flex-col items-center">
        <svg viewBox="0 0 160 24" className="w-full" aria-hidden>
          <line
            x1="4"
            y1="12"
            x2="140"
            y2="12"
            stroke={edge.agrees ? "var(--color-iris)" : "var(--color-detain)"}
            strokeWidth="2"
            strokeDasharray={edge.agrees ? undefined : "7 5"}
          />
          <path
            d="M140 6 L154 12 L140 18 Z"
            fill={edge.agrees ? "var(--color-iris)" : "var(--color-detain)"}
          />
        </svg>
        <span
          className={cn(
            "mt-1 text-label",
            edge.agrees ? "text-iris-ink" : "text-detain font-medium",
          )}
        >
          {edge.agrees ? "confirms" : "contradicts"}
        </span>
        {/* Certainty is never implied by colour alone. */}
        <span
          className="mt-1 inline-flex items-center gap-1 text-label text-iris-ink"
          title={TRUST_STYLE[edge.trustClass].gloss}
        >
          <TrustMark trust={edge.trustClass} size={11} />
          {TRUST_STYLE[edge.trustClass].label}
        </span>
      </div>

      <div>
        <p className="text-label text-iris-ink">{FIELD_LABEL[edge.field] ?? edge.field}</p>
        <p
          className={cn(
            "data mt-1 text-[length:var(--text-evidence)]",
            !edge.agrees && "text-detain font-medium",
          )}
        >
          {edge.toValue ?? <span className="text-iris-ink">no longer held</span>}
        </p>
        <p className="text-label text-iris-ink">printed on the card</p>
      </div>

      {edge.evidence && (
        <p className="col-span-3 mt-2 text-label text-iris-ink">{edge.evidence}</p>
      )}
    </motion.li>
  );
}

export function Session() {
  const { sessionId, documents, edges, activeField, start, add, setEdges } =
    useSession();
  const mode = useMode();

  /** Live: whatever this session has actually screened.
   *
   *  Empty is the normal state — a session holds documents only once the
   *  counter has screened two, and that is a fact about the shift, not an
   *  error. The rehearsed pair below fills in only when there is no service. */
  useEffect(() => {
    if (mode !== "live") return;
    let alive = true;
    fetchSession(sessionId)
      .then((view) => {
        if (!alive || view.documents.length === 0) return;
        start(view.session_id);
        for (const d of view.documents) {
          add({
            id: d.id,
            docType: d.doc_type,
            label: docLabel(d.doc_type),
            signed: d.signed,
            band: d.band,
            fixture: "green",
          });
        }
        setEdges(
          view.edges.map((e) => ({
            field: e.field,
            from: e.from,
            to: e.to,
            fromValue: e.from_value,
            toValue: e.to_value,
            agrees: e.agrees,
            trustClass: e.trust_class,
            evidence: e.evidence,
          })),
        );
      })
      .catch(() => null);
    return () => {
      alive = false;
    };
  }, [mode, sessionId, start, add, setEdges]);

  /** Seed the rehearsed Scene 3 pair when there is no backend, so the view is
   *  demonstrable before the capture flow has been driven twice. */
  useEffect(() => {
    if (mode !== "fixtures" || documents.length > 0) return;
    const doc = fixture("crossdoc");
    const meta = doc.meta as unknown as {
      session_documents: { doc_type: string; signed: boolean; label: string; band: string }[];
      propagation: {
        field: string; from: string; to: string; agrees: boolean;
        from_value: string; to_value: string;
      }[];
    };
    start();
    for (const d of meta.session_documents) {
      add({
        id: d.doc_type,
        docType: d.doc_type,
        label: d.label,
        signed: d.signed,
        band: d.band as "GREEN" | "AMBER" | "RED",
        fixture: d.signed ? "green" : "crossdoc",
      });
    }
    setEdges(
      meta.propagation.map((p) => ({
        field: p.field,
        from: p.from,
        to: p.to,
        fromValue: p.from_value,
        toValue: p.to_value,
        agrees: p.agrees,
        // The propagated finding is cryptographic because one side of the
        // comparison is a verified signature - not because a model was sure.
        trustClass: "cryptographic" as const,
        evidence: "",
      })),
    );
  }, [mode, documents.length, start, add, setEdges]);

  const anchor = documents.find((d) => d.signed);
  const disputed = edges.filter((e) => !e.agrees);
  // Shown only when a signature actually verified, never as furniture (D1).
  // The string is the reference issuer's own, identical to the one the profile
  // carries and the one the screening stream sends on `verdict.disclosure`;
  // this view has no verdict event to read it from, so it takes the same text
  // from the fixture rather than making a request for a constant.
  const disclosure = anchor ? fixture("crossdoc").verdict.disclosure : null;

  return (
    <div className="mx-auto w-full max-w-5xl px-8 py-8">
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <h1 className="text-[length:var(--text-screen)] font-semibold">
          Documents presented together
        </h1>
        <ModeBadge mode={mode} />
      </div>
      <p className="mt-1 text-iris-ink">
        Session <span className="data">{sessionId}</span>
      </p>

      {mode === "live" && documents.length === 0 && (
        <p className="mt-8 text-iris-ink">
          Nothing has been presented in this session yet. Trust propagation
          needs a second document to check against the first.
        </p>
      )}

      <div className="mt-8 grid gap-6 md:grid-cols-2">
        {documents.map((d) => (
          <DocumentCard
            key={d.id}
            label={d.label}
            docType={d.docType}
            signed={d.signed}
            band={d.band}
            active={activeField !== null}
          />
        ))}
      </div>

      {anchor && (
        <p className="mt-10 max-w-[42rem] text-[length:var(--text-evidence)] leading-relaxed">
          The {anchor.label} signature verifies against a key in the trust
          anchor store. Everything inside that signed payload is therefore
          proven, and it can be used to check the documents presented with it.
        </p>
      )}

      {documents.length > 1 && edges.length === 0 && (
        <p className="mt-6 border-l-2 border-secondary-ink bg-guilloche/25 px-4 py-3">
          Nothing was propagated between these documents. A signed payload can
          only be checked against a field that was actually read off the other
          card, and none were — so the comparison is an open question, not a
          clean result. The unsigned document's own evidence list says which
          fields could not be read.
        </p>
      )}

      <ol className="mt-6">
        {edges.map((e, i) => (
          <Edge key={e.field} edge={e} index={i} />
        ))}
      </ol>

      {disputed.length > 0 && (
        <div className="mt-8 border-t-2 border-detain pt-5">
          <p className="text-[length:var(--text-evidence)] font-semibold">
            {disputed.length === 1
              ? `${FIELD_LABEL[disputed[0].field] ?? disputed[0].field} is contradicted by a signed document.`
              : `${disputed.length} fields are contradicted by a signed document.`}
          </p>
          <p className="mt-2 max-w-[42rem] text-iris-ink">
            This is a cryptographic finding, not an inference. No model produced
            it and no threshold was crossed — two values that must be the same
            are different, and one of them is signed.
          </p>
          <Link
            to="/screening"
            className="mt-5 inline-block bg-intaglio px-5 py-2.5 text-paper hover:bg-intaglio/90"
          >
            Open the disputed document
          </Link>
        </div>
      )}

      <DisclosureNotice text={disclosure} />
    </div>
  );
}
