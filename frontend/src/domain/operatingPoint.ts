/**
 * The face-verification trade-off curve.
 *
 * FAR and FRR are both derived from the same two score distributions, so they
 * move against each other as the threshold slides. That opposition is the
 * whole point of the screen: there is no threshold that is simply "accurate",
 * only one that trades an impostor admitted against a genuine traveller
 * stopped, and the checkpoint commander makes that trade — not us.
 *
 * The distributions here stand in for the doc-vs-live calibration set
 * (>=500 pairs from >=30 people, context/MODULES.md). Replace MU/SIGMA with
 * the measured values once that capture session has happened; nothing else on
 * this screen changes.
 */

/** Doc-vs-live genuine pairs. Wide, because a passport photo is printed,
 *  halftone-screened and up to ten years old. */
export const GENUINE = { mu: 0.58, sigma: 0.125 };
/** Impostor pairs. */
export const IMPOSTOR = { mu: 0.05, sigma: 0.09 };

/** Abramowitz & Stegun 7.1.26 — plenty for drawing a curve. */
function erf(x: number): number {
  const s = Math.sign(x);
  const a = Math.abs(x);
  const t = 1 / (1 + 0.3275911 * a);
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t +
      0.254829592) *
      t *
      Math.exp(-a * a);
  return s * y;
}

const cdf = (x: number, mu: number, sigma: number) =>
  0.5 * (1 + erf((x - mu) / (sigma * Math.SQRT2)));

/** Share of genuine travellers wrongly stopped at this threshold. */
export const frr = (t: number) => cdf(t, GENUINE.mu, GENUINE.sigma);

/** Share of impostors wrongly admitted at this threshold. */
export const far = (t: number) => 1 - cdf(t, IMPOSTOR.mu, IMPOSTOR.sigma);

export interface CurvePoint {
  t: number;
  far: number;
  frr: number;
}

export function curve(lo = 0, hi = 0.9, steps = 180): CurvePoint[] {
  return Array.from({ length: steps + 1 }, (_, i) => {
    const t = lo + ((hi - lo) * i) / steps;
    return { t, far: far(t), frr: frr(t) };
  });
}

/** Where the two rates cross. Not a recommendation — just a landmark. */
export function equalErrorRate(): { t: number; rate: number } {
  let lo = 0;
  let hi = 0.9;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (far(mid) > frr(mid)) lo = mid;
    else hi = mid;
  }
  const t = (lo + hi) / 2;
  return { t, rate: (far(t) + frr(t)) / 2 };
}

/** The number that actually matters to a checkpoint commander. */
export function dailyConsequence(threshold: number, volume: number) {
  return {
    stopped: Math.round(frr(threshold) * volume),
    admitted: Math.round(far(threshold) * volume),
  };
}
