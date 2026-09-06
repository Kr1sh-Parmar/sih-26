/**
 * Extracted fields.
 *
 * `source` matters as much as `value`: a field read by the VLM fallback has no
 * checksum behind it and is `unverified`, which must not look the same as a
 * field lifted from a verified MRZ. That is the whole trust-class idea applied
 * one row at a time.
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

/** Where a value came from decides how much it can be trusted. */
const SOURCE_TRUST = {
  qr: "cryptographic",
  mrz: "arithmetic",
  ocr: "probabilistic",
  vlm: "unverified",
} as const;

const SOURCE_LABEL = {
  qr: "signed QR payload",
  mrz: "machine-readable zone",
  ocr: "printed text",
  vlm: "fallback reader, no checksum",
} as const;

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
      <h2 className="text-[length:var(--text-evidence)]">Extracted fields</h2>
      <div className="mt-1 border-t border-intaglio" />

      <table className="w-full">
        <tbody>
          {fields.map((f) => {
            const anchor = `field:${f.name}`;
            const active = activeAnchor === anchor;
            const trust = SOURCE_TRUST[f.source];
            return (
              <tr
                key={f.name}
                className={cn(
                  "border-b border-iris/50 align-baseline",
                  active && "bg-bloom/70",
                )}
                onMouseEnter={() => setActiveAnchor(anchor)}
                onMouseLeave={() => setActiveAnchor(null)}
              >
                <td className="w-36 py-2 pr-4 text-label text-iris-ink">
                  {LABEL[f.name] ?? f.name}
                </td>
                <td
                  className={cn(
                    "py-2 pr-4 data whitespace-nowrap",
                    f.state === "fail" && "text-detain font-medium",
                    f.state === "inconclusive" && "text-iris-ink",
                  )}
                >
                  {f.value}
                </td>
                <td className="py-2 text-label text-iris-ink whitespace-nowrap">
                  <span className="inline-flex items-center gap-2">
                    <TrustMark trust={trust} size={13} />
                    {SOURCE_LABEL[f.source]}
                  </span>
                </td>
                <td className="w-16 py-2 text-right text-label text-iris-ink data">
                  {f.source === "ocr" || f.source === "vlm"
                    ? f.confidence.toFixed(2)
                    : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
