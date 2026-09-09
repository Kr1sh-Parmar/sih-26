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

    # There is deliberately NO separate threshold for documents that carry a
    # verified signature, and this is worth stating because the obvious design
    # is the opposite one.
    #
    # A branch here used to escalate un-signed documents above a *higher*
    # threshold (0.25) than the general rule below (0.15), which meant it never
    # changed a decision - only the reason string. Measured across the whole
    # range, the signed and unsigned columns were identical.
    #
    # The tempting repair is to invert it: let a signature buy the document
    # more benefit of the doubt in a grey zone. That is refused. D48 measured
    # what a signature actually proves - the payload, and nothing whatever
    # about the ink on the card. A verified signature must not buy a document
    # less forensic scrutiny of its printing, which is exactly the assumption
    # that let a retyped card pass twice already.
    #
    # So every document escalates on the same tamper threshold, and the config
    # carries one number instead of two that contradicted each other.

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
