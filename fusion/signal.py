"""FROZEN CONTRACT. See context/CONTRACTS.md §1.

Changes require agreement from the integration owner and must update
context/CONTRACTS.md and every implementation in the same commit.

There is no `weight` field and none gets added. Weights come from the document
profile at fusion time — a signal does not know its own importance.
"""
from dataclasses import dataclass
from typing import Literal, Optional

Verdict = Literal["pass", "fail", "inconclusive", "not_applicable"]
TrustClass = Literal["cryptographic", "arithmetic", "probabilistic", "unverified"]
Band = Literal["GREEN", "AMBER", "RED"]

#: Runs in the same direction as certainty. Mirrors frontend/src/contracts/signal.ts.
TRUST_ORDER: tuple[TrustClass, ...] = (
    "cryptographic",
    "arithmetic",
    "probabilistic",
    "unverified",
)


def trust_rank(t: TrustClass) -> int:
    return TRUST_ORDER.index(t)


@dataclass(frozen=True)
class Signal:
    id: str                 # dotted, stable: "mrz.checkdigit.dob"
    module: str             # extraction | validation | tamper | face
    tier: int               # 1 = always runs, 2 = escalated only
    verdict: Verdict
    confidence: float       # 0.0-1.0. For deterministic checks use 1.0.
    trust_class: TrustClass
    hard_fail: bool         # True bypasses scoring entirely -> RED
    anchor: str             # "field:dob" | "region:x1,y1,x2,y2" | "document"
    evidence: str           # one line, shown verbatim to the officer
    region: Optional[tuple] = None   # (x1,y1,x2,y2) for UI overlay
    latency_ms: int = 0


def to_json(s: Signal) -> dict:
    """Wire form. Matches frontend/src/contracts/signal.ts exactly."""
    return {
        "id": s.id,
        "module": s.module,
        "tier": s.tier,
        "verdict": s.verdict,
        "confidence": s.confidence,
        "trust_class": s.trust_class,
        "hard_fail": s.hard_fail,
        "anchor": s.anchor,
        "evidence": s.evidence,
        "region": list(s.region) if s.region else None,
        "latency_ms": s.latency_ms,
    }


def from_json(d: dict) -> Signal:
    r = d.get("region")
    return Signal(
        id=d["id"], module=d["module"], tier=d["tier"], verdict=d["verdict"],
        confidence=d["confidence"], trust_class=d["trust_class"],
        hard_fail=d["hard_fail"], anchor=d["anchor"], evidence=d["evidence"],
        region=tuple(r) if r else None, latency_ms=d.get("latency_ms", 0),
    )
