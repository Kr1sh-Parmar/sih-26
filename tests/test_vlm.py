"""The Florence-2 fallback reader.

Most of what can go wrong here is not the model. It is the plumbing around it:
a region parser that silently returns nothing, a timeout that does not fire, a
field assignment that guesses, or a crash that takes the whole screening down
with it. Those are tested without loading 275 MB of graphs.

Exactly one test runs the model end to end, and it skips when the weights are
absent. Eight seconds is the ceiling for one document, so a suite that ran it
per assertion would cost minutes to say what a pure function already said.
"""
import time

import numpy as np
import pytest

from core.profiles import load_profile
from fusion.context import ScreeningContext
from modules.extraction import vlm

HAVE_MODEL = vlm.deployed()
needs_model = pytest.mark.skipif(
    not HAVE_MODEL, reason="Florence-2 is not deployed; run scripts/fetch_vlm_model.py")


def ctx_for(doc_type="passport", image=None, **kw):
    return ScreeningContext(
        session_id="t",
        image=image if image is not None else np.full((700, 1000, 3), 240, np.uint8),
        doc_type=doc_type, profile=load_profile(doc_type), **kw)


def by_id(signals):
    return {s.id: s for s in signals}


# ------------------------------------------------------------- region parsing

def test_regions_pair_each_string_with_its_own_quad():
    text = ("<s>PASSPORT<loc_100><loc_200><loc_300><loc_200><loc_300><loc_250>"
            "<loc_100><loc_250>M1234567<loc_500><loc_100><loc_700><loc_100>"
            "<loc_700><loc_150><loc_500><loc_150></s>")
    regions = vlm.parse_regions(text, 1000, 1000)
    assert [label for label, _box in regions] == ["PASSPORT", "M1234567"]
    assert regions[0][1] == (100.0, 200.0, 300.0, 250.0)


def test_region_coordinates_scale_to_the_image():
    """Florence-2 quantises into 1000 bins whatever the image size."""
    text = "X<loc_0><loc_0><loc_500><loc_500>"
    (_label, box), = vlm.parse_regions(text, 800, 400)
    assert box == (0.0, 0.0, 400.0, 200.0)


def test_text_with_no_location_tokens_is_dropped():
    """A string the model did not ground is a string it cannot be held to."""
    assert vlm.parse_regions("<s>just some text</s>", 100, 100) == []


def test_an_empty_read_parses_to_nothing_rather_than_raising():
    assert vlm.parse_regions("", 100, 100) == []


# --------------------------------------------------------------- assignment

def test_only_recognisable_shapes_are_assigned():
    """A line of capitals could be the name, the father's name or an address.

    Guessing puts a wrong value where Layer C and Layer D compare against it,
    which is the harm the ratifier exists to prevent, reached from the other
    side. Names are read and reported; they are not assigned.
    """
    reads = [("PRADEEP GHARAT", (0, 0, 10, 10)),
             ("SOME STREET, PUNE", (0, 20, 10, 30))]
    assert vlm.assign(reads, "aadhaar") == {}


def test_a_number_that_validates_is_assigned_and_one_that_does_not_is_not():
    from modules.validation.checksums import verhoeff_digit
    good = "23456789012" + verhoeff_digit("23456789012")
    bad = good[:-1] + str((int(good[-1]) + 1) % 10)

    assert vlm.assign([(good, (0, 0, 1, 1))], "aadhaar")["id_number"] == good
    assert "id_number" not in vlm.assign([(bad, (0, 0, 1, 1))], "aadhaar")


def test_dates_are_ordered_birth_issue_expiry():
    """No labels to tell three dates apart, so they are ordered. A shaky guess,
    and one Layer C reports as a date-order failure when it is wrong."""
    reads = [("2028-10-26", (0, 0, 1, 1)), ("1967-09-28", (0, 2, 1, 3)),
             ("2018-10-29", (0, 4, 1, 5))]
    assigned = vlm.assign(reads, "passport")
    assert assigned["dob"] == "1967-09-28"
    assert assigned["issue_date"] == "2018-10-29"
    assert assigned["expiry_date"] == "2028-10-26"


def test_an_mrz_line_is_recognised_by_its_charset_and_length():
    strip = "P<INDGHARAT<<PRADEEP<" + "<" * 23
    assert len(strip) == 44
    assert vlm.assign([(strip, (0, 0, 1, 1))], "passport")["mrz"] == strip
    assert not vlm._looks_like_mrz("PRADEEP GHARAT")


def test_located_fields_settle_the_assignment_without_guessing():
    """When a detector ran, overlap answers the question properly."""
    reads = [("PRADEEP GHARAT", (10, 10, 90, 30))]
    boxes = {"name": (12, 12, 88, 28)}
    assert vlm.assign(reads, "aadhaar", boxes) == {"name": "PRADEEP GHARAT"}


def test_a_read_overlapping_nothing_is_left_unassigned():
    reads = [("PRADEEP GHARAT", (500, 500, 560, 520))]
    assert vlm.assign(reads, "aadhaar", {"name": (10, 10, 40, 20)}) == {}


# ------------------------------------------------------------------- decoding

def test_decode_inverts_the_byte_level_mapping():
    """Encoding lives in the fetcher and runs once at build time; this is the
    half the screening path actually needs."""
    vocab = {5: "Hello", 6: "Ġworld"}       # the space marker GPT-2 uses
    assert vlm.decode([5, 6], vocab) == "Hello world"


def test_added_tokens_survive_decoding_so_the_regions_can_be_parsed():
    vocab = {5: "AB", 6: "<loc_42>"}
    assert vlm.decode([5, 6], vocab) == "AB<loc_42>"


# ------------------------------------------------------------------- the guard

def test_a_timeout_stops_the_read_and_asks_for_a_re_capture(monkeypatch):
    """"An unbounded fallback will hang the demo" - TECHNICAL-SPEC section 4."""
    def slow(*_args, **kwargs):
        deadline = kwargs["deadline"]
        while time.perf_counter() < deadline + 0.01:
            time.sleep(0.01)
        raise vlm.Timeout("too slow")

    monkeypatch.setattr(vlm, "generate", slow)
    monkeypatch.setattr(vlm, "deployed", lambda: True)
    monkeypatch.setattr(vlm, "config", lambda: {"timeout_seconds": 0.2})

    started = time.perf_counter()
    signal, = vlm.run(ctx_for())
    assert time.perf_counter() - started < 3, "the timeout did not actually stop it"
    assert signal.verdict == "inconclusive"
    assert "Re-capture" in signal.evidence


def test_a_crash_inside_the_model_does_not_crash_the_screening(monkeypatch):
    """A fallback that takes the whole screening down is worse than one that
    admits it could not read."""
    def explode(*_args, **_kwargs):
        raise RuntimeError("the graph is corrupt")

    monkeypatch.setattr(vlm, "generate", explode)
    monkeypatch.setattr(vlm, "deployed", lambda: True)
    signal, = vlm.run(ctx_for())
    assert signal.verdict == "inconclusive"
    assert "RuntimeError" in signal.evidence


def test_an_undeployed_model_names_the_obstacle(monkeypatch):
    monkeypatch.setattr(vlm, "deployed", lambda: False)
    signal, = vlm.run(ctx_for())
    assert signal.verdict == "inconclusive"
    assert "fetch_vlm_model" in signal.evidence


def test_the_fallback_is_lazy_and_never_warmed_at_startup():
    """Four graphs and 275 MB. Warming them would take the resident footprint
    from about 450 MB to 910 MB for the 85% of documents that never need it."""
    from core import registry
    assert registry.FLORENCE not in registry.warm()["loaded"]
    assert registry.FLORENCE not in registry.warm()["missing"]


# --------------------------------------------------------------- end to end

@needs_model
def test_the_model_reads_a_generated_passport_inside_its_budget():
    """The one test that loads the graphs. Measured numbers: data/EXTRACTION.md."""
    pytest.importorskip("PIL")
    from data.generator import build

    doc = build("passport", seed=14)
    started = time.perf_counter()
    text = vlm.generate(doc.image, deadline=started + 30)
    elapsed = time.perf_counter() - started

    regions = vlm.parse_regions(text, *doc.size)
    assert len(regions) >= 8, f"only {len(regions)} regions in {elapsed:.1f}s"

    # Dates, not names or numbers. The model transcribes digit strings reliably
    # and drops characters from alphanumerics - it read CHABRA for CHHABRA and
    # M37011978 for M3701978 on this very document. That is the measured
    # behaviour (data/EXTRACTION.md) and precisely why the ratifier discards
    # what it cannot confirm rather than trusting the read.
    assigned = vlm.assign(regions, "passport")
    assert assigned.get("dob") == doc.identity.dob, assigned


@needs_model
def test_every_id_the_fallback_emits_is_registered_and_unique():
    from core.profiles import reliability
    from modules.extraction import ratify

    ctx = ctx_for("aadhaar")
    signals = ratify.ratify(ctx, {"name": "A B"})
    ids = [s.id for s in signals]
    assert len(ids) == len(set(ids))
    for sid in ids:
        assert reliability(sid) > 0, sid


# ------------------------------------------- the fallback yields to the MRZ

def test_the_fallback_does_not_run_once_the_mrz_has_been_read():
    """The largest latency win in the module, and it is a yield, not a race.

    A verified MRZ already carries surname, given names, document number,
    nationality, date of birth, sex and expiry, each with its own ICAO check
    digit - every field Florence-2 could offer, at `arithmetic` trust instead
    of `unverified`, in about two seconds instead of seven.

    Measured over ten generated passports: 1,702 ms median when the zone reads
    against 9,634 ms when it does not and the fallback runs to its 8 s ceiling.
    """
    from data.generator import build as build_doc
    from fusion.context import NormalizedField
    from modules import extraction

    doc = build_doc("passport", seed=44)
    ctx = ctx_for("passport", image=doc.image)
    # `_mrz_from_its_fixed_position` only stores the strip once its own check
    # digits agree, so presence here means verified, not merely read.
    ctx.fields["mrz"] = NormalizedField(raw=doc.identity.mrz(), value="",
                                        source="mrz", confidence=0.9)

    signals = {s.id: s for s in extraction._fallback(ctx, [])}
    assert "extraction.vlm.unratified" not in signals
    ratified = signals["extraction.vlm.ratified"]
    assert ratified.verdict == "not_applicable", (
        "the fallback ran anyway, spending its budget re-reading fields the "
        "machine-readable zone already carries with check digits")
    assert "not needed" in ratified.evidence


def test_the_fallback_still_runs_when_the_mrz_did_not_read():
    """The skip must not have turned into a blanket disable: a document whose
    zone could not be read is exactly the one that needs the fallback."""
    from data.generator import build as build_doc
    from modules import extraction

    ctx = ctx_for("passport", image=build_doc("passport", seed=44).image)
    assert "mrz" not in ctx.fields
    ids = {s.id for s in extraction._fallback(ctx, [])}
    assert ids, "nothing was read and the fallback declined to run"


def test_the_ratified_signal_reports_the_whole_fallback_not_just_the_ratifying():
    """The measurement bug this pins.

    The ratifier is the only producer of `extraction.vlm.*`, so its signals are
    the only place the fallback's cost can be reported. It used to start its own
    clock, which timed the ratification - a few hundred microseconds - and threw
    away the seconds of Florence-2 that produced the reads.

    Measured on `var/demo/gen_pan.png`, which spends its whole screening in the
    fallback: extraction reported **4 ms** of a ~6,000 ms document. Every
    per-stage latency table built from signal latencies was wrong by three
    orders of magnitude on exactly the documents that blow the budget.

    CLAUDE.md asks for the latency budget to be a requirement rather than a
    hope. A budget policed by a number that omits the expensive part polices
    nothing.
    """
    from modules.extraction import ratify as ratifier

    ctx = ScreeningContext(session_id="t", image=np.zeros((80, 200, 3), np.uint8),
                           doc_type="pan", profile=load_profile("pan"))

    # Pretend the model spent 250 ms before handing reads to the ratifier.
    started = time.perf_counter() - 0.250
    signals = ratifier.ratify(ctx, {"dob": "02/11/1998"}, started=started)

    reported = max(s.latency_ms for s in signals)
    assert reported >= 250, (
        f"the fallback's cost was dropped: reported {reported} ms for work that "
        f"began 250 ms ago"
    )


def test_ratify_still_times_itself_when_no_clock_is_handed_in():
    """The default has to keep working - most callers do not pass one."""
    from modules.extraction import ratify as ratifier

    ctx = ScreeningContext(session_id="t", image=np.zeros((80, 200, 3), np.uint8),
                           doc_type="pan", profile=load_profile("pan"))
    signals = ratifier.ratify(ctx, {"dob": "02/11/1998"})
    assert all(s.latency_ms >= 0 for s in signals)
