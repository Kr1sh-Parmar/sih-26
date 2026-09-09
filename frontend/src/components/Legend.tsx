/**
 * The trust-class legend, always on screen.
 */
import type { TrustClass } from "../contracts";
import { TRUST_STYLE } from "../domain/trustClass";
import { TrustMark } from "./marks/TrustMark";

const ORDER: TrustClass[] = ["cryptographic", "arithmetic", "probabilistic", "unverified"];

const BADGE_STYLE: Record<TrustClass, string> = {
  cryptographic: "bg-blue-50 text-blue-700 border border-blue-200",
  arithmetic: "bg-slate-100 text-slate-600 border border-slate-200",
  probabilistic: "bg-violet-50 text-violet-600 border border-violet-200",
  unverified: "bg-orange-50 text-orange-600 border border-orange-200",
};

export function Legend() {
  return (
    <footer className="border-t border-iris/50 bg-white/80 backdrop-blur-sm px-6 py-3">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2">
        <span className="text-label font-semibold text-iris-ink mr-2">Trust levels:</span>
        {ORDER.map((t) => (
          <span key={t} className="inline-flex items-center gap-2 text-label">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 font-medium text-[11px] ${BADGE_STYLE[t]}`}>
              <TrustMark trust={t} size={12} />
              {TRUST_STYLE[t].label}
            </span>
            <span className="hidden lg:inline text-iris-ink">{TRUST_STYLE[t].gloss}</span>
          </span>
        ))}
      </div>
    </footer>
  );
}
