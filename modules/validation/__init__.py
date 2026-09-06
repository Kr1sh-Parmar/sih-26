"""Validation, six layers. context/MODULES.md, Module 2.

Every layer is a pure function of the context: no I/O, no mutation beyond the
signals it returns. Layers A and E need a trust anchor store and a watchlist,
which are injected rather than opened, so each layer stays unit-testable with a
hand-built ScreeningContext and no fixture on disk.

Layers A to D combined are budgeted at under 15 ms. They are the backbone and
the fast path: a checksum failure, an invalid signature, an expired document or
a watchlist hit returns RED before a single model runs.
"""
import time

from fusion.context import ScreeningContext
from fusion.signal import Signal


def emit(profile: dict, sid: str, verdict: str, evidence: str, *,
         trust="arithmetic", confidence=1.0, anchor="document", tier=1,
         region=None, started=None) -> Signal:
    """Build a validation Signal, taking hard_fail from the profile.

    A module cannot decide its own importance, and it should not have to
    remember which of six documents treats its check as fatal.
    """
    from core.profiles import is_hard_fail
    return Signal(
        id=sid, module="validation", tier=tier, verdict=verdict,
        confidence=confidence, trust_class=trust,
        hard_fail=is_hard_fail(profile, sid), anchor=anchor,
        evidence=evidence, region=region,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0,
    )


def value_of(ctx: ScreeningContext, field: str) -> str | None:
    f = ctx.fields.get(field)
    return f.value if f and f.value else None


def raw_of(ctx: ScreeningContext, field: str) -> str | None:
    f = ctx.fields.get(field)
    return f.raw if f and f.raw else None


def box_of(ctx: ScreeningContext, field: str):
    f = ctx.fields.get(field)
    if f and f.box:
        return tuple(f.box)
    box = ctx.field_boxes.get(field)
    return tuple(box) if box else None


def anchor_for(field: str) -> str:
    return f"field:{field}"


def run(ctx: ScreeningContext, *, anchors=None, store=None) -> list[Signal]:
    """All six layers, in order. Returns signals; does not mutate ctx.signals."""
    from modules.validation import layer_a, layer_b, layer_c, layer_d, layer_e, layer_f

    signals: list[Signal] = []
    signals += layer_a.run(ctx, anchors=anchors)
    signals += layer_b.run(ctx)
    signals += layer_c.run(ctx)
    signals += layer_d.run(ctx)
    if store is not None:
        signals += layer_e.run(ctx, store=store)
        signals += layer_f.run(ctx, store=store)
    return signals
