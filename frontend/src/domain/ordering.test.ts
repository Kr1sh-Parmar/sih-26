import { describe, expect, it } from "vitest";
import { orderEvidence, type EvidenceRow } from "./ordering";
import type { Finding, Signal } from "../contracts";

import green from "../fixtures/signals_green.json";
import red from "../fixtures/signals_red_hardfail.json";
import amber from "../fixtures/signals_amber_coverage.json";
import crossdoc from "../fixtures/signals_crossdoc_mismatch.json";

type Fixture = { signals: Signal[]; findings: Finding[] };
const load = (f: unknown) => f as unknown as Fixture;
const kinds = (rows: EvidenceRow[]) => rows.map((r) => r.kind);

function sig(over: Partial<Signal>): Signal {
  return {
    id: "x", module: "validation", tier: 1, verdict: "pass", confidence: 1,
    trust_class: "arithmetic", hard_fail: false, anchor: "document",
    evidence: "", region: null, latency_ms: 0, ...over,
  };
}

describe("orderEvidence — contract §7", () => {
  it("puts hard fails first, ahead of a higher-severity finding", () => {
    const hf = sig({ id: "validation.expiry.expired", verdict: "fail", hard_fail: true });
    const finding: Finding = {
      anchor: "field:dob", severity: 0.99, trust_class: "cryptographic",
      headline: "something worse-looking", supporting: [], region: null,
    };
    const rows = orderEvidence([finding], [hf]);
    expect(rows[0].kind).toBe("hard_fail");
  });

  it("sorts findings by trust class before severity", () => {
    const weakCrypto: Finding = {
      anchor: "a", severity: 0.1, trust_class: "cryptographic",
      headline: "crypto", supporting: [], region: null,
    };
    const strongProb: Finding = {
      anchor: "b", severity: 0.9, trust_class: "probabilistic",
      headline: "probabilistic", supporting: [], region: null,
    };
    const rows = orderEvidence([strongProb, weakCrypto], []);
    expect(rows.map((r) => (r.kind === "finding" ? r.finding.headline : r.kind)))
      .toEqual(["crypto", "probabilistic"]);
  });

  it("sorts by severity descending inside one trust class", () => {
    const mk = (sev: number, headline: string): Finding => ({
      anchor: headline, severity: sev, trust_class: "arithmetic",
      headline, supporting: [], region: null,
    });
    const rows = orderEvidence([mk(0.2, "low"), mk(0.8, "high"), mk(0.5, "mid")], []);
    expect(rows.map((r) => (r.kind === "finding" ? r.finding.headline : "?")))
      .toEqual(["high", "mid", "low"]);
  });

  it("shows inconclusive as a gap but never not_applicable", () => {
    const rows = orderEvidence([], [
      sig({ id: "blurred", verdict: "inconclusive" }),
      sig({ id: "no-mrz-on-aadhaar", verdict: "not_applicable" }),
    ]);
    expect(kinds(rows)).toEqual(["gap"]);
    expect(rows[0].kind === "gap" && rows[0].signal.id).toBe("blurred");
  });

  it("always renders a passing cryptographic signal on its own line", () => {
    const rows = orderEvidence([], [
      sig({ id: "validation.signature.valid", trust_class: "cryptographic" }),
    ]);
    expect(kinds(rows)).toEqual(["crypto_pass"]);
  });

  it("collapses passing probabilistic signals to one count row", () => {
    const rows = orderEvidence([], [
      sig({ id: "p1", trust_class: "probabilistic" }),
      sig({ id: "p2", trust_class: "probabilistic" }),
      sig({ id: "p3", trust_class: "probabilistic" }),
    ]);
    expect(kinds(rows)).toEqual(["passed"]);
    expect(rows[0].kind === "passed" && rows[0].count).toBe(3);
  });

  it("never repeats a signal already collapsed inside a finding", () => {
    const s = sig({ id: "validation.signature.valid", trust_class: "cryptographic" });
    const f: Finding = {
      anchor: "document", severity: 0, trust_class: "cryptographic",
      headline: "Signature verifies", supporting: [s], region: null,
    };
    const rows = orderEvidence([f], [s]);
    expect(kinds(rows)).toEqual(["finding"]);
  });
});

describe("orderEvidence — against the four fixtures", () => {
  it("Scene 2 leads with the date of birth hard fail", () => {
    const { signals, findings } = load(red);
    const rows = orderEvidence(findings, signals);
    expect(rows[0].kind).toBe("hard_fail");
    expect(rows[0].kind === "hard_fail" && rows[0].signal.id)
      .toBe("validation.vizmrz.dob_mismatch");
    // The officer has to be able to read both values off the card.
    expect(rows[0].kind === "hard_fail" && rows[0].signal.evidence)
      .toContain("1991-03-04");
    expect(rows[0].kind === "hard_fail" && rows[0].signal.evidence)
      .toContain("1991-08-04");
  });

  it("Scene 3 leads with the cross-document contradiction", () => {
    const { signals, findings } = load(crossdoc);
    const rows = orderEvidence(findings, signals);
    expect(rows[0].kind === "hard_fail" && rows[0].signal.id)
      .toBe("validation.crossdoc.dob_mismatch");
  });

  it("Scene 1 has no hard fail and surfaces the crypto pass", () => {
    const { signals, findings } = load(green);
    const rows = orderEvidence(findings, signals);
    expect(rows.some((r) => r.kind === "hard_fail")).toBe(false);
    const first = rows[0];
    expect(first.kind === "finding" && first.finding.trust_class).toBe("cryptographic");
  });

  it("Scene 5 reports the gaps and never claims the checks passed", () => {
    const { signals, findings } = load(amber);
    const rows = orderEvidence(findings, signals);
    const gaps = rows.filter((r) => r.kind === "gap");
    expect(gaps.length).toBeGreaterThan(0);
    // not_applicable must not leak into the gap list
    const gapIds = gaps.map((r) => (r.kind === "gap" ? r.signal.id : ""));
    expect(gapIds).not.toContain("tamper.digital.exif_software");
  });

  it("every fixture places all hard fails before every other row", () => {
    for (const f of [green, red, amber, crossdoc]) {
      const { signals, findings } = load(f);
      const k = kinds(orderEvidence(findings, signals));
      const lastHardFail = k.lastIndexOf("hard_fail");
      const firstOther = k.findIndex((x) => x !== "hard_fail");
      if (lastHardFail >= 0 && firstOther >= 0) {
        expect(lastHardFail).toBeLessThan(firstOther);
      }
    }
  });
});

describe("orderEvidence — regression", () => {
  it("keeps both findings when they share the document anchor", () => {
    // Scene 1 has a cryptographic and an arithmetic finding, both anchored to
    // "document". The five MRZ check digits are the whole claim of that scene;
    // an earlier version let the first finding's supporting set swallow it.
    const { signals, findings } = load(green);
    const rows = orderEvidence(findings, signals);
    const headlines = rows
      .filter((r) => r.kind === "finding")
      .map((r) => (r.kind === "finding" ? r.finding.headline : ""));
    expect(headlines).toContain("Signature verifies against a trusted issuer");
    expect(headlines).toContain("All five MRZ check digits are correct");
  });
});

describe("orderEvidence — one finding, not four bullets", () => {
  it("folds a same-anchor finding into the hard-fail row", () => {
    // Scene 2 fires the VIZ/MRZ mismatch plus three tamper signals on the same
    // date of birth. That is one story and must render as one card.
    const { signals, findings } = load(red);
    const rows = orderEvidence(findings, signals);
    const dobRows = rows.filter(
      (r) =>
        (r.kind === "hard_fail" && r.signal.anchor === "field:dob") ||
        (r.kind === "finding" && r.finding.anchor === "field:dob"),
    );
    expect(dobRows).toHaveLength(1);
    expect(dobRows[0].kind).toBe("hard_fail");
    // and the corroborating tamper checks come with it
    expect(dobRows[0].kind === "hard_fail" && dobRows[0].finding?.supporting.length)
      .toBeGreaterThan(1);
  });
});
