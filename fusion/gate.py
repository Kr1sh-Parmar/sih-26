"""The risk gate - the single branch point. context/CONTRACTS.md section 5.

About 85% of documents are resolved by deterministic checks in under 400 ms.
Running deep forensics, active liveness and 1:N search on all of them would
blow the budget for no gain (D6).
"""
from typing import Literal

from core.profiles import is_hard_fail, load_config, matches
from fusion.signal import Signal

Decision = Literal["hard_fail", "escalate", "clear"]

#: Any of these failing escalates to Tier 2 regardless of the tamper score.
ESCALATE_ON_FAIL = (
    "validation.vizmrz.*",
    "tamper.stamp.duplicate",
)


def tamper_score(signals: list[Signal]) -> float:
    """Worst single tamper failure. Deliberately not a sum - correlated tamper
    signals are combined properly at fusion time, not here."""
    fails = [s for s in signals if s.id.startswith("tamper.") and s.verdict == "fail"]
    return max((s.confidence for s in fails), default=0.0)


def decide(signals: list[Signal], profile: dict) -> tuple[Decision, str]:
    """Returns the decision and a one-line reason for the audit log."""
    cfg = load_config("thresholds")["gate"]

    for s in signals:
        if s.verdict == "fail" and (s.hard_fail or is_hard_fail(profile, s.id)):
            return "hard_fail", s.evidence

    tamper = tamper_score(signals)

    for s in signals:
        if s.verdict != "fail":
            continue
        if any(matches(p, s.id) for p in ESCALATE_ON_FAIL):
            return "escalate", s.evidence

    # A document with no cryptographic anchor gets less benefit of the doubt.
    crypto_ok = any(
        s.trust_class == "cryptographic" and s.verdict == "pass" for s in signals
    )
    if not crypto_ok and tamper > cfg["tamper_escalate_above"]:
        return "escalate", (
            f"No cryptographic anchor and tamper indication {tamper:.2f} "
            f"above {cfg['tamper_escalate_above']}"
        )

    if _uncertain(signals, "face.match.cosine"):
        return "escalate", "Face match falls in the review band"

    if _uncertain(signals, "face.liveness.passive"):
        return "escalate", "Passive liveness score is uncertain"

    if tamper > cfg["tamper_clear_below"]:
        return "escalate", f"Tamper indication {tamper:.2f} above the clear threshold"

    return "clear", "Deterministic checks clear, no escalation triggered"


def _uncertain(signals: list[Signal], sid: str) -> bool:
    """Escalate when a face check reached a verdict it is not sure of.

    This used to read `confidence` as if it carried the raw score and test it
    against the configured band directly. That made `confidence` mean two
    incompatible things at once: the gate wanted the cosine, and fusion's
    noisy-OR wants certainty. Reading it as a score meant a *confident*
    impostor - cosine 0.10, far below any threshold - arrived at fusion as
    confidence 0.10 and barely moved the score, which is the D10 failure one
    layer down: wrong in the direction that admits fraudsters.

    `confidence` is certainty now, everywhere, as the contract says. The face
    module scales it so that anything inside the configured review band comes
    out below 1.0, which is an exact translation of the old test.
    """
    for s in signals:
        if s.id == sid and s.verdict in ("pass", "fail") and s.confidence < 1.0:
            return True
    return False
