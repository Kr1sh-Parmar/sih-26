/**
 * Pre-submit capture quality.
 *
 * The same gates the backend runs (`extraction.quality.*`), computed in the
 * browser on the captured frame so the officer is told to re-capture *before*
 * the traveller has walked away. An AMBER "re-capture required" at the counter
 * costs a minute; the same verdict after the passenger has moved on costs a
 * lot more.
 *
 * Thresholds differ by source on purpose: a printed photograph is naturally
 * softer than a camera capture, so a document scan is judged more leniently
 * than a live frame (CLAUDE.md, "things that look like bugs but are
 * deliberate").
 */

export type CaptureSource = "scanner" | "upload" | "camera";

export interface QualityReading {
  /** Variance of the Laplacian. Higher is sharper. */
  sharpness: number;
  /** Mean luminance, 0-255. */
  brightness: number;
  /** Share of pixels at or near full white — glare from overhead lighting. */
  glare: number;
  width: number;
  height: number;
}

export interface QualityGate {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
}

const SHARPNESS_MIN: Record<CaptureSource, number> = {
  scanner: 140,
  upload: 140,
  camera: 220,
};

export function gradeCapture(
  q: QualityReading,
  source: CaptureSource,
): QualityGate[] {
  const sharpMin = SHARPNESS_MIN[source];
  const shortEdge = Math.min(q.width, q.height);

  return [
    {
      key: "sharpness",
      label: "Sharpness",
      ok: q.sharpness >= sharpMin,
      detail:
        q.sharpness >= sharpMin
          ? `${Math.round(q.sharpness)}, above the ${sharpMin} threshold`
          : `${Math.round(q.sharpness)}, below the ${sharpMin} threshold. Hold the document flat and still.`,
    },
    {
      key: "resolution",
      label: "Resolution",
      // 600, because that is what the pipeline actually enforces:
      // `config/thresholds.yaml` sets `quality.min_short_edge_px: 600`. This
      // said 700, so the console refused to screen documents the backend would
      // have accepted - including every generated demo card, which is 1000x640.
      // A gate that is stricter than the thing it guards does not add safety,
      // it just makes the officer re-capture a document that was fine.
      //
      // The number is duplicated rather than fetched, and that is the standing
      // risk: nothing stops the two drifting again. `quality.doc_blur_min` and
      // SHARPNESS_MIN below are already apart (180 against 140) and are left
      // alone deliberately - the two are not measured on the same scale, so
      // aligning the digits would be a guess dressed as a fix.
      ok: shortEdge >= 600,
      detail:
        shortEdge >= 600
          ? `${q.width} by ${q.height} pixels`
          : `${q.width} by ${q.height} pixels. Move closer, or scan at a higher setting.`,
    },
    {
      key: "brightness",
      label: "Exposure",
      ok: q.brightness >= 55 && q.brightness <= 215,
      detail:
        q.brightness < 55
          ? "Too dark. Add light or move away from the shadow."
          : q.brightness > 215
            ? "Washed out. Reduce the light falling on the document."
            : `Mean luminance ${Math.round(q.brightness)}`,
    },
    {
      key: "glare",
      label: "Glare",
      ok: q.glare < 0.04,
      detail:
        q.glare < 0.04
          ? "No significant specular highlight"
          : `${(q.glare * 100).toFixed(1)}% of the frame is blown out. Tilt the document away from the light.`,
    },
  ];
}

export function isSubmittable(gates: QualityGate[]): boolean {
  // Resolution and sharpness are hard blocks: nothing downstream can recover a
  // machine-readable zone that was never resolved. Exposure and glare are
  // warnings — the officer may have no better light available.
  return gates
    .filter((g) => g.key === "sharpness" || g.key === "resolution")
    .every((g) => g.ok);
}

/**
 * Measure a frame. Downsamples to a fixed working width first, so the numbers
 * mean the same thing whether the source is a 300 dpi scan or a webcam.
 */
export function measure(source: CanvasImageSource, w: number, h: number): QualityReading {
  const WORK = 480;
  const scale = WORK / Math.max(w, h);
  const cw = Math.max(1, Math.round(w * scale));
  const ch = Math.max(1, Math.round(h * scale));

  const canvas = document.createElement("canvas");
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(source, 0, 0, cw, ch);
  const { data } = ctx.getImageData(0, 0, cw, ch);

  const grey = new Float32Array(cw * ch);
  let sum = 0;
  let blown = 0;
  for (let i = 0, p = 0; i < data.length; i += 4, p++) {
    const g = 0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2];
    grey[p] = g;
    sum += g;
    if (g > 246) blown++;
  }

  // Variance of the Laplacian — the standard cheap sharpness measure.
  let lapSum = 0;
  let lapSq = 0;
  let n = 0;
  for (let y = 1; y < ch - 1; y++) {
    for (let x = 1; x < cw - 1; x++) {
      const i = y * cw + x;
      const lap =
        4 * grey[i] - grey[i - 1] - grey[i + 1] - grey[i - cw] - grey[i + cw];
      lapSum += lap;
      lapSq += lap * lap;
      n++;
    }
  }
  const mean = lapSum / n;
  const variance = lapSq / n - mean * mean;

  return {
    sharpness: variance,
    brightness: sum / (cw * ch),
    glare: blown / (cw * ch),
    width: w,
    height: h,
  };
}
