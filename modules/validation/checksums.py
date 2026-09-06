"""Layer A arithmetic anchors, one per document type. Pure functions.

Each returns (ok, detail) where `detail` is a fragment of officer-readable
English. Nothing here needs a key, a network call or a model - which is why
these run in microseconds and why they carry full reliability weight.

An honest note on what is and is not a checksum
-----------------------------------------------
Only Aadhaar has a real, publicly documented check digit (Verhoeff). The PAN,
EPIC and driving licence "checks" below are *structural* - they verify the
composition rules the issuing authority publishes, not a checksum, because no
check-character algorithm for those documents is published. `^[A-Z]{5}[0-9]{4}[A-Z]$`
passes for AAAAA0000A, and we say so rather than implying more certainty than
we have. The compensating strength for PAN is its fifth character, which really
does have to equal the first letter of the surname - a genuine cross-field
constraint that a spliced name breaks.
"""
import re
from datetime import date

# ------------------------------------------------------------------ Verhoeff
# The one real check digit among the six. UIDAI documents the 12th Aadhaar
# digit as a Verhoeff checksum, so this is arithmetic certainty, not a heuristic.

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff(number: str) -> bool:
    """True when the trailing digit is a valid Verhoeff check digit."""
    digits = "".join(c for c in number if c.isdigit())
    if not digits:
        return False
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _D[c][_P[i % 8][int(ch)]]
    return c == 0


def verhoeff_digit(payload: str) -> str:
    """Check digit for an 11-digit payload. Used by the synthetic generator."""
    c = 0
    for i, ch in enumerate(reversed(payload)):
        c = _D[c][_P[(i + 1) % 8][int(ch)]]
    return str(_INV[c])


def check_aadhaar(number: str) -> tuple[bool, str]:
    digits = "".join(c for c in str(number) if c.isdigit())
    if len(digits) != 12:
        return False, f"Aadhaar number has {len(digits)} digits, not 12"
    if digits[0] in "01":
        return False, "Aadhaar numbers do not begin with 0 or 1"
    if not verhoeff(digits):
        return False, "The Aadhaar check digit does not match the other eleven"
    return True, f"Aadhaar check digit {digits[-1]} is correct"


# ---------------------------------------------------------------------- PAN
# Fourth character is the holder type; fifth is the first letter of the surname
# (or of the entity name for non-individuals). Both are published rules.

PAN_HOLDER_TYPES = {
    "P": "individual", "C": "company", "H": "Hindu undivided family",
    "A": "association of persons", "B": "body of individuals",
    "G": "government agency", "J": "artificial juridical person",
    "L": "local authority", "F": "firm", "T": "trust",
}
_PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def check_pan(number: str, surname: str | None = None) -> tuple[bool, str]:
    """Structural validation. There is no published PAN check character."""
    pan = str(number).upper().replace(" ", "")
    if not _PAN_RE.match(pan):
        return False, f"PAN {pan} does not follow the five-letter, four-digit, one-letter format"
    if pan[3] not in PAN_HOLDER_TYPES:
        return False, f"PAN holder-type character {pan[3]} is not a recognised category"
    if surname:
        initial = surname.strip().upper()[:1]
        if initial and pan[4] != initial:
            return False, (
                f"PAN fifth character {pan[4]} does not match the first letter "
                f"of the surname {surname.strip().upper()}"
            )
    detail = f"PAN format valid, holder type {PAN_HOLDER_TYPES[pan[3]]}"
    if surname:
        detail += f", fifth character matches the surname {surname.strip().upper()}"
    return True, detail


# ----------------------------------------------------------------- Voter ID
# EPIC: three letters of functional constituency code, then seven digits.

_EPIC_RE = re.compile(r"^[A-Z]{3}[0-9]{7}$")


def check_epic(number: str) -> tuple[bool, str]:
    epic = str(number).upper().replace(" ", "")
    if not _EPIC_RE.match(epic):
        return False, f"Voter ID {epic} does not follow the three-letter, seven-digit EPIC format"
    return True, f"Voter ID follows the EPIC format, constituency code {epic[:3]}"


# ---------------------------------------------------------- Driving licence
# Two-letter state code, two-digit RTO office, four-digit year, seven-digit
# serial. The state codes are published under the Central Motor Vehicles Rules.

STATE_CODES = {
    "AN": "Andaman and Nicobar Islands", "AP": "Andhra Pradesh",
    "AR": "Arunachal Pradesh", "AS": "Assam", "BR": "Bihar",
    "CG": "Chhattisgarh", "CH": "Chandigarh", "DD": "Daman and Diu",
    "DL": "Delhi", "DN": "Dadra and Nagar Haveli", "GA": "Goa",
    "GJ": "Gujarat", "HP": "Himachal Pradesh", "HR": "Haryana",
    "JH": "Jharkhand", "JK": "Jammu and Kashmir", "KA": "Karnataka",
    "KL": "Kerala", "LA": "Ladakh", "LD": "Lakshadweep",
    "MH": "Maharashtra", "ML": "Meghalaya", "MN": "Manipur",
    "MP": "Madhya Pradesh", "MZ": "Mizoram", "NL": "Nagaland",
    "OD": "Odisha", "OR": "Odisha", "PB": "Punjab", "PY": "Puducherry",
    "RJ": "Rajasthan", "SK": "Sikkim", "TN": "Tamil Nadu",
    "TR": "Tripura", "TS": "Telangana", "UA": "Uttarakhand",
    "UK": "Uttarakhand", "UP": "Uttar Pradesh", "WB": "West Bengal",
}
_DL_RE = re.compile(r"^([A-Z]{2})([0-9]{2})([0-9]{4})([0-9]{7})$")


def check_dl(number: str, today: date | None = None) -> tuple[bool, str]:
    dl = re.sub(r"[\s-]", "", str(number).upper())
    m = _DL_RE.match(dl)
    if not m:
        return False, f"Licence number {dl} does not follow the state, RTO, year, serial format"
    state, rto, year, _ = m.groups()
    if state not in STATE_CODES:
        return False, f"Licence state code {state} is not a recognised Indian state or union territory"
    if int(rto) == 0:
        return False, f"Licence RTO office code {rto} is not valid"
    today = today or date.today()
    if not 1900 <= int(year) <= today.year:
        return False, f"Licence issue year {year} is not a plausible year"
    return True, f"Licence issued by {STATE_CODES[state]}, RTO office {rto}, {year}"


#: Which arithmetic anchor each document type actually has. A document type
#: absent from this map has none, and Layer A must say NO_CRYPTO_ANCHOR rather
#: than quietly pass it.
ANCHORS = {
    "aadhaar": "verhoeff_aadhaar",
    "pan": "pan_format",
    "voter_id": "epic_format",
    "dl": "dl_state_rto",
    "passport": "mrz_checkdigits",
    "visa": "mrz_checkdigits",
}
