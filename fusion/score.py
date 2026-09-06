"""Verdict, score and coverage. context/CONTRACTS.md section 6.

Order matters and is not negotiable:
  1. hard fail wins outright, without scoring
  2. coverage floor - inconclusive is not pass
  3. cryptographic precedence
  4. weighted sum over findings
  5. bands
"""
from dataclasses import dataclass

from core.profiles import is_hard_fail, load_config, weight_for
from fusion.finding import Finding
from fusion.signal import Band, Signal


@dataclass(frozen=True)
class Verdict:
    band: Band
    score: float
    coverage: float
    findings: list
    reason: str | None = None


def hard_failures(signals: list[Signal], profile: dict) -> list[Signal]:
    """Signals that bypass scoring entirely.

    The profile is the authority - a module that forgot to set the flag still
    hard-fails if the profile says the id does.
    """
    return [
        s for s in signals
        if s.verdict == "fail" and (s.hard_fail or is_hard_fail(profile, s.id))
    ]


def coverage(signals: list[Signal], profile: dict) -> float:
    """Fraction of applicable check weight that actually produced an answer.

    A blurry photo makes the face check inconclusive. If inconclusive counted
    as zero contribution the total would stay low and the verdict would be
    GREEN - clearing an impostor because the camera was out of focus (D9).

    `not_applicable` is different and leaves the denominator: Aadhaar genuinely
    has no MRZ, so that check is not a gap.
    """
    applicable = [s for s in signals if s.verdict != "not_applicable"]
    if not applicable:
        return 0.0
    ran = [s for s in applicable if s.verdict != "inconclusive"]
    total = sum(weight_for(profile, s.id) for s in applicable)
    if total <= 0:
        # Nothing carried weight, so coverage is unmeasurable. Say so by
        # failing the floor rather than by quietly passing it.
        return 0.0
    return sum(weight_for(profile, s.id) for s in ran) / total


def apply_crypto_precedence(findings: list[Finding], signed_fields: set[str]) -> list[Finding]:
    """An ELA hotspot over a cryptographically signed date of birth is noise.

    Only fires when every cryptographic finding is clean. One failing signature
    and the probabilistic evidence is exactly what the officer needs.
    """
    crypto = [f for f in findings if f.trust_class == "cryptographic"]
    if not crypto or any(f.severity > 0 for f in crypto):
        return findings
    return [
        f for f in findings
        if not (f.trust_class == "probabilistic" and f.anchor in signed_fields)
    ]


def _finding_weight(f: Finding, profile: dict) -> float:
    """Profile weight of a finding: the weight its failing signals carry."""
    return sum(weight_for(profile, s.id) for s in f.supporting if s.verdict == "fail")


def score_findings(findings: list[Finding], signals: list[Signal], profile: dict) -> float:
    """Weighted sum across findings, renormalised over the signals that ran.

    Renormalising over `ran` rather than over everything declared means a
    document whose checks mostly could not execute does not get a flattering
    low score - it gets caught by the coverage floor instead.
    """
    ran = [s for s in signals if s.verdict not in ("not_applicable", "inconclusive")]
    denom = sum(weight_for(profile, s.id) for s in ran)
    if denom <= 0:
        return 0.0
    numer = sum(f.severity * _finding_weight(f, profile) for f in findings)
    return min(1.0, max(0.0, numer / denom))


def band_for(score: float) -> Band:
    bands = load_config("bands")["bands"]
    if score < bands["green_below"]:
        return "GREEN"
    if score < bands["amber_below"]:
        return "AMBER"
    return "RED"


def score(
    signals: list[Signal],
    profile: dict,
    findings: list[Finding],
    signed_fields: set[str] | None = None,
) -> Verdict:
    cfg = load_config("bands")
    cov = coverage(signals, profile)

    hard = hard_failures(signals, profile)
    if hard:
        # Straight to RED. Ordering keeps the hard fail visible as the reason.
        return Verdict("RED", 1.0, cov, findings, hard[0].evidence)

    if cov < cfg["coverage_floor"]:
        return Verdict("AMBER", score_findings(findings, signals, profile), cov,
                       findings, cfg["messages"]["low_coverage"])

    kept = apply_crypto_precedence(findings, signed_fields or set())
    value = score_findings(kept, signals, profile)
    return Verdict(band_for(value), value, cov, kept)
