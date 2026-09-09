import { describe, expect, it } from "vitest";
import { gradeCapture, isSubmittable, type QualityReading } from "./quality";

const good: QualityReading = {
  sharpness: 300,
  brightness: 140,
  glare: 0.005,
  width: 1654,
  height: 1170,
};
const gate = (r: Partial<QualityReading>, src: "scanner" | "camera" = "scanner") =>
  gradeCapture({ ...good, ...r }, src);
const find = (gs: ReturnType<typeof gate>, key: string) => gs.find((g) => g.key === key)!;

describe("gradeCapture", () => {
  it("passes a clean scan", () => {
    expect(gate({}).every((g) => g.ok)).toBe(true);
    expect(isSubmittable(gate({}))).toBe(true);
  });

  it("judges a live frame more strictly than a document scan", () => {
    // A printed photograph is naturally softer than a camera capture, so the
    // same sharpness reading means different things by source.
    const s = 180;
    expect(find(gate({ sharpness: s }, "scanner"), "sharpness").ok).toBe(true);
    expect(find(gate({ sharpness: s }, "camera"), "sharpness").ok).toBe(false);
  });

  it("blocks submission on sharpness or resolution, never on light", () => {
    expect(isSubmittable(gate({ sharpness: 40 }))).toBe(false);
    expect(isSubmittable(gate({ width: 400, height: 300 }))).toBe(false);
    // The officer may have no better light available; those are warnings.
    expect(isSubmittable(gate({ brightness: 20 }))).toBe(true);
    expect(isSubmittable(gate({ glare: 0.5 }))).toBe(true);
  });

  it("tells the officer what to do, not what is wrong", () => {
    expect(find(gate({ sharpness: 40 }), "sharpness").detail).toMatch(/hold the document/i);
    expect(find(gate({ brightness: 20 }), "brightness").detail).toMatch(/add light/i);
    expect(find(gate({ glare: 0.2 }), "glare").detail).toMatch(/tilt the document/i);
    expect(find(gate({ width: 400, height: 300 }), "resolution").detail).toMatch(/move closer/i);
  });

  it("flags both ends of the exposure range", () => {
    expect(find(gate({ brightness: 20 }), "brightness").ok).toBe(false);
    expect(find(gate({ brightness: 250 }), "brightness").ok).toBe(false);
    expect(find(gate({ brightness: 140 }), "brightness").ok).toBe(true);
  });
});

describe("the resolution gate agrees with the pipeline", () => {
  it("accepts what config/thresholds.yaml accepts", () => {
    // `quality.min_short_edge_px: 600` in config/thresholds.yaml. This gate
    // used to demand 700, so the console blocked every generated demo card
    // (1000x640) with "Move closer" while the backend screened it happily.
    // A console stricter than the pipeline sends officers to re-capture
    // documents that were already good enough.
    const reading = { width: 1000, height: 640, sharpness: 2858, brightness: 120, glare: 0.1 };
    const gate = gradeCapture(reading, "upload").find((g) => g.key === "resolution");
    expect(gate?.ok).toBe(true);
  });

  it("still rejects a capture the pipeline would refuse", () => {
    const reading = { width: 900, height: 599, sharpness: 2858, brightness: 120, glare: 0.1 };
    const gate = gradeCapture(reading, "upload").find((g) => g.key === "resolution");
    expect(gate?.ok).toBe(false);
  });
});
