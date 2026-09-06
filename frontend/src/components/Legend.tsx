/**
 * The trust-class legend, always on screen.
 *
 * context/MODULES.md: "Do not hide the trust class. Flattening a signature
 * check and a texture heuristic into one number is exactly what this system
 * exists to avoid." An officer learns four marks once; the legend is what
 * makes the first sighting work.
 */
import type { TrustClass } from "../contracts";
import { TRUST_STYLE } from "../domain/trustClass";
import { TrustMark } from "./marks/TrustMark";

const ORDER: TrustClass[] = [
  "cryptographic",
  "arithmetic",
  "probabilistic",
  "unverified",
];

export function Legend() {
  return (
    <footer className="border-t border-iris bg-paper px-8 py-3">
      <ul className="flex flex-wrap items-center gap-x-8 gap-y-2">
        {ORDER.map((t) => (
          <li key={t} className="inline-flex items-center gap-2 text-label">
            <span className={t === "cryptographic" ? "text-intaglio" : "text-iris-ink"}>
              <TrustMark trust={t} size={14} />
            </span>
            <span className="text-intaglio">{TRUST_STYLE[t].label}</span>
            <span className="text-iris-ink">{TRUST_STYLE[t].gloss}</span>
          </li>
        ))}
      </ul>
    </footer>
  );
}
