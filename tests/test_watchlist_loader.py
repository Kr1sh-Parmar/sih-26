"""The watchlist loader's parsing decisions.

The loading itself is setup tooling, but two of its judgement calls change what
an officer sees and are worth pinning down.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "data" / "tools"))

from load_watchlist import (                              # noqa: E402
    WATCHLIST, _ofac_documents, _ofac_dob, clean, load_ofac, load_un, seed_demo,
)

from core.store import Store                              # noqa: E402
from modules.extraction import normalize as N             # noqa: E402


def test_full_dates_of_birth_are_parsed():
    assert _ofac_dob("DOB 12 Mar 1965; POB Havana, Cuba") == "1965-03-12"
    assert _ofac_dob("nationality Cuba; DOB 01 Jan 1980") == "1980-01-01"


def test_a_year_only_date_of_birth_stays_null():
    # Inventing 1 January would either make a namesake look like a match or
    # hide a real one. Layer E treats a missing date as "cannot rule out".
    assert _ofac_dob("DOB 1965; POB Havana") is None
    assert _ofac_dob("DOB circa 1965") is None
    assert _ofac_dob("no date at all") is None


def test_document_numbers_are_pulled_out_of_the_remarks():
    remarks = "Passport A1234567 (Cuba); National ID No. 65031204321 (Cuba)"
    assert "A1234567" in _ofac_documents(remarks)
    assert "65031204321" in _ofac_documents(remarks)


def test_ofac_null_marker_is_treated_as_empty():
    assert clean("-0- ") == ""
    assert clean(None) == ""
    assert clean(" AEROCARIBBEAN ") == "AEROCARIBBEAN"


def test_demo_entries_are_findable_both_ways():
    store = Store(":memory:")
    assert seed_demo(store) == 2
    assert store.watchlist_by_name_key(N.watchlist_key("Devi Sunita"))
    assert store.watchlist_by_document("X9999999")


@pytest.mark.skipif(not (WATCHLIST / "sdn.csv").exists(),
                    reason="OFAC data not downloaded")
def test_the_real_lists_load_and_only_individuals_arrive():
    store = Store(":memory:")
    ofac = load_ofac(store)
    un = load_un(store)
    assert ofac > 5000
    assert un > 500

    # Vessels and companies do not present a document at a counter.
    rows = store._conn.execute(
        "SELECT name FROM watchlist WHERE name LIKE '%AIRLINES%' "
        "OR name LIKE '%LTD%' OR name LIKE '%CO.,%'").fetchall()
    assert not rows, f"non-individual entries loaded: {[r[0] for r in rows][:5]}"

    with_dob = store._conn.execute(
        "SELECT COUNT(*) FROM watchlist WHERE dob IS NOT NULL").fetchone()[0]
    assert with_dob > 1000, "too few dates of birth - the DOB parser regressed"
