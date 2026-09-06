"""Layer E - external lookups against local tables. No network, ever.

Watchlist by document number and by name. Seeded from the OFAC SDN list and the
UN Consolidated List, which are real, free and public - and which give the
lookup genuine name-matching problems (transliteration variants, aliases,
partial dates of birth) that an invented table would not (D21).

ponytail: exact match on a normalised, order-insensitive name key, plus exact
match on document number. That catches "GHARAT PRADEEP" against
"Pradeep Gharat" but not "Prodeep Ghorat". Fuzzy and phonetic matching is
Phase 2 and is the part a panel will probe - the ceiling is stated here rather
than hidden behind a number.
"""
import json
import time

from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import normalize as N
from modules.validation import anchor_for, box_of, emit, value_of


def run(ctx: ScreeningContext, store) -> list[Signal]:
    return _watchlist(ctx, store)


def _watchlist(ctx: ScreeningContext, store) -> list[Signal]:
    started = time.perf_counter()
    profile = ctx.profile

    if store.watchlist_size() == 0:
        return [emit(profile, "validation.watchlist.hit", "inconclusive",
                     "The watchlist is empty, so no check against it was made",
                     confidence=0.0, started=started)]

    number = value_of(ctx, "id_number")
    name = value_of(ctx, "name")
    dob = value_of(ctx, "dob")

    if not number and not name:
        return [emit(profile, "validation.watchlist.hit", "inconclusive",
                     "Neither the identity number nor the name could be read, so "
                     "no watchlist check was possible",
                     confidence=0.0, started=started)]

    if number:
        for row in store.watchlist_by_document(N.id_number(number)):
            return [emit(
                profile, "validation.watchlist.hit", "fail",
                f"Document number matches {row['name']} on the {row['source']} list",
                anchor=anchor_for("id_number"), region=box_of(ctx, "id_number"),
                started=started,
            )]

    if name:
        for row in store.watchlist_by_name_key(N.watchlist_key(name)):
            # A name alone is a weaker hit than a document number. If we hold a
            # date of birth for the listed person and it does not match, say so
            # rather than detaining a namesake.
            if dob and row.get("dob") and N.iso_date(dob) != row["dob"]:
                return [emit(
                    profile, "validation.watchlist.hit", "inconclusive",
                    f"Name matches {row['name']} on the {row['source']} list, but "
                    f"the listed date of birth is {row['dob']} and this document "
                    f"gives {N.iso_date(dob)}. Manual check required.",
                    confidence=0.5, anchor=anchor_for("name"),
                    region=box_of(ctx, "name"), started=started,
                )]
            aliases = json.loads(row.get("aliases") or "[]")
            extra = f" (also known as {aliases[0]})" if aliases else ""
            return [emit(
                profile, "validation.watchlist.hit", "fail",
                f"Name matches {row['name']}{extra} on the {row['source']} list",
                anchor=anchor_for("name"), region=box_of(ctx, "name"),
                started=started,
            )]

    return [emit(profile, "validation.watchlist.hit", "pass",
                 "No match in the OFAC SDN or UN Consolidated list",
                 started=started)]
