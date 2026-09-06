"""Layer F - temporal and behavioural. Framework only, and it says so.

Cut-list item 3, honestly: the framework is in place and it needs deployment
history to be meaningful. On a machine that has screened forty documents,
"impossible transit" is a sentence with nothing behind it.

Why it does not fire today
--------------------------
Impossible transit means the same document appeared at *two different posts*
too far apart in too little time. We record no post identifier, so the only
thing this layer can actually observe is the same document being screened
twice on the same machine - which is what a re-capture and a secondary
inspection both look like. Firing on that produces a confident accusation
every time an officer scans a document a second time, and an officer who sees
one false "impossible transit" stops reading the whole evidence list.

So the transit check reports `not_applicable` and stays out of the coverage
denominator. What is real - that this document number has been seen here
before, and when - is reported as ordinary context the officer can use.

ponytail: needs a post identifier on screening_events plus a distance table
between posts. Both are deployment facts, not code. Add the column and set
SCREENING_POST_ID when there is more than one post.
"""
import os
import time
from datetime import datetime

from core.profiles import describe_start
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import normalize as N
from modules.validation import anchor_for, box_of, emit, value_of


def post_id() -> str | None:
    """Which checkpoint this machine is. None until a deployment sets it."""
    return os.environ.get("SCREENING_POST_ID") or None


def run(ctx: ScreeningContext, store) -> list[Signal]:
    started = time.perf_counter()
    number = value_of(ctx, "id_number")

    if not number:
        return [emit(ctx.profile, "validation.history.impossible_transit",
                     "inconclusive",
                     "The identity number could not be read, so this document "
                     "could not be checked against previous crossings",
                     trust="probabilistic", confidence=0.0, started=started)]

    if post_id() is None:
        return [emit(
            ctx.profile, "validation.history.impossible_transit", "not_applicable",
            "Transit history needs more than one checkpoint reporting in. This "
            "post is not configured as part of a network, so no crossing "
            "pattern can be checked.",
            trust="probabilistic", started=started,
        ) ] + _seen_before(ctx, store, number, started)

    return _seen_before(ctx, store, number, started)


def _seen_before(ctx: ScreeningContext, store, number: str,
                 started: float) -> list[Signal]:
    """Context, not an accusation: has this number been screened here before?"""
    prior = store.seen_document_number(N.id_number(number),
                                       exclude_session=ctx.session_id)
    if not prior:
        return []

    latest = max(prior, key=lambda e: e["created_at"])
    try:
        seen = datetime.fromisoformat(latest["created_at"])
        hours = (datetime.utcnow() - seen).total_seconds() / 3600
    except (TypeError, ValueError):
        return []

    when = (f"{hours * 60:.0f} minutes ago" if hours < 1
            else f"{hours:.0f} hours ago" if hours < 48
            else f"{hours / 24:.0f} days ago")
    return [emit(
        ctx.profile, "validation.history.impossible_transit", "pass",
        f"{describe_start(ctx.profile['doc_type'])} with this number was last "
        f"screened at this post {when}, {len(prior)} time"
        f"{'s' if len(prior) != 1 else ''} in total",
        trust="probabilistic", confidence=0.6,
        anchor=anchor_for("id_number"), region=box_of(ctx, "id_number"),
        started=started,
    )]
