"""Guards on the things that are expensive to get wrong quietly.

The architectural rules in CLAUDE.md are only rules if something checks them.
These are cheap, and each one has a specific failure it prevents.
"""
import re
from pathlib import Path

import cv2
import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "context" / "CONTRACTS.md"

#: The console's TypeScript contracts. Two tests below read them to prove the
#: Python and TypeScript vocabularies have not drifted - which they can only do
#: where the console's source exists. The screening image ships the console's
#: runtime fixtures and nothing else of it (`.dockerignore`), so there the check
#: skips and says why rather than failing on a missing file.
TS_CONTRACTS = ROOT / "frontend" / "src" / "contracts"
needs_ts_contracts = pytest.mark.skipif(
    not (TS_CONTRACTS / "signal.ts").exists(),
    reason="frontend/src/contracts is not in this tree; the console has its "
           "own image and this check needs its TypeScript sources")
SCREENING_PACKAGES = ("api", "core", "modules", "fusion")


# ------------------------------------------------- the issuer boundary

def test_the_issuer_is_not_importable_from_the_screening_path():
    """CLAUDE.md rule 7, and the lint rule TECHNICAL-SPEC.md section 12 asks for.

    A real issuing authority is not reachable from a border checkpoint. If
    `issuer` ever appears in the inspection path, the demo claim that the two
    are separate stops being true.
    """
    offenders = []
    for package in SCREENING_PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if re.match(r"^(from\s+issuer|import\s+issuer)\b", stripped):
                    offenders.append(f"{path.relative_to(ROOT)}: {stripped}")
    assert not offenders, "issuer/ leaked into the screening path:\n" + "\n".join(offenders)


def test_the_issuer_does_not_import_the_api_either():
    # The dependency runs one way through core/canonical.py. If issuer/ starts
    # importing api/, the two are coupled again just in the other direction.
    offenders = []
    for path in (ROOT / "issuer").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*(from\s+api|import\s+api)\b", line):
                offenders.append(f"{path.relative_to(ROOT)}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


# --------------------------------------------- the signal id namespace

def registered_patterns() -> list[re.Pattern]:
    """Parse the Signal ID namespace block out of CONTRACTS.md section 1.

    `<field>` in the contract stands for one dotted segment, so
    `validation.mrz.checkdigit.<field>` registers `...checkdigit.composite`.
    """
    text = CONTRACTS.read_text(encoding="utf-8")
    block = text.split("### Signal ID namespace", 1)[1].split("```")[1]
    patterns = []
    for token in block.split():
        escaped = re.escape(token)
        # re.escape leaves < and > alone on 3.7+, but be explicit either way.
        escaped = escaped.replace(r"\<", "<").replace(r"\>", ">")
        patterns.append(re.compile("^" + re.sub(r"<[a-z_]+>", "[a-z0-9_]+", escaped) + "$"))
    return patterns


PATTERNS = registered_patterns()


def is_registered(signal_id: str) -> bool:
    return any(p.match(signal_id) for p in PATTERNS)


def test_the_namespace_block_actually_parsed():
    assert len(PATTERNS) > 30
    assert is_registered("validation.mrz.checkdigit.composite")
    assert is_registered("validation.mrz.checkdigit.dob")
    assert is_registered("extraction.field.name.confidence")
    assert is_registered("validation.format.pan.id_number")
    assert not is_registered("validation.totally.made.up")


def emitted_signal_ids() -> set[str]:
    """Every literal signal id the code can emit.

    A typo here is silent and expensive: the id gets the default reliability,
    matches no profile weight, and never fires as a hard fail.
    """
    found = set()
    literal = re.compile(r'"(?:extraction|validation|tamper|face)\.[a-z0-9_.{}]*"')
    for package in SCREENING_PACKAGES:
        for path in (ROOT / package).rglob("*.py"):
            for match in literal.finditer(path.read_text(encoding="utf-8")):
                token = match.group(0).strip('"')
                if "{" in token:
                    continue                      # f-string, resolved at runtime
                if token.count(".") < 2:
                    continue                      # a startswith() prefix, not an id
                found.add(token)
    return found


def test_every_emitted_signal_id_is_registered_in_contracts_md():
    unregistered = sorted(s for s in emitted_signal_ids() if not is_registered(s))
    assert not unregistered, (
        "these signal ids are emitted but not registered in CONTRACTS.md section 1:\n"
        + "\n".join(unregistered)
    )


def test_every_profile_weight_and_hard_fail_names_a_registered_id():
    from core.profiles import DOC_TYPES, load_profile
    bad = []
    for doc_type in DOC_TYPES:
        profile = load_profile(doc_type)
        for key in list(profile["weights"]) + list(profile["hard_fail"]):
            probe = key[:-2] + ".x" if key.endswith(".*") else key
            if not any(p.match(probe) or p.pattern.startswith("^" + re.escape(key[:-2]))
                       for p in PATTERNS):
                bad.append(f"{doc_type}: {key}")
    assert not bad, "profile keys that match no registered signal id:\n" + "\n".join(bad)


def test_every_reliability_key_is_registered():
    from core.profiles import load_config
    table = load_config("reliability")
    bad = [k for k in table if k != "_default" and not is_registered(k)]
    assert not bad, "reliability.yaml keys not in CONTRACTS.md:\n" + "\n".join(bad)


# ------------------------------------------ frontend / backend parity

@needs_ts_contracts
def test_the_python_and_typescript_contracts_agree_on_their_vocabularies():
    """Drift between the dataclass and contracts/signal.ts is, in that file's
    own words, the single most expensive bug available in this project."""
    ts = (ROOT / "frontend" / "src" / "contracts" / "signal.ts").read_text(encoding="utf-8")
    events = (ROOT / "frontend" / "src" / "contracts" / "events.ts").read_text(encoding="utf-8")

    from api.router import PHASES
    from fusion.signal import TRUST_ORDER

    for verdict in ("pass", "fail", "inconclusive", "not_applicable"):
        assert f'"{verdict}"' in ts
    for band in ("GREEN", "AMBER", "RED"):
        assert f'"{band}"' in ts
    for trust in TRUST_ORDER:
        assert f'"{trust}"' in ts
    for module in ("extraction", "validation", "tamper", "face"):
        assert f'"{module}"' in ts
    for phase in PHASES:
        assert f'"{phase}"' in events, f"phase {phase} is not in the console union"


@needs_ts_contracts
def test_the_signal_wire_shape_matches_the_typescript_interface():
    from fusion.signal import Signal, to_json
    ts = (ROOT / "frontend" / "src" / "contracts" / "signal.ts").read_text(encoding="utf-8")
    wire = to_json(Signal("a.b", "validation", 1, "pass", 1.0, "arithmetic",
                          False, "document", "x"))
    for key in wire:
        assert re.search(rf"^\s*{key}\??:", ts, re.M), f"{key} is not in signal.ts"


# ------------------------------------------------ the QR decode floor

def test_qr_decoding_is_reliable_on_freshly_signed_payloads():
    """Regression guard.

    OpenCV's built-in detector failed roughly one code in ten on a version-12
    QR, and it failed as "no cryptographic anchor" - the system confidently
    reporting a finding rather than a decoder that gave up. Every signature is
    different, so this has to be measured over several codes, not one.
    """
    from issuer.qr import encode_bytes
    from issuer.sign import Keypair, sign
    from modules.extraction.qr import decode

    payload = {"doc_type": "aadhaar", "id_number": "234567890124",
               "name": "PRADEEP KESHAV GHARAT", "dob": "1996-11-02", "gender": "M"}

    failures = 0
    for _ in range(15):
        envelope = sign(payload, Keypair.generate())
        png = encode_bytes(envelope, scale=6)
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        got, _region = decode(image)
        if got != envelope:
            failures += 1
    assert failures == 0, f"{failures}/15 signed QR codes failed to decode"


@pytest.mark.skipif(not __import__("modules.extraction.qr", fromlist=["HAVE_ZBAR"]).HAVE_ZBAR,
                    reason="libzbar is not installed")
def test_zbar_is_the_decoder_actually_in_use():
    # If this ever skips in CI, the fallback is running and the reliability
    # floor above is no longer guaranteed.
    from modules.extraction.qr import HAVE_ZBAR
    assert HAVE_ZBAR


# ------------------------------------------------- overclaiming guards

#: Files that are read by a judge, a panel, or an officer. A claim that is
#: wrong here is worse than a missing feature.
CLAIM_SURFACES = ("README.md", "context", "profiles", "config",
                  "frontend/src/fixtures", "frontend/scripts")


def claim_text() -> list[tuple[str, int, str]]:
    lines = []
    for surface in CLAIM_SURFACES:
        target = ROOT / surface
        paths = [target] if target.is_file() else [
            p for p in target.rglob("*")
            if p.suffix in (".md", ".json", ".yaml", ".py") and p.is_file()
        ]
        for path in paths:
            rel = path.relative_to(ROOT).as_posix()
            for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                lines.append((rel, n, line))
    return lines


#: The document has to be attached to the claim, not merely in the same
#: sentence, so the window stops at a comma: "Verhoeff-valid Aadhaar,
#: format-valid PAN, TD3 MRZ with correct check digits" is a correct sentence
#: and a window that spans commas flags it - which this guard did on its first
#: run. Table pipes stay inside the window, because the README row
#: "| PAN | Reference issuer | Format + check character |" is exactly the shape
#: of the claim being guarded against.
_PAN_CLAIM = re.compile(
    r"(?:PAN|EPIC|driving licence|driving license)[^,.;]{0,40}"
    r"check[ _]*(?:character|char\b|digit)"
    r"|check[ _]*(?:character|char\b|digit)[^,.;]{0,40}(?:PAN|EPIC)",
    re.I,
)

#: DECISIONS.md D23 is the one place allowed to name the thing, in order to say
#: that it does not exist.
_CLAIM_EXEMPT = ("context/DECISIONS.md",)


def test_nothing_claims_a_pan_check_character():
    """D23. There is no published PAN check-character algorithm.

    An earlier draft said "PAN check character F is correct for ABLPG7040" in
    the Scene 3 fixture and in six documents. It was wrong in the direction
    that overclaims certainty to a panel, which is the expensive direction.
    """
    offenders = [
        f"{path}:{n}: {line.strip()}"
        for path, n, line in claim_text()
        if not path.startswith(_CLAIM_EXEMPT) and _PAN_CLAIM.search(line)
    ]
    assert not offenders, (
        "these claim a check character that does not exist (see DECISIONS.md D23):\n"
        + "\n".join(offenders)
    )


def test_the_guard_would_catch_the_claim_it_was_written_for():
    # A guard nobody has watched fail is a guard nobody knows works. These are
    # the exact strings that were in the repo before D23.
    assert _PAN_CLAIM.search("PAN check character F is correct for ABLPG7040")
    assert _PAN_CLAIM.search("Layer A: Verhoeff, PAN check char, EPIC format")
    assert _PAN_CLAIM.search("| PAN | Reference issuer | Format + check character |")
    # ...and leaves the correct sentences alone.
    assert not _PAN_CLAIM.search(
        "Verhoeff-valid Aadhaar, format-valid PAN, TD3 MRZ with correct check digits")
    assert not _PAN_CLAIM.search("MRZ five check digits: document number, DOB")


def test_the_pan_fixture_evidence_is_what_the_code_actually_says():
    """The fixture is what the console renders before the backend is wired.

    If it says something the real check never emits, the console has been built
    against a sentence no officer will ever see.
    """
    import json

    from modules.validation.checksums import check_pan

    doc = json.loads((ROOT / "frontend" / "src" / "fixtures"
                      / "signals_crossdoc_mismatch.json").read_text(encoding="utf-8"))
    fixture = next(s for s in doc["signals"]
                   if s["id"] == "validation.format.pan.id_number")
    _ok, detail = check_pan("ABLPG7040F", surname="GHARAT")
    assert fixture["evidence"] == detail
