"""Orchestration. Decode once, route by profile, run the tiers, fuse.

This is the only place that knows the order of things. Modules do not call each
other and do not know the tier they are in; the pipeline decides.

Results are yielded as they land rather than returned at the end, so the socket
can stream them. The officer sees validation at roughly 300 ms and the rest
follows - perceived latency is what is actually being optimised here, and it is
nearly free (TECHNICAL-SPEC.md section 3).
"""
import time
from dataclasses import dataclass
from typing import Iterator

import numpy as np

from core.canonical import doc_hash, signed_fields
from core.decode import decode
from core.profiles import load_config, load_profile
from core.trust import TrustAnchorStore, Verification
from fusion.context import ScreeningContext
from fusion.evidence import cards
from fusion.findings import build_findings
from fusion.gate import decide
from fusion.score import Verdict, score
from fusion.signal import Signal
from modules import extraction, face, tamper
from modules import validation
from modules.validation import layer_a, layer_d

#: What the console is told, in the order it is told. Mirrors the Phase union in
#: frontend/src/contracts/events.ts - the reducer switches on these exact strings.
PHASES = ("decoding", "tier1", "gate", "tier2", "fusing", "done")

def model_versions() -> dict:
    """What actually ran, read live from the registry.

    This was a static dict reporting `None` forever, which is worse than
    useless in an audit log: it would keep claiming no detector was deployed
    long after one was, so a historical case could not be honestly re-scored.
    `None` now means genuinely absent.
    """
    from core import registry
    return registry.versions()


@dataclass
class Event:
    type: str
    payload: dict


@dataclass
class Result:
    ctx: ScreeningContext
    verdict: Verdict
    verification: Verification | None
    signals: list
    escalated: bool
    doc_hash: str


def build_context(image_bytes: bytes, doc_type: str, session_id: str,
                  prior_docs: list | None = None) -> ScreeningContext:
    """Decode ONCE. Nothing downstream reopens the file."""
    return ScreeningContext(
        session_id=session_id,
        image=decode(image_bytes),
        doc_type=doc_type,
        profile=load_profile(doc_type),
        prior_docs=list(prior_docs or []),
    )


def decode_live(image_bytes: bytes) -> np.ndarray:
    """The live camera frame. A second capture, not a second read of the first.

    Decode-once (CLAUDE.md rule 6) is about not re-reading the *document*; the
    live frame is a different photograph and has to enter somewhere.
    """
    return decode(image_bytes)


def screen(ctx: ScreeningContext, *, anchors: TrustAnchorStore | None = None,
           store=None, uploaded: bool = False,
           raw: bytes | None = None) -> Iterator[Event]:
    """Run the pipeline, yielding events as each stage completes.

    `raw` is the original file bytes. They are threaded through as an argument
    rather than added to `ScreeningContext`, which is a frozen contract - and
    only the tampering module wants them, for the two checks that read file
    structure rather than pixels. Nothing re-decodes them.
    """
    started = time.perf_counter()
    yield Event("phase", {"phase": "decoding"})
    yield Event("phase", {"phase": "tier1"})

    # --- Tier 1 -----------------------------------------------------------
    for s in extraction.run(ctx, uploaded=uploaded):
        ctx.signals.append(s)
        yield Event("signal", {"signal": s})

    verification = layer_a.verified_payload(ctx, anchors)
    if verification and verification.ok:
        extraction.seed_from_payload(ctx, verification.payload)

    for s in validation.run(ctx, anchors=anchors, store=store):
        ctx.signals.append(s)
        yield Event("signal", {"signal": s})

    for s in tamper.run(ctx, tier=1, uploaded=uploaded, raw=raw):
        ctx.signals.append(s)
        yield Event("signal", {"signal": s})

    for s in face.run(ctx, tier=1):
        ctx.signals.append(s)
        yield Event("signal", {"signal": s})

    # --- Gate -------------------------------------------------------------
    yield Event("phase", {"phase": "gate"})
    decision, reason = decide(ctx.signals, ctx.profile)
    escalated = decision == "escalate"

    if escalated:
        # About 15% of documents get here. Running deep forensics on the other
        # 85% would blow the budget for no gain (D6).
        yield Event("phase", {"phase": "tier2"})
        for s in tamper.run(ctx, tier=2, uploaded=uploaded, raw=raw):
            if s.tier == 2:
                ctx.signals.append(s)
                yield Event("signal", {"signal": s})
        for s in face.run(ctx, tier=2, store=store,
                          doc_hash=_hash_of(ctx, verification)):
            if s.tier == 2:
                ctx.signals.append(s)
                yield Event("signal", {"signal": s})

    # --- Fusion -----------------------------------------------------------
    yield Event("phase", {"phase": "fusing"})
    proven = signed_fields(verification.payload) if verification and verification.ok else set()
    findings = build_findings(ctx.signals, ctx.field_boxes)
    verdict = score(ctx.signals, ctx.profile, findings, signed_fields=proven)

    yield Event("findings", {"findings": verdict.findings})
    yield Event("verdict", {
        "band": verdict.band,
        "score": round(verdict.score, 3),
        "coverage": round(verdict.coverage, 3),
        "disclosure": _disclosure(ctx, verification),
        "reason": verdict.reason,
    })
    yield Event("cards", {"cards": cards(ctx.signals, verdict.findings, ctx.profile)})
    yield Event("phase", {"phase": "done"})
    yield Event("done", {
        "result": Result(ctx, verdict, verification, ctx.signals, escalated,
                         _hash_of(ctx, verification)),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "gate": {"decision": decision, "reason": reason},
    })


def _disclosure(ctx: ScreeningContext, verification: Verification | None) -> str | None:
    """Only shown when a reference-issuer signature actually verified.

    Rendering it on every document would turn it into furniture the officer
    stops reading, which is the opposite of the point. A reference verification
    must not look like a government one (DEMO.md Scene 3).
    """
    if verification and verification.ok and verification.is_reference:
        return ctx.profile.get("disclosure")
    return None


def _hash_of(ctx: ScreeningContext, verification: Verification | None) -> str:
    """SHA-256 over the canonical fields, for the audit log."""
    payload = {"doc_type": ctx.doc_type}
    if verification and verification.ok:
        payload.update(verification.payload)
    else:
        from core.canonical import FIELD_ORDER
        for name in FIELD_ORDER:
            f = ctx.fields.get(name)
            if f and f.value:
                payload[name] = f.value
    payload.pop("issuer_id", None)
    return doc_hash(payload)


def persist(result: Result, store, officer_id: str | None = None) -> str:
    """Record the event. Full signal list, hashed identity number, no raw PII.

    The face embedding is stored; the crop is not. A 512-float vector cannot be
    turned back into a face, and raw face images do not outlive the session
    (TECHNICAL-SPEC.md section 9). Without this the 1:N gallery has nothing to
    search and would report "no duplicate" forever, which reads as a pass.
    """
    number = result.ctx.fields.get("id_number")
    event_id = _record(result, store, number, officer_id)
    embedding = result.ctx.embeddings.get("live") or result.ctx.embeddings.get("doc")
    if embedding is not None:
        store.add_face(event_id, embedding)
    return event_id


def _record(result: Result, store, number, officer_id) -> str:
    return store.record_event(
        session_id=result.ctx.session_id,
        doc_type=result.ctx.doc_type,
        doc_hash=result.doc_hash,
        verdict=result.verdict.band,
        score=result.verdict.score,
        coverage=result.verdict.coverage,
        signals=result.signals,
        model_versions=model_versions(),
        id_number=number.value if number else None,
        officer_id=officer_id,
    )


def as_prior(result: Result) -> dict:
    """Feed a screened document forward as ground truth for the next one."""
    return layer_d.as_prior(
        result.ctx.doc_type, result.verification,
        {k: v.value for k, v in result.ctx.fields.items() if k != "signed_payload"},
    )


# --------------------------------------------------------------- re-scoring

def profile_with_weights(doc_type: str, weights: dict | None) -> dict:
    """A profile with some weights overridden, without touching the cached one.

    `load_profile` is `lru_cache`d, so the dict it returns is shared by every
    request in the process. Mutating it would change the operating point for
    everyone who screened afterwards - and silently, since nothing re-reads the
    file. Copy first.
    """
    import copy

    profile = load_profile(doc_type)
    if not weights:
        return profile
    clone = copy.deepcopy(profile)
    clone["weights"].update({str(k): float(v) for k, v in weights.items()})
    return clone


def rescore(signals: list[Signal], profile: dict, bands: dict,
            signed_fields: set[str] | None = None) -> Verdict:
    """`fusion.score.score()` with the bands injected instead of read from config.

    ponytail: this restates score()'s ordering - hard fail, then coverage
    floor, then cryptographic precedence, then bands - because the coverage
    floor is itself band-dependent, so it cannot simply be re-banded after the
    fact. Every piece of arithmetic is imported rather than copied; only the
    order is written twice. `tests/test_rescore.py` asserts this agrees with
    `score()` exactly when handed the configured bands, which is the guard
    against the two drifting apart. The real fix is a `bands=` parameter on
    `score()`, which is a frozen-contract-adjacent change and not mine to make.
    """
    from fusion.score import (apply_crypto_precedence, coverage, hard_failures,
                              score_findings)

    cfg = load_config("bands")
    cov = coverage(signals, profile)

    hard = hard_failures(signals, profile)
    if hard:
        return Verdict("RED", 1.0, cov, [], hard[0].evidence)

    findings = build_findings(signals)
    if cov < float(bands["coverage_floor"]):
        return Verdict("AMBER", score_findings(findings, signals, profile), cov,
                       findings, cfg["messages"]["low_coverage"])

    kept = apply_crypto_precedence(findings, signed_fields or set())
    value = score_findings(kept, signals, profile)
    if value < float(bands["green_below"]):
        band = "GREEN"
    elif value < float(bands["amber_below"]):
        band = "AMBER"
    else:
        band = "RED"
    return Verdict(band, value, cov, kept, None)
