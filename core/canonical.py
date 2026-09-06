"""Canonical serialisation of a document payload.

Shared infrastructure, and deliberately so. Both sides of a signature need the
same definition of "these bytes", but the dependency runs one way only: the
reference issuer imports this, and the screening path imports this. Neither
imports the other, which is what keeps `issuer/` out of the inspection path
(CLAUDE.md rule 7, D2). There is no signing capability in this module - only
the byte form and the hash.

Determinism is the whole game. Identical logical data must produce identical
bytes, or signatures fail at random and nobody can reproduce it. So:

  * fields in a fixed order, defined here and nowhere else
  * UTF-8 NFC, no BOM
  * dates always ISO-8601, never locale formatting
  * a null field is present and empty, never absent - otherwise a document
    with no father's name canonicalises differently depending on whether the
    producer omitted the key or set it to None
  * no whitespace, no floats, no dict iteration order
"""
import hashlib
import unicodedata

#: Frozen field order. Appending is safe; reordering or removing invalidates
#: every signature ever issued, so treat this like a contract.
FIELD_ORDER = (
    "doc_type",
    "id_number",
    "name",
    "father_name",
    "dob",
    "gender",
    "nationality",
    "address",
    "issue_date",
    "expiry_date",
    "issuing_authority",
    "secondary_id",
)

SEPARATOR = "\x1f"      # unit separator: cannot occur in a normalised field
VERSION = "sih-ref-1"


def normalise(value) -> str:
    """One value to its canonical string form."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value)).strip()
    # Collapse internal whitespace so "ANNA  MARIA" and "ANNA MARIA" cannot
    # produce two different signatures for the same person.
    return " ".join(text.split())


def canonicalise(payload: dict) -> bytes:
    """Payload to the exact bytes that get hashed and signed."""
    unknown = set(payload) - set(FIELD_ORDER) - {"issuer_id"}
    if unknown:
        raise ValueError(
            f"cannot canonicalise unknown fields {sorted(unknown)}; add them to "
            f"FIELD_ORDER (append only) before signing"
        )
    parts = [VERSION, normalise(payload.get("issuer_id"))]
    parts += [normalise(payload.get(f)) for f in FIELD_ORDER]
    return SEPARATOR.join(parts).encode("utf-8")


def digest(payload: dict) -> bytes:
    """SHA-256 over the canonical bytes. This is what gets signed."""
    return hashlib.sha256(canonicalise(payload)).digest()


def doc_hash(payload: dict) -> str:
    """Hex digest, stored on the screening event so a case can be re-scored."""
    return hashlib.sha256(canonicalise(payload)).hexdigest()


def signed_fields(payload: dict) -> set[str]:
    """Anchors the signature actually proves, for fusion's precedence rule.

    Only fields carrying a value are proven. An empty field is signed as empty,
    which says nothing about what is printed on the card.
    """
    return {f"field:{f}" for f in FIELD_ORDER if normalise(payload.get(f))}
