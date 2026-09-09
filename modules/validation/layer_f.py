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

Both of those are now in place: `screening_events.post_id` records which
checkpoint screened a document, and `config/posts.yaml` gives the network its
geography. What has not changed is the default. With `SCREENING_POST_ID` unset
this layer still reports `not_applicable`, because a single-post installation
genuinely cannot observe transit - and a check that fires on the same document
being scanned twice at one counter is a confident accusation every time an
officer re-captures, which teaches them to stop reading the evidence list.
"""
import math
import time
from datetime import datetime

from core.profiles import describe_start, load_config
from core.store import post_id as store_post_id
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import normalize as N
from modules.validation import anchor_for, box_of, emit, value_of


#: Re-exported from the store, which is what writes it onto every event. Two
#: readings of one environment variable is one too many.
post_id = store_post_id


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

    return (_transit(ctx, store, number, started)
            or _seen_before(ctx, store, number, started))


def haversine_km(a: dict, b: dict) -> float:
    """Great-circle distance between two posts, in kilometres."""
    lat1, lon1, lat2, lon2 = map(math.radians,
                                 (a["lat"], a["lon"], b["lat"], b["lon"]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def _transit(ctx: ScreeningContext, store, number: str,
             started: float) -> list[Signal]:
    """The same document at two posts, too far apart in too little time.

    Only prior screenings at a *different* post are considered. The same
    document twice at this post is a re-capture or a secondary inspection, and
    both are ordinary - `_seen_before` reports those as context instead.

    Returns [] when there is nothing to say, so the caller falls through to
    that context rather than emitting two signals about one document.
    """
    here = post_id()
    cfg = load_config("posts")
    posts, limit = cfg["posts"], cfg["max_ground_speed_kmh"]

    elsewhere = [e for e in store.seen_document_number(
        N.id_number(number), exclude_session=ctx.session_id)
        if e.get("post_id") and e["post_id"] != here]
    if not elsewhere:
        return []

    latest = max(elsewhere, key=lambda e: e["created_at"])
    there = latest["post_id"]
    try:
        hours = ((datetime.utcnow() - datetime.fromisoformat(latest["created_at"]))
                 .total_seconds() / 3600)
    except (TypeError, ValueError):
        return []

    if here not in posts or there not in posts:
        # A post outside the table. The distance is unmeasurable, and inventing
        # one would be worse than saying so - but the officer should still know
        # the document was presented somewhere else.
        return [emit(
            ctx.profile, "validation.history.impossible_transit", "inconclusive",
            f"This document was screened at post {there} "
            f"{_ago(hours)}, but that post is not in this network's location "
            f"table, so the journey could not be checked for plausibility.",
            trust="probabilistic", confidence=0.0,
            anchor=anchor_for("id_number"), region=box_of(ctx, "id_number"),
            started=started,
        )]

    km = haversine_km(posts[here], posts[there])
    a, b = posts[there]["name"], posts[here]["name"]

    if hours > 0 and km / hours > limit:
        need = km / limit
        return [emit(
            ctx.profile, "validation.history.impossible_transit", "fail",
            f"This document was screened at {a} {_ago(hours)} and is now at "
            f"{b}. That is {km:.0f} km apart, which cannot be travelled by road "
            f"in {_span(hours)} - it needs at least {_span(need)}. Either the "
            f"document has been duplicated, or one of the two crossings was "
            f"recorded against the wrong document.",
            trust="probabilistic", confidence=0.8,
            anchor=anchor_for("id_number"), region=box_of(ctx, "id_number"),
            started=started,
        )]

    return [emit(
        ctx.profile, "validation.history.impossible_transit", "pass",
        f"This document was screened at {a} {_ago(hours)}; the journey to {b} "
        f"is {km:.0f} km and the timing is consistent with it.",
        trust="probabilistic", confidence=0.6,
        anchor=anchor_for("id_number"), region=box_of(ctx, "id_number"),
        started=started,
    )]


def _ago(hours: float) -> str:
    return (f"{hours * 60:.0f} minutes ago" if hours < 1
            else f"{hours:.0f} hours ago" if hours < 48
            else f"{hours / 24:.0f} days ago")


def _span(hours: float) -> str:
    return (f"{hours * 60:.0f} minutes" if hours < 1
            else f"{hours:.1f} hours" if hours < 48
            else f"{hours / 24:.1f} days")


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

    when = _ago(hours)
    return [emit(
        ctx.profile, "validation.history.impossible_transit", "pass",
        f"{describe_start(ctx.profile['doc_type'])} with this number was last "
        f"screened at this post {when}, {len(prior)} time"
        f"{'s' if len(prior) != 1 else ''} in total",
        trust="probabilistic", confidence=0.6,
        anchor=anchor_for("id_number"), region=box_of(ctx, "id_number"),
        started=started,
    )]
