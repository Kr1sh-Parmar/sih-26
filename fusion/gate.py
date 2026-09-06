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

    if _in_review_band(signals, "face.match.cosine", "face", "review_band"):
        return "escalate", "Face match falls in the review band"

    if _in_review_band(signals, "face.liveness.passive", "liveness", "uncertain_band"):
        return "escalate", "Passive liveness score is uncertain"

    if tamper > cfg["tamper_clear_below"]:
        return "escalate", f"Tamper indication {tamper:.2f} above the clear threshold"

    return "clear", "Deterministic checks clear, no escalation triggered"


def _in_review_band(signals: list[Signal], sid: str, group: str, key: str) -> bool:
    th = load_config("thresholds")["face"]
    band = th["doc_live"][key] if group == "face" else th[group][key]
    for s in signals:
        if s.id == sid and s.verdict in ("pass", "fail"):
            if band[0] <= s.confidence <= band[1]:
                return True
    return False
