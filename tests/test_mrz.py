"""MRZ parser against the ICAO Doc 9303 published specimen, plus deliberate
check-digit failures.

The specimen below is the worked example printed in ICAO Doc 9303. Every one of
its five check digits must verify. If the weighting, the character values or
the composite field ranges are wrong, at least one of them will not - which is
why this single string is worth more than a dozen hand-made cases.
"""
import pytest

from modules.extraction import mrz as M

# ICAO Doc 9303 Part 4, TD3 specimen (UTOPIA, ERIKSSON ANNA MARIA).
ICAO_TD3 = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
    "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
)


def test_icao_specimen_parses():
    m = M.parse(ICAO_TD3)
    assert m.format == "TD3"
    assert m.doc_code == "P"
    assert m.issuing_state == "UTO"
    assert m.surname == "ERIKSSON"
    assert m.given_names == "ANNA MARIA"
    assert m.document_number == "L898902C3"
    assert m.nationality == "UTO"
    assert m.birth_date == "1974-08-12"
    assert m.sex == "F"
    assert m.expiry_date == "2012-04-15"
    assert m.optional_data == "ZE184226B"


def test_all_five_icao_specimen_check_digits_verify():
    m = M.parse(ICAO_TD3)
    assert set(m.check_digits) == {
        "document_number", "dob", "expiry", "optional", "composite"
    }
    for name, (value, digit) in m.check_digits.items():
        assert M.verify(value, digit), f"{name} check digit failed"


@pytest.mark.parametrize("pos,field", [
    (9, "document_number"),
    (19, "dob"),
    (27, "expiry"),
    (42, "optional"),
    (43, "composite"),
])
def test_a_corrupted_check_digit_is_caught(pos, field):
    l1, l2 = ICAO_TD3.splitlines()
    wrong = str((int(l2[pos]) + 1) % 10)
    m = M.parse(f"{l1}\n{l2[:pos]}{wrong}{l2[pos + 1:]}")
    value, digit = m.check_digits[field]
    assert not M.verify(value, digit)


def test_altering_the_date_of_birth_breaks_two_digits_not_one():
    # This is the forgery the whole system is built around. Editing the MRZ
    # date without recomputing invalidates its own digit and the composite.
    l1, l2 = ICAO_TD3.splitlines()
    m = M.parse(f"{l1}\n{l2[:13]}740813{l2[19:]}")
    assert not M.verify(*m.check_digits["dob"])
    assert not M.verify(*m.check_digits["composite"])


def test_check_digit_worked_examples():
    # ICAO Doc 9303 Part 3, section 4.9 worked examples.
    assert M.check_digit("520727") == "3"
    assert M.check_digit("AB2134<<<") == "5"


def test_filler_check_digit_means_the_field_is_unused():
    assert M.verify("<<<<<<<<<<<<<<", "<")
    assert not M.verify("ZE184226B<<<<<", "<")


def test_charset_is_restricted_to_ocr_b():
    l1, l2 = ICAO_TD3.splitlines()
    with pytest.raises(M.MRZError):
        M.parse(f"{l1}\n{'-' + l2[1:]}")     # punctuation cannot appear in an MRZ


def test_case_and_whitespace_are_normalised_not_rejected():
    # The recogniser is charset-locked to OCR-B, so lowercase should never
    # arrive. If it does it is a rendering artifact, not evidence of forgery -
    # repairing it is right, and the check digits still have to hold.
    l1, l2 = ICAO_TD3.splitlines()
    m = M.parse(f"  {l1.lower()}  \n{l2.lower()}")
    assert m.document_number == "L898902C3"
    assert all(M.verify(v, d) for v, d in m.check_digits.values())


def test_the_dangerous_ocr_slips_are_invisible_to_the_charset_check():
    # 0/O, 1/I and 5/S are all inside the OCR-B charset, so the charset gate
    # cannot catch them. The check digits are what catch them, which is the
    # whole reason this module exists.
    l1, l2 = ICAO_TD3.splitlines()
    m = M.parse(f"{l1}\n{l2.replace('0', 'O', 1)}")
    assert not all(M.verify(v, d) for v, d in m.check_digits.values())


def test_wrong_line_count_is_an_error_not_a_guess():
    with pytest.raises(M.MRZError):
        M.parse(ICAO_TD3.splitlines()[0])


def test_impossible_date_returns_none_rather_than_a_guess():
    assert M.parse_date("740832", past=True) is None
    assert M.parse_date("74081", past=True) is None
    assert M.parse_date("AB0812", past=True) is None


def test_two_digit_year_windowing():
    from datetime import date
    today = date(2026, 9, 6)
    # A birth date cannot be in the future.
    assert M.parse_date("740812", past=True, today=today) == "1974-08-12"
    assert M.parse_date("991231", past=True, today=today) == "1999-12-31"
    # An expiry generally is not decades past.
    assert M.parse_date("310717", past=False, today=today) == "2031-07-17"


def test_visa_has_no_composite_or_optional_check_digit():
    # MRV-A carries neither. Asserting one would fabricate a failure.
    strip = M.build_td3(surname="GHARAT", given_names="PRADEEP",
                        document_number="V1234567", birth_date="1996-11-02",
                        expiry_date="2031-07-17")
    visa = "V<" + strip.splitlines()[0][2:] + "\n" + strip.splitlines()[1]
    m = M.parse(visa)
    assert m.format == "MRVA"
    assert set(m.check_digits) == {"document_number", "dob", "expiry"}


def test_builder_round_trips_through_the_parser():
    strip = M.build_td3(
        issuing_state="IND", surname="SABRI", given_names="MUHAMAD",
        document_number="E1009353", nationality="IND",
        birth_date="1991-08-04", sex="M", expiry_date="2031-07-17",
    )
    m = M.parse(strip)
    assert m.surname == "SABRI"
    assert m.given_names == "MUHAMAD"
    assert m.document_number == "E1009353"
    assert m.birth_date == "1991-08-04"
    assert m.expiry_date == "2031-07-17"
    for name, (value, digit) in m.check_digits.items():
        assert M.verify(value, digit), f"{name} did not verify on a built strip"


def test_archive_render_mrz_is_cosmetic_and_fails_by_construction():
    # data/raw/passport/_archive_raw ships synthetic renders whose MRZ uses
    # DDMMYYYY and carries no per-field check digits (see data/PROVENANCE.md).
    # A parser that accepted them would be accepting a forgery pattern.
    fake = ("P<UAEDOE<<JOHN<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<\n"
            "A123456780UAE0108199100M31072031<<<<<<<<<<<0")
    m = M.parse(fake)
    assert not all(M.verify(v, d) for v, d in m.check_digits.values())
