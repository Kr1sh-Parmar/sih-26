import { describe, expect, it } from "vitest";
import { faceMargin, gaugePosition } from "./faceMargin";

describe("faceMargin", () => {
  it("reports the signed margin from the threshold, not a percentage", () => {
    const r = faceMargin(0.41, 0.32);
    expect(r.band).toBe("match");
    expect(r.margin).toBeCloseTo(0.09, 5);
    expect(r.cosine).toBe(0.41);
  });

  it("puts a value inside the review band into review", () => {
    expect(faceMargin(0.35, 0.32).band).toBe("review");
    expect(faceMargin(0.29, 0.32).band).toBe("review");
  });

  it("rejects clearly below the threshold", () => {
    const r = faceMargin(0.11, 0.32);
    expect(r.band).toBe("no_match");
    expect(r.margin).toBeCloseTo(-0.21, 5);
  });

  it("never fails silently when no face was found", () => {
    for (const v of [null, undefined, NaN]) {
      const r = faceMargin(v, 0.32);
      expect(r.band).toBe("no_face");
      expect(r.margin).toBeNull();
    }
  });

  it("never produces a 0-100 figure — a stranger must not read as 50", () => {
    // cosine 0 is a stranger. ((0+1)/2)*100 = 50, which is the banned mapping.
    const r = faceMargin(0, 0.32);
    expect(r.band).toBe("no_match");
    const values = Object.values(r).filter((v) => typeof v === "number");
    for (const v of values) expect(Math.abs(v as number)).toBeLessThanOrEqual(1);
  });
});

describe("gaugePosition", () => {
  it("clamps to the drawable range", () => {
    expect(gaugePosition(-5)).toBe(0);
    expect(gaugePosition(5)).toBe(1);
  });

  it("places the threshold consistently", () => {
    expect(gaugePosition(0.4)).toBeCloseTo(0.5, 2);
  });
});
