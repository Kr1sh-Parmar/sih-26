/**
 * The four trust-class marks, drawn inline. No icon package: these do not
 * exist in one, and a package would be a build-time network dependency and a
 * bundle cost for four glyphs.
 *
 * Each is drawn on a 16x16 box, optically centred on the cap height of the
 * evidence line beside it.
 */
import type { TrustClass } from "../../contracts";

export interface MarkProps {
  size?: number;
  className?: string;
}

/** Engraved. A guilloche rosette — the thing a forger cannot reproduce. */
export function Rosette({ size = 16, className }: MarkProps) {
  const petals = Array.from({ length: 6 }, (_, i) => (i * 360) / 6);
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none">
      {petals.map((deg) => (
        <ellipse key={deg} cx="8" cy="8" rx="2.6" ry="6.6"
                 transform={`rotate(${deg} 8 8)`}
                 stroke="currentColor" strokeWidth="1" />
      ))}
      <circle cx="8" cy="8" r="2.1" fill="currentColor" />
    </svg>
  );
}

/** Mechanical. A plate-registration cross — exact, or the print is wrong. */
export function RegisterCross({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <path d="M8 0.8 V6.2 M8 9.8 V15.2 M0.8 8 H6.2 M9.8 8 H15.2"
            strokeWidth="1.3" />
      <circle cx="8" cy="8" r="4.2" strokeWidth="1" />
      <circle cx="8" cy="8" r="0.9" fill="currentColor" stroke="none" />
    </svg>
  );
}

/** Screened. A halftone cluster — an approximation of a continuous tone. */
export function Halftone({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="currentColor">
      <circle cx="4" cy="4.5" r="2.5" />
      <circle cx="11.2" cy="5.6" r="1.7" />
      <circle cx="5.4" cy="11.4" r="1.7" />
      <circle cx="11.6" cy="11.8" r="1" />
    </svg>
  );
}

/** Blank. Nothing was checked — which is not the same as nothing was wrong. */
export function OpenCircle({ size = 16, className }: MarkProps) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} className={className}
         aria-hidden="true" fill="none" stroke="currentColor">
      <circle cx="8" cy="8" r="5.6" strokeWidth="1" strokeDasharray="2 2" />
    </svg>
  );
}

const MARKS = {
  cryptographic: Rosette,
  arithmetic: RegisterCross,
  probabilistic: Halftone,
  unverified: OpenCircle,
} as const;

export function TrustMark({
  trust,
  size = 16,
  className,
}: { trust: TrustClass } & MarkProps) {
  const Mark = MARKS[trust];
  return <Mark size={size} className={className} />;
}
