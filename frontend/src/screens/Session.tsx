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
        "rounded-[var(--radius-lg)] border p-6 transition-all",
        active ? "border-guilloche/40 bg-guilloche/5" : "border-iris/40 bg-bloom/40",
      )}
      style={{ boxShadow: "var(--shadow-sm)" }}
    >
      <div className="flex items-baseline gap-3">
        <span className={signed ? "text-intaglio" : "text-iris-ink"}>
          <TrustMark trust={signed ? "cryptographic" : "unverified"} size={18} />
        </span>
        <span className="text-[length:var(--text-evidence)] font-semibold">{label}</span>
        <span className="ml-auto rounded-full bg-bloom px-3 py-0.5 text-label text-iris-ink">{docType}</span>
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
        "grid grid-cols-[1fr_auto_1fr] items-center gap-4 rounded-[var(--radius-md)] border-t py-5 px-3 -mx-3 transition-colors",
        edge.agrees ? "border-iris/40" : "border-detain/30",
        active && "bg-guilloche/5",
      )}
    >
      <div className="text-right">
        <p className="text-label text-iris-ink">{FIELD_LABEL[edge.field] ?? edge.field}</p>
        <p className="data mt-1 text-[length:var(--text-evidence)]">{edge.fromValue}</p>
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
      </div>

      <div>
        <p className="text-label text-iris-ink">{FIELD_LABEL[edge.field] ?? edge.field}</p>
        <p
          className={cn(
            "data mt-1 text-[length:var(--text-evidence)]",
            !edge.agrees && "text-detain font-medium",
          )}
        >
          {edge.toValue}
        </p>
        <p className="text-label text-iris-ink">printed on the card</p>
      </div>
    </motion.li>
  );
}

export function Session() {
  const { sessionId, documents, edges, activeField, start, add, setEdges } =
    useSession();

  /** Seed the rehearsed Scene 3 pair when the session is empty, so the view is
   *  demonstrable before the capture flow has been driven twice. */
  useEffect(() => {
    if (documents.length > 0) return;
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
      })),
    );
  }, [documents.length, start, add, setEdges]);

  const anchor = documents.find((d) => d.signed);
  const disputed = edges.filter((e) => !e.agrees);
  const disclosure = fixture("crossdoc").verdict.disclosure;

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-8">
      <h1 className="text-[length:var(--text-screen)] font-semibold tracking-[-0.02em]">
        Documents presented together
      </h1>
      <p className="mt-1 text-iris-ink">
        Session <span className="data">{sessionId}</span>
      </p>

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
        <p className="mt-10 max-w-[42rem] text-[length:var(--text-evidence)] leading-relaxed text-iris-ink">
          The {anchor.label} signature verifies against a key in the trust
          anchor store. Everything inside that signed payload is therefore
          proven, and it can be used to check the documents presented with it.
        </p>
      )}

      <ol className="mt-6">
        {edges.map((e, i) => (
          <Edge key={e.field} edge={e} index={i} />
        ))}
      </ol>

      {disputed.length > 0 && (
        <div className="mt-8 rounded-[var(--radius-lg)] border border-detain/30 bg-detain/5 p-6">
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
            className="mt-5 inline-block rounded-[var(--radius-md)] bg-intaglio px-5 py-2.5 font-medium text-white hover:bg-intaglio/90 transition-colors"
          >
            Open the disputed document
          </Link>
        </div>
      )}

      <DisclosureNotice text={disclosure} />
    </div>
  );
}
