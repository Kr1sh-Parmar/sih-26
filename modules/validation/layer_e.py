"""Layer E - external lookups against local tables. No network, ever.

Watchlist by document number and by name. Seeded from the OFAC SDN list and the
UN Consolidated List, which are real, free and public - and which give the
lookup genuine name-matching problems (transliteration variants, aliases,
partial dates of birth) that an invented table would not (D21).

Three strengths of match, and they do not carry the same authority:

  document number, exact   -> `fail`, and `fail` here is a hard fail
  name key, exact          -> `fail`
  name, phonetic near-miss -> `inconclusive`, never `fail`

That last line is the load-bearing one. `validation.watchlist.hit` is listed
under `hard_fail` in all six profiles, so a `fail` verdict from this layer is
not a score contribution - it is RED, detain, on the spot. A near-match is a
guess about spelling, and a guess must never be able to detain somebody. It
reports what it found, names both spellings, and asks for a manual check.
"""
import difflib
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

        near = _nearest(store, name)
        if near:
            row, ratio = near
            return [emit(
                profile, "validation.watchlist.hit", "inconclusive",
                f"This name is spelled differently from, but sounds like, "
                f"{row['name']} on the {row['source']} list. Not treated as a "
                f"match - the spellings differ. Confirm against the listed "
                f"entry before deciding.",
                confidence=round(0.30 + 0.30 * ratio, 2),
                anchor=anchor_for("name"), region=box_of(ctx, "name"),
                started=started,
            )]

    return [emit(profile, "validation.watchlist.hit", "pass",
                 "No match in the OFAC SDN or UN Consolidated list",
                 started=started)]


# --------------------------------------------------------------- near matches
#
# Two names that sound alike are bucketed together by Soundex, then compared
# character by character. Soundex alone is far too loose to accuse anyone with -
# it collapses "Gharat" and "Ghorat", which is the point, but it also collapses
# plenty of genuinely different names - so it is used only to pick a handful of
# candidates out of 8,000, and the actual decision is the character ratio.
#
# Stdlib only, deliberately. `jellyfish` and `rapidfuzz` both do this better,
# and neither is worth a wheel in an image that ships to a border post and must
# install from a locked, offline requirements file.

#: Below this the two spellings are different names, not variants of one.
#:
#: Measured against the 8,256 loaded OFAC + UN entries: 60 listed names with one
#: vowel transliterated ("Pradeep" -> "Prodeep") were recovered 56 times, and 15
#: unrelated Indian names produced no near-match at all. "Prodeep Ghorat"
#: against "Pradeep Gharat" scores 0.857, which is where the floor sits.
NEAR_RATIO = 0.84

_SOUNDEX = {**{c: "1" for c in "BFPV"}, **{c: "2" for c in "CGJKQSXZ"},
            **{c: "3" for c in "DT"}, "L": "4",
            **{c: "5" for c in "MN"}, "R": "6"}


def soundex(token: str) -> str:
    """Classic Soundex. Four characters: initial plus three consonant codes."""
    token = "".join(c for c in token.upper() if c.isalpha())
    if not token:
        return ""
    out = token[0]
    previous = _SOUNDEX.get(token[0], "")
    for char in token[1:]:
        code = _SOUNDEX.get(char, "")
        # H and W are transparent: they do not code, and they do not break a
        # run either, so "Ashcraft" keeps its doubled consonant collapsed.
        if char in "HW":
            continue
        if code and code != previous:
            out += code
        previous = code if char not in "AEIOUY" else ""
        if len(out) == 4:
            break
    return (out + "000")[:4]


def phonetic_key(name_key: str) -> str:
    """Order-insensitive phonetic key, mirroring `normalize.watchlist_key`.

    Sorted, so a surname-first document and a given-name-first list entry land
    in the same bucket - the same reason the exact key is sorted.
    """
    return " ".join(sorted(soundex(t) for t in name_key.split() if t))


#: Built once per process, and rebuilt only if the list grew underneath us.
#: Measured on the loaded list: 72 ms to build 7,751 buckets, after which a
#: lookup is p50 0.06 ms / p95 0.11 ms because the largest bucket holds four
#: names. Pushing 8,256 comparisons through SQLite per screening would not.
#: Cached on the store, not in a module global. A global keyed on row count
#: would hand one store's index to a different store that happened to hold the
#: same number of rows - which is not a hypothetical, it is what two
#: `Store(":memory:")` fixtures in one test run look like.
def _index(store) -> dict[str, list[dict]]:
    size = store.watchlist_size()
    cached = getattr(store, "_phonetic_index", None)
    if cached is None or cached[0] != size:
        buckets: dict[str, list[dict]] = {}
        for row in store.watchlist_names():
            buckets.setdefault(phonetic_key(row["name_key"] or ""), []).append(row)
        cached = (size, buckets)
        store._phonetic_index = cached
    return cached[1]


def _nearest(store, name: str) -> tuple[dict, float] | None:
    """The closest listed name that sounds like this one, or nothing.

    Returns the single best candidate rather than every one above the floor.
    An officer reading four near-misses learns less than one, and the second
    best is by definition a worse guess than the first.
    """
    key = N.watchlist_key(name)
    if not key:
        return None

    best, best_ratio = None, 0.0
    for row in _index(store).get(phonetic_key(key), ()):
        listed = row["name_key"] or ""
        if listed == key:
            continue          # an exact match was already handled and reported
        ratio = difflib.SequenceMatcher(None, key, listed).ratio()
        if ratio > best_ratio:
            best, best_ratio = row, ratio
    return (best, best_ratio) if best and best_ratio >= NEAR_RATIO else None
