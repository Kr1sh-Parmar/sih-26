/**
 * Face match presentation.
 *
 * Never `((cos + 1) / 2) * 100`. That maps a stranger to 50, which is
 * misleading in the direction that admits fraudsters (CLAUDE.md, and
 * context/MODULES.md pitfalls). There is no function in this file that
 * returns a 0-100 figure.
 *
 * What the officer gets instead: the band, the raw cosine, and the signed
 * margin from the operating threshold — which is the number that actually
 * says how close the call was.
 */

export type FaceBand = "no_match" | "review" | "match" | "no_face";

export interface FaceReading {
  band: FaceBand;
  /** Signed distance from the threshold. Positive means above it. */
  margin: number | null;
  cosine: number | null;
  threshold: number;
}

/** Width of the review band on either side of the threshold. Operator-tunable
 *  via config/thresholds.yaml; this is the default. */
export const REVIEW_HALF_WIDTH = 0.06;

export function faceMargin(
  cosine: number | null | undefined,
  threshold: number,
  reviewHalfWidth = REVIEW_HALF_WIDTH,
): FaceReading {
  if (cosine === null || cosine === undefined || Number.isNaN(cosine)) {
    return { band: "no_face", margin: null, cosine: null, threshold };
  }
  const margin = cosine - threshold;
  const band: FaceBand =
    margin > reviewHalfWidth
      ? "match"
      : margin < -reviewHalfWidth
        ? "no_match"
        : "review";
  return { band, margin, cosine, threshold };
}

export const FACE_BAND_LABEL: Record<FaceBand, string> = {
  match: "Match",
  review: "Review",
  no_match: "No match",
  no_face: "No face found",
};

/** Where to put the marker on a gauge running from `lo` to `hi` cosine. */
export function gaugePosition(cosine: number, lo = -0.1, hi = 0.9): number {
  return Math.min(1, Math.max(0, (cosine - lo) / (hi - lo)));
}
