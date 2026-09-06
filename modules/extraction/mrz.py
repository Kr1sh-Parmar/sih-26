"""ICAO Doc 9303 machine-readable zone parser.

This is our one genuine external standard. It needs nobody's permission, it is
present on every passport in the world, and it is the anchor that lets us say
something true about a document without a government key (D1).

Pure functions: a string goes in, fields come out. This module parses and
computes; it does not judge. Deciding that a check digit is wrong is Layer A's
job (modules/validation/layer_a.py) - see MODULES.md, "Module 1 outputs fields;
Module 2 judges them".
"""
from dataclasses import dataclass, field
from datetime import date

#: OCR-B alphanumerics plus the filler. Restricting the recogniser to this set
#: is a large, free accuracy gain on the MRZ strip (MODULES.md).
CHARSET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"

_WEIGHTS = (7, 3, 1)


class MRZError(ValueError):
    """The strip is not a machine-readable zone we can parse."""


def char_value(c: str) -> int:
    """Filler is 0, digits are themselves, A..Z are 10..35."""
    if c == "<":
        return 0
    if c.isdigit():
        return int(c)
    if "A" <= c <= "Z":
        return ord(c) - ord("A") + 10
    raise MRZError(f"character {c!r} is not in the OCR-B machine-readable charset")


def check_digit(value: str) -> str:
    """ICAO 9303 Part 3 section 4.9. Weights 7, 3, 1 repeating; sum modulo 10."""
    total = sum(char_value(c) * _WEIGHTS[i % 3] for i, c in enumerate(value))
    return str(total % 10)


def verify(value: str, digit: str) -> bool:
    """A filler in the check-digit position means the field is not used."""
    if digit == "<":
        return value.strip("<") == ""
    if not digit.isdigit():
        return False
    return check_digit(value) == digit


def parse_date(yymmdd: str, *, past: bool, today: date | None = None) -> str | None:
    """Six MRZ digits to an ISO-8601 date.

    The MRZ carries two-digit years, so the century has to be inferred. A date
    of birth cannot be in the future; an expiry generally is not decades past.
    Returns None rather than guessing when the digits are not a real date.
    """
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return None
    today = today or date.today()
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    century = today.year - today.year % 100
    try:
        value = date(century + yy, mm, dd)
    except ValueError:
        return None
    if past and value > today:
        value = value.replace(year=value.year - 100)
    elif not past and value.year < today.year - 50:
        value = value.replace(year=value.year + 100)
    return value.isoformat()


def parse_name(field_39: str) -> tuple[str, str]:
    """`SURNAME<<GIVEN<NAMES` to (surname, given names), both spaced."""
    primary, _, secondary = field_39.partition("<<")
    clean = lambda s: " ".join(p for p in s.split("<") if p)
    return clean(primary), clean(secondary)


@dataclass
class MRZ:
    """Parsed MRZ. `check_digits` maps field name to (value, digit_read)."""
    format: str                       # TD3 | MRVA | MRVB
    doc_code: str
    issuing_state: str
    surname: str
    given_names: str
    document_number: str
    nationality: str
    birth_date: str | None
    sex: str
    expiry_date: str | None
    optional_data: str
    lines: tuple = ()
    check_digits: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return " ".join(p for p in (self.given_names, self.surname) if p)


def _clean(line: str) -> str:
    return "".join(line.split()).upper()


def parse(strip: str, today: date | None = None) -> MRZ:
    """Parse a whole MRZ strip. Raises MRZError if it is not one we support."""
    lines = [_clean(l) for l in strip.strip().splitlines() if _clean(l)]
    if len(lines) != 2:
        raise MRZError(f"expected 2 MRZ lines, got {len(lines)}")

    bad = {c for line in lines for c in line} - set(CHARSET)
    if bad:
        raise MRZError(f"characters outside the OCR-B charset: {sorted(bad)}")

    if all(len(l) == 44 for l in lines):
        return _parse_44(lines, today)
    if all(len(l) == 36 for l in lines):
        return _parse_mrvb(lines, today)
    raise MRZError(f"unsupported MRZ line lengths {[len(l) for l in lines]}")


def _parse_44(lines: list[str], today: date | None) -> MRZ:
    """TD3 passport and MRV-A visa share a 2x44 layout up to the optional data.

    They diverge after position 27 of line 2: TD3 has 14 characters of personal
    number, its own check digit and a composite; MRV-A has 16 characters of
    optional data and neither. The document code tells them apart - V is a visa.
    """
    l1, l2 = lines
    visa = l1[0] == "V"
    fmt = "MRVA" if visa else "TD3"
    surname, given = parse_name(l1[5:44])

    m = MRZ(
        format=fmt,
        doc_code=l1[0:2].rstrip("<"),
        issuing_state=l1[2:5].rstrip("<"),
        surname=surname,
        given_names=given,
        document_number=l2[0:9].rstrip("<"),
        nationality=l2[10:13].rstrip("<"),
        birth_date=parse_date(l2[13:19], past=True, today=today),
        sex=l2[20],
        expiry_date=parse_date(l2[21:27], past=False, today=today),
        optional_data=(l2[28:44] if visa else l2[28:42]).rstrip("<"),
        lines=tuple(lines),
    )
    m.check_digits = {
        "document_number": (l2[0:9], l2[9]),
        "dob": (l2[13:19], l2[19]),
        "expiry": (l2[21:27], l2[27]),
    }
    if not visa:
        m.check_digits["optional"] = (l2[28:42], l2[42])
        # The composite runs over the document number, date of birth and expiry
        # fields *including* their own check digits, plus the optional data.
        m.check_digits["composite"] = (l2[0:10] + l2[13:20] + l2[21:43], l2[43])
    return m


def _parse_mrvb(lines: list[str], today: date | None) -> MRZ:
    """MRV-B visa, 2x36. No optional-data or composite check digit exists."""
    l1, l2 = lines
    surname, given = parse_name(l1[5:36])
    m = MRZ(
        format="MRVB",
        doc_code=l1[0:2].rstrip("<"),
        issuing_state=l1[2:5].rstrip("<"),
        surname=surname,
        given_names=given,
        document_number=l2[0:9].rstrip("<"),
        nationality=l2[10:13].rstrip("<"),
        birth_date=parse_date(l2[13:19], past=True, today=today),
        sex=l2[20],
        expiry_date=parse_date(l2[21:27], past=False, today=today),
        optional_data=l2[28:36].rstrip("<"),
        lines=tuple(lines),
    )
    m.check_digits = {
        "document_number": (l2[0:9], l2[9]),
        "dob": (l2[13:19], l2[19]),
        "expiry": (l2[21:27], l2[27]),
    }
    return m


def build_td3(doc_code="P", issuing_state="IND", surname="", given_names="",
              document_number="", nationality="IND", birth_date="", sex="M",
              expiry_date="", optional_data="") -> str:
    """Emit a valid TD3 strip. Used by the reference issuer and by tests.

    Dates are ISO-8601 in, YYMMDD out. Every check digit is computed, so a
    document produced here is internally consistent by construction - which is
    what makes a deliberately desynchronised forgery a meaningful test.
    """
    def pad(s, n):
        return (s.upper().replace(" ", "<")[:n]).ljust(n, "<")

    def yymmdd(iso):
        return iso.replace("-", "")[2:] if iso else "<" * 6

    name = f"{surname.upper().replace(' ', '<')}<<{given_names.upper().replace(' ', '<')}"
    l1 = pad(doc_code, 2) + pad(issuing_state, 3) + pad(name, 39)

    num = pad(document_number, 9)
    dob = yymmdd(birth_date)
    exp = yymmdd(expiry_date)
    opt = pad(optional_data, 14)
    body = (num + check_digit(num) + pad(nationality, 3)
            + dob + check_digit(dob) + (sex or "<")[0]
            + exp + check_digit(exp) + opt + check_digit(opt))
    return f"{l1}\n{body + check_digit(body[0:10] + body[13:20] + body[21:43])}"
