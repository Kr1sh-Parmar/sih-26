"""FROZEN CONTRACT. See context/CONTRACTS.md §3.

Changes require agreement from the integration owner and must update
context/CONTRACTS.md and every implementation in the same commit.
"""
from dataclasses import dataclass, field

from fusion.signal import Signal, TrustClass, to_json


@dataclass
class Finding:
    anchor: str
    severity: float           # 0-1, noisy-OR over the group
    trust_class: TrustClass   # strongest class among members
    headline: str             # what the officer reads
    supporting: list = field(default_factory=list)   # list[Signal]
    region: tuple | None = None


def finding_to_json(f: Finding) -> dict:
    """Wire form. Matches frontend/src/contracts/finding.ts exactly."""
    return {
        "anchor": f.anchor,
        "severity": f.severity,
        "trust_class": f.trust_class,
        "headline": f.headline,
        "supporting": [to_json(s) for s in f.supporting],
        "region": list(f.region) if f.region else None,
    }
