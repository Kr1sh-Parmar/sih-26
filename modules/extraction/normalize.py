"""Field normalisation. Pure functions.

Everything downstream compares field values, so they have to arrive in one
shape. A VIZ/MRZ comparison that fails because one side said "04/08/1991" and
the other "1991-08-04" is a false accusation, and the officer has no way to see
that the system is the one that is wrong.
"""
import re
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISO3166_CSV = ROOT / "data" / "raw" / "reference" / "iso3166" / "country-codes.csv"

#: MRZ nationality codes that are not ISO 3166-1 alpha-3. Doc 9303 defines
#: these, ISO does not, and a Layer B check driven only by the ISO list would
#: flag a genuine German passport (TECHNICAL-SPEC.md section 6).
ICAO_EXTRA = {
    "D": "Germany",
    "GBD": "United Kingdom (British Overseas Territories citizen)",
    "GBN": "United Kingdom (British National Overseas)",
    "GBO": "United Kingdom (British Overseas citizen)",
    "GBP": "United Kingdom (British Protected Person)",
    "GBS": "United Kingdom (British Subject)",
    "UNO": "United Nations Organization",
    "UNA": "United Nations Agency",
    "UNK": "UNMIK travel document holder",
    "XXA": "Stateless person",
    "XXB": "Refugee (1951 Convention)",
    "XXC": "Refugee (other)",
    "XXX": "Person of unspecified nationality",
    "XOM": "Sovereign Military Order of Malta",
    "XCC": "Caribbean Community",
    "RKS": "Kosovo",
}

_DATE_PATTERNS = (
    ("%Y-%m-%d", re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    ("%d/%m/%Y", re.compile(r"^\d{2}/\d{2}/\d{4}$")),
    ("%d-%m-%Y", re.compile(r"^\d{2}-\d{2}-\d{4}$")),
    ("%d.%m.%Y", re.compile(r"^\d{2}\.\d{2}\.\d{4}$")),
    ("%Y/%m/%d", re.compile(r"^\d{4}/\d{2}/\d{2}$")),
    ("%d %b %Y", re.compile(r"^\d{2} [A-Za-z]{3} \d{4}$")),
)


@lru_cache(maxsize=1)
def country_codes() -> dict[str, str]:
    """alpha-3 to country name, ISO 3166-1 plus the ICAO supplementary codes."""
    codes = dict(ICAO_EXTRA)
    if not ISO3166_CSV.exists():
        return codes
    import csv
    with ISO3166_CSV.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            alpha3 = (row.get("ISO3166-1-Alpha-3") or "").strip().upper()
            name = (row.get("official_name_en") or row.get("CLDR display name")
                    or row.get("UNTERM English Short") or "").strip()
            if len(alpha3) == 3:
                codes.setdefault(alpha3, name or alpha3)
    return codes


def is_country_code(code: str) -> bool:
    return str(code).strip().upper() in country_codes()


def name(value: str) -> str:
    """Uppercase, transliterated, single-spaced.

    Diacritics are stripped because the MRZ cannot carry them: a passport
    printed for "MÜLLER" has "MUELLER" or "MULLER" in the machine-readable
    zone, and comparing the two forms directly manufactures a mismatch.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("<", " ").upper()
    text = re.sub(r"[^A-Z0-9 ]+", " ", text)
    return " ".join(text.split())


def iso_date(value: str, *, past: bool = False, today: date | None = None) -> str | None:
    """Any printed date form to ISO-8601, or None if it is not a date.

    None rather than a guess: a field the system could not read must become
    `inconclusive`, not a plausible-looking value nobody can check.
    """
    if not value:
        return None
    from datetime import datetime
    text = " ".join(str(value).split())
    for fmt, pattern in _DATE_PATTERNS:
        if pattern.match(text):
            try:
                parsed = datetime.strptime(text, fmt).date()
            except ValueError:
                return None
            if past and parsed > (today or date.today()):
                return None
            return parsed.isoformat()
    return None


def gender(value: str) -> str | None:
    """To the MRZ codes M, F or < (unspecified)."""
    if not value:
        return None
    text = str(value).strip().upper()
    if text in ("M", "MALE", "PURUSH"):
        return "M"
    if text in ("F", "FEMALE", "MAHILA"):
        return "F"
    if text in ("<", "X", "O", "OTHER", "TRANSGENDER", "T"):
        return "<"
    return None


def id_number(value: str) -> str:
    """Strip printed grouping. Aadhaar prints in groups of four; the checksum
    is over the twelve digits."""
    return re.sub(r"[\s\-]", "", str(value or "")).upper()


def watchlist_key(value: str) -> str:
    """Order-insensitive name key for the watchlist index.

    Indian names are printed surname-first on some documents and given-name
    first on others, so a positional comparison misses hits that are staring
    the officer in the face.
    """
    return " ".join(sorted(name(value).split()))
