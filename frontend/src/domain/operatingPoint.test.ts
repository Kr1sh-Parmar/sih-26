import { describe, expect, it } from "vitest";
import {
  curve,
  dailyConsequence,
  equalErrorRate,
  far,
  frr,
} from "./operatingPoint";

describe("operating point", () => {
  it("moves the two errors in opposite directions", () => {
    // The whole point of the screen: there is no threshold that avoids both.
    expect(frr(0.5)).toBeGreaterThan(frr(0.2));
    expect(far(0.5)).toBeLessThan(far(0.2));
  });

  it("keeps both rates inside 0 and 1 across the range", () => {
    for (const p of curve()) {
      expect(p.far).toBeGreaterThanOrEqual(0);
      expect(p.far).toBeLessThanOrEqual(1);
      expect(p.frr).toBeGreaterThanOrEqual(0);
      expect(p.frr).toBeLessThanOrEqual(1);
    }
  });

  it("finds a crossing where the two rates meet", () => {
    const { t, rate } = equalErrorRate();
    expect(t).toBeGreaterThan(0);
    expect(t).toBeLessThan(0.9);
    expect(Math.abs(far(t) - frr(t))).toBeLessThan(0.005);
    expect(rate).toBeGreaterThan(0);
  });

  it("reproduces the figure the demo quotes", () => {
    // DEMO.md Scene 4: "At 5,000 passengers a day, a 2% false rejection rate is
    // 100 secondary inspections." The default 0.32 threshold must land near it,
    // or the narration and the screen disagree in front of the panel.
    const c = dailyConsequence(0.32, 5000);
    expect(c.stopped).toBeGreaterThan(60);
    expect(c.stopped).toBeLessThan(140);
    // and far fewer impostors than genuine travellers, at this operating point
    expect(c.admitted).toBeLessThan(c.stopped);
  });

  it("counts people, not fractions", () => {
    const c = dailyConsequence(0.32, 5000);
    expect(Number.isInteger(c.stopped)).toBe(true);
    expect(Number.isInteger(c.admitted)).toBe(true);
  });
});
