"""Profile and config loading, and the weight/hard-fail lookup rules.

Schema is context/CONTRACTS.md section 4. Wildcards match by prefix, and the
most specific pattern wins: an exact id beats `validation.mrz.checkdigit.*`
beats `validation.*`. Weights need not sum to 1 - they are renormalised at
scoring time over the signals that actually ran.
"""
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROFILE_DIR = ROOT / "profiles"
CONFIG_DIR = ROOT / "config"

#: TECHNICAL-SPEC.md section 5. One detector, six document types. Do not add a
#: class without discussion - it means retraining and re-annotating.
ONTOLOGY = (
    "person_photo", "ghost_photo", "signature", "qr_code", "barcode", "mrz",
    "name", "father_name", "dob", "gender", "address", "nationality",
    "id_number", "secondary_id", "issue_date", "expiry_date",
    "issuing_authority", "emblem", "logo", "hologram", "blood_group",
    "doc_title",
)

DOC_TYPES = ("passport", "visa", "aadhaar", "pan", "voter_id", "dl")

_REQUIRED_TOP = ("doc_type", "extract", "verify", "tamper", "face", "hard_fail",
                 "weights", "disclosure")


class ProfileError(ValueError):
    """A profile that would silently misbehave. Fail at startup, not mid-screening."""


@lru_cache(maxsize=None)
def load_config(name: str) -> dict:
    path = CONFIG_DIR / f"{name}.yaml"
    if not path.exists():
        raise ProfileError(f"missing config {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_profile(doc_type: str) -> dict:
    path = PROFILE_DIR / f"{doc_type}.yaml"
    if not path.exists():
        raise ProfileError(
            f"no profile for document type {doc_type!r}; "
            f"known types are {', '.join(DOC_TYPES)}"
        )
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    validate(profile, source=str(path))
    return profile


def validate(profile: dict, source: str = "<profile>") -> None:
    missing = [k for k in _REQUIRED_TOP if k not in profile]
    if missing:
        raise ProfileError(f"{source}: missing keys {missing}")

    extract = profile["extract"]
    for key in ("detector_classes", "forbidden_classes"):
        unknown = set(extract.get(key, [])) - set(ONTOLOGY)
        if unknown:
            raise ProfileError(
                f"{source}: {key} contains classes outside the 22-class "
                f"ontology: {sorted(unknown)}"
            )

    overlap = set(extract["detector_classes"]) & set(extract["forbidden_classes"])
    if overlap:
        raise ProfileError(
            f"{source}: {sorted(overlap)} are both expected and forbidden"
        )

    if profile["verify"]["signature"] not in ("reference_issuer", "none"):
        raise ProfileError(f"{source}: verify.signature must be reference_issuer or none")

    # A reference-issuer verification must never look like a government one.
    if profile["verify"]["signature"] == "reference_issuer" and not profile["disclosure"]:
        raise ProfileError(
            f"{source}: declares a reference-issuer signature but no disclosure "
            f"string. See CONTEXT.md section 5 - the console must label it."
        )

    if profile["tamper"]["track"] not in ("full", "partial"):
        raise ProfileError(f"{source}: tamper.track must be full or partial")

    for w in profile["weights"].values():
        if not 0.0 <= float(w) <= 1.0:
            raise ProfileError(f"{source}: weights must be within 0..1, got {w}")


def matches(pattern: str, signal_id: str) -> bool:
    """Prefix wildcard. `tamper.*` matches `tamper.digital.ela`."""
    if pattern.endswith(".*"):
        return signal_id.startswith(pattern[:-1])
    if pattern == "*":
        return True
    return pattern == signal_id


def _most_specific(patterns, signal_id: str) -> str | None:
    """Longest matching pattern wins, so an exact id beats any wildcard."""
    hits = [p for p in patterns if matches(p, signal_id)]
    return max(hits, key=len) if hits else None


def weight_for(profile: dict, signal_id: str) -> float:
    """Profile weight for a signal id, 0.0 if the profile does not mention it.

    Zero is meaningful: a signal with no weight still renders as evidence and
    can still hard-fail, it just does not move the score.
    """
    hit = _most_specific(profile["weights"], signal_id)
    return float(profile["weights"][hit]) if hit else 0.0


def is_hard_fail(profile: dict, signal_id: str) -> bool:
    return _most_specific(profile["hard_fail"], signal_id) is not None


@lru_cache(maxsize=None)
def _reliability_table() -> dict:
    return load_config("reliability")


def reliability(signal_id: str) -> float:
    """How much this technique is actually worth. context/CONTRACTS.md section 3."""
    table = _reliability_table()
    hit = _most_specific([k for k in table if k != "_default"], signal_id)
    return float(table[hit]) if hit else float(table.get("_default", 0.5))


#: Officer-facing names. `doc_type` is an identifier; this is English.
DOC_LABEL = {
    "passport": "passport",
    "visa": "visa",
    "aadhaar": "Aadhaar card",
    "pan": "PAN card",
    "voter_id": "Voter ID",
    "dl": "driving licence",
}


def label(doc_type: str) -> str:
    return DOC_LABEL.get(doc_type, doc_type.replace("_", " "))


def describe(doc_type: str) -> str:
    """"an Aadhaar card", "a PAN card". Evidence strings are read by a person."""
    text = label(doc_type)
    return f"{'an' if text[0].upper() in 'AEIOU' else 'a'} {text}"


def describe_start(doc_type: str) -> str:
    """`describe` at the start of a sentence. Not str.capitalize(), which
    lowercases the rest and turns "an Aadhaar card" into "An aadhaar card"."""
    text = describe(doc_type)
    return text[:1].upper() + text[1:]


#: Officer-facing field names. `dob` is a column name; "date of birth" is what
#: goes in front of a border officer who may detain someone on the strength of
#: the sentence it appears in.
FIELD_LABEL = {
    "dob": "date of birth",
    "id_number": "identity number",
    "secondary_id": "secondary identity number",
    "father_name": "father's name",
    "issue_date": "issue date",
    "expiry_date": "expiry date",
    "issuing_authority": "issuing authority",
    "mrz": "machine-readable zone",
    "person_photo": "photograph",
    "ghost_photo": "ghost portrait",
    "doc_title": "document title",
    "blood_group": "blood group",
    "qr_code": "QR code",
}


def field_label(field: str) -> str:
    return FIELD_LABEL.get(field, field.replace("_", " "))
