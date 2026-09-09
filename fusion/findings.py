"""Group correlated signals into findings. context/CONTRACTS.md section 3.

One altered date of birth fires four signals - VIZ/MRZ mismatch, tamper mask
overlap, font inconsistency, age mismatch. Summing them inflates the score
about 4x in exactly the cases that matter most, and shows the officer four
bullets for one problem (D8). So signals are grouped by anchor and combined
with noisy-OR inside the group.
"""
from core.profiles import reliability
from fusion.finding import Finding
from fusion.signal import Signal, trust_rank


def _parse_region_anchor(anchor: str) -> tuple | None:
    if not anchor.startswith("region:"):
        return None
    try:
        return tuple(float(v) for v in anchor[len("region:"):].split(","))
    except ValueError:
        return None


def _iou(a: tuple, b: tuple) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def resolve_anchor(anchor: str, field_boxes: dict, min_iou: float = 0.30) -> str:
    """A region anchor becomes a field anchor when it overlaps a known field box.

    Without this a tamper signal over the date of birth and the VIZ/MRZ mismatch
    on the same date land in two different findings, and the officer reads one
    problem twice.
    """
    region = _parse_region_anchor(anchor)
    if region is None:
        return anchor
    best, best_iou = None, min_iou
    for name, box in (field_boxes or {}).items():
        score = _iou(region, tuple(box))
        if score > best_iou:
            best, best_iou = name, score
    return f"field:{best}" if best else anchor


def group_severity(signals: list[Signal]) -> float:
    """Noisy-OR over the failing members. Passing members contribute nothing.

    Two independent checks each 60% reliable and both failing give 0.84, not
    1.2. Agreement raises confidence; it does not stack past certainty.
    """
    p = 1.0
    for s in signals:
        if s.verdict != "fail":
            continue
        p *= 1 - min(1.0, max(0.0, s.confidence)) * reliability(s.id)
    return 1.0 - p


def _dominant(signals: list[Signal]) -> Signal:
    """The signal the officer should read first for this anchor."""
    failures = [s for s in signals if s.verdict == "fail"]
    pool = failures or signals
    return max(
        pool,
        key=lambda s: (-trust_rank(s.trust_class), s.confidence * reliability(s.id)),
    )


def build_findings(signals: list[Signal], field_boxes: dict | None = None) -> list[Finding]:
    """Signals in, findings out. One finding per anchor."""
    groups: dict[str, list[Signal]] = {}
    for s in signals:
        if s.verdict == "not_applicable":
            continue  # excluded entirely - it is not a gap, the check does not apply
        groups.setdefault(resolve_anchor(s.anchor, field_boxes or {}), []).append(s)

    findings = []
    for anchor, members in groups.items():
        lead = _dominant(members)
        # The class of the evidence that drives the CLAIM, not of the strongest
        # signal that happens to share the anchor.
        #
        # It used to be the strongest class present. So a clean cryptographic
        # pass sharing an anchor with a failing tamper heuristic produced a
        # finding labelled `cryptographic` whose headline was the heuristic -
        # a guess wearing the authority of a signature, which is the exact
        # failure this system exists to prevent.
        #
        # It also disabled crypto precedence outright: that finding landed in
        # the cryptographic set carrying severity, so `any(severity > 0)` was
        # true and nothing was ever suppressed. The rule could not fire in the
        # one situation it was written for.
        #
        # Same pool as `_dominant`, so the headline and the class an officer
        # reads beside it can no longer disagree.
        failing = [m for m in members if m.verdict == "fail"]
        findings.append(Finding(
            anchor=anchor,
            severity=group_severity(members),
            trust_class=min((m.trust_class for m in (failing or members)),
                            key=trust_rank),
            # ponytail: headline is the dominant signal's evidence. Those strings
            # are already written for an officer to read; a separate headline
            # table would be a second place to keep the same sentence correct.
            headline=lead.evidence,
            supporting=sorted(
                members,
                key=lambda m: (m.verdict != "fail", trust_rank(m.trust_class), -m.confidence),
            ),
            region=lead.region,
        ))

    # Worst first, and within equal severity the more certain class first.
    findings.sort(key=lambda f: (-f.severity, trust_rank(f.trust_class)))
    return findings
