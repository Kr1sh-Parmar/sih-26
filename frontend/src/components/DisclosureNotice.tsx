/**
 * The reference-issuer disclosure.
 *
 * context/DEMO.md Scene 3: "the console must render the `disclosure` string.
 * Do not let a reference verification look like a government one."
 *
 * So this deliberately does NOT use the cryptographic rosette or the intaglio
 * ink of a real trust anchor. It sits on the lilac wash with a dashed edge —
 * the same visual language the ontology uses for `unverified` — because that
 * is the honest reading: the signature is real, the authority behind it is
 * ours.
 */
import { OpenCircle } from "./marks/TrustMark";

export function DisclosureNotice({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <aside className="mt-6 rounded-[var(--radius-md)] border border-dashed border-iris bg-bloom/60 p-4">
      <div className="flex gap-3">
        <span className="mt-0.5 shrink-0 text-iris-ink">
          <OpenCircle />
        </span>
        <p className="text-iris-ink">{text}</p>
      </div>
    </aside>
  );
}
