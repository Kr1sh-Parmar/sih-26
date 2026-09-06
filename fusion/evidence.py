"""Evidence card assembly and ordering. context/CONTRACTS.md section 7.

Ordering is by decision impact, not by module and not by raw weight. A hard
fail with weight 0 outranks a 0.35 probabilistic finding.

  1. Hard fails                     always first, always visible
  2. Findings, by trust class then severity descending
  3. Coverage gaps                  "could not evaluate X"
  4. Passing cryptographic signals  always visible - reassurance
  5. Collapsed count of passing probabilistic signals
"""
from core.profiles import is_hard_fail
from fusion.finding import Finding, finding_to_json
from fusion.signal import Signal, to_json, trust_rank


def cards(signals: list[Signal], findings: list[Finding], profile: dict) -> dict:
    hard = [
        s for s in signals
        if s.verdict == "fail" and (s.hard_fail or is_hard_fail(profile, s.id))
    ]
    hard_ids = {s.id for s in hard}

    ordered = sorted(
        (f for f in findings if f.severity > 0),
        key=lambda f: (trust_rank(f.trust_class), -f.severity),
    )

    # A gap is a check that was applicable and could not answer. This is the
    # list that turns a low coverage number into something actionable.
    gaps = [s for s in signals if s.verdict == "inconclusive"]

    crypto_passes = [
        s for s in signals
        if s.verdict == "pass" and s.trust_class == "cryptographic"
    ]

    # Passing probabilistic signals are noise. Passing cryptographic signals are
    # the most reassuring thing an officer can see, so those never collapse.
    passing_probabilistic = [
        s for s in signals
        if s.verdict == "pass" and s.trust_class in ("probabilistic", "unverified")
    ]

    return {
        "hard_fails": [to_json(s) for s in hard],
        "findings": [finding_to_json(f) for f in ordered if not (
            len(f.supporting) == 1 and f.supporting[0].id in hard_ids
        )],
        "coverage_gaps": [
            {"id": s.id, "evidence": s.evidence, "region": list(s.region) if s.region else None}
            for s in gaps
        ],
        "cryptographic_passes": [to_json(s) for s in crypto_passes],
        "passing_collapsed": len(passing_probabilistic),
    }
