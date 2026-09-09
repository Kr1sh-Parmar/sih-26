/**
 * Extracted fields.
 */
import type { Region } from "../contracts";
import { useScreening } from "../store/screening";
import { TrustMark } from "./marks/TrustMark";
import { cn } from "../lib/utils";

export interface FieldRow {
  name: string;
  value: string;
  source: "ocr" | "mrz" | "qr" | "vlm";
  confidence: number;
  state: "pass" | "fail" | "inconclusive";
  region: Region | null;
}

const SOURCE_TRUST = {
  qr: "cryptographic",
  mrz: "arithmetic",
  ocr: "probabilistic",
  vlm: "unverified",
} as const;

const SOURCE_LABEL = {
  qr: "signed QR",
  mrz: "MRZ",
  ocr: "printed text",
  vlm: "fallback reader",
} as const;

const SOURCE_BADGE: Record<string, string> = {
  qr: "bg-blue-50 text-blue-700 border border-blue-200",
  mrz: "bg-slate-100 text-slate-600 border border-slate-200",
  ocr: "bg-violet-50 text-violet-600 border border-violet-200",
  vlm: "bg-orange-50 text-orange-600 border border-orange-200",
};

const STATE_STYLE = {
  pass: "",
  fail: "text-red-600 font-semibold",
  inconclusive: "text-iris-ink",
};

const LABEL: Record<string, string> = {
  name: "Name",
  father_name: "Father's name",
  dob: "Date of birth",
  id_number: "Number",
  nationality: "Nationality",
  expiry_date: "Expires",
  issue_date: "Issued",
  gender: "Sex",
  address: "Address",
};

export function FieldTable({ fields }: { fields: FieldRow[] }) {
  const activeAnchor = useScreening((s) => s.activeAnchor);
  const setActiveAnchor = useScreening((s) => s.setActiveAnchor);

  if (fields.length === 0) return null;

  return (
    <section className="mt-8">
      <h2 className="text-[length:var(--text-evidence)] font-semibold">Extracted fields</h2>
      <div className="mt-2 h-px bg-iris/40" />

      <div className="mt-3 overflow-hidden rounded-[var(--radius-md)] border border-iris/40 bg-white" style={{ boxShadow: "var(--shadow-sm)" }}>
        <table className="w-full">
          <thead>
            <tr className="border-b border-iris/30 bg-bloom/60">
              <th className="py-2.5 pl-4 text-left text-label font-semibold text-iris-ink">Field</th>
              <th className="py-2.5 text-left text-label font-semibold text-iris-ink">Value</th>
              <th className="py-2.5 pr-4 text-left text-label font-semibold text-iris-ink">Source</th>
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => {
              const anchor = `field:${f.name}`;
              const active = activeAnchor === anchor;
              const trust = SOURCE_TRUST[f.source];
              return (
                <tr
                  key={f.name}
                  className={cn(
                    "border-t border-iris/20 transition-colors cursor-pointer",
                    active ? "bg-guilloche/5" : "hover:bg-bloom/50",
                    f.state === "fail" && "bg-red-50/60 hover:bg-red-50",
                  )}
                  onMouseEnter={() => setActiveAnchor(anchor)}
                  onMouseLeave={() => setActiveAnchor(null)}
                >
                  <td className="py-3 pl-4 text-label text-iris-ink whitespace-nowrap font-medium">
                    {LABEL[f.name] ?? f.name}
                  </td>
                  <td className={cn("py-3 pr-4 data whitespace-nowrap text-[15px]", STATE_STYLE[f.state])}>
                    {f.state === "fail" && (
                      <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-red-500" />
                    )}
                    {f.value}
                  </td>
                  <td className="py-3 pr-4">
                    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-medium", SOURCE_BADGE[f.source])}>
                      <TrustMark trust={trust} size={11} />
                      {SOURCE_LABEL[f.source]}
                      {(f.source === "ocr" || f.source === "vlm") && (
                        <span className="opacity-60">{f.confidence.toFixed(2)}</span>
                      )}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
