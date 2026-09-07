"""Synthetic Indian identities, with numbers that survive our own checks.

BUILD TIME ONLY. Nothing under `api/ core/ fusion/ modules/` imports this.

No real person, no real number, ever (CLAUDE.md rule 4). Faker `en_IN` supplies
the name and address; every identity number is then *constructed* to be valid
under the same functions Layer A validates with, rather than sampled and hoped
over:

    Aadhaar     11 digits + `checksums.verhoeff_digit()`
    PAN         five letters whose fifth is the surname initial, per the
                published rule Layer A enforces
    EPIC        three-letter constituency code + seven digits
    DL          real state code, real RTO, plausible year
    MRZ         `mrz.build_td3()`, every check digit computed

That reuse is the point. `verhoeff_digit()`'s docstring has said *"Used by the
synthetic generator"* since it was written, with nothing using it. If the
generator computed its own check digits and the two implementations ever
disagreed, every generated document would be quietly invalid and the validation
tests would still pass, because they would be testing the same bug twice.

A generated identity is deliberately *self-consistent*: the same person, the
same dates, across every document they hold. Making two documents disagree is
then a single deliberate edit, which is what Scene 3 needs.
"""
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.extraction import mrz                                  # noqa: E402
from modules.validation.checksums import (PAN_HOLDER_TYPES,         # noqa: E402
                                          STATE_CODES, verhoeff_digit)

#: Three-letter EPIC constituency prefixes. Real ones are allotted per
#: constituency; these are drawn from the format, not from the register.
EPIC_PREFIXES = ("ABC", "MHK", "DLX", "KAR", "TNV", "UPB", "WBZ", "GJR")

#: Passport office codes appear in the optional data of an Indian TD3.
PASSPORT_OFFICES = ("MUMBAI", "DELHI", "CHENNAI", "KOLKATA", "BENGALURU",
                    "HYDERABAD", "PUNE", "AHMEDABAD")


@dataclass
class Identity:
    """One person, and every number they would hold. All synthetic."""
    surname: str
    given_names: str
    dob: str                     # ISO-8601
    sex: str                     # M | F
    address: str
    father_name: str
    nationality: str = "IND"
    aadhaar: str = ""
    pan: str = ""
    epic: str = ""
    dl: str = ""
    passport_number: str = ""
    issue_date: str = ""
    expiry_date: str = ""
    blood_group: str = ""
    dl_state: str = ""
    hindi_name: str = ""
    extras: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        return f"{self.given_names} {self.surname}".strip()

    @property
    def aadhaar_spaced(self) -> str:
        """4-4-4, the grouping UIDAI prints.

        `normalize.id_number` strips the spaces before Layer A sees it, so the
        printed form and the validated form differ on purpose - which is also
        what makes the OCR path's normalisation worth having.
        """
        n = self.aadhaar
        return f"{n[0:4]} {n[4:8]} {n[8:12]}" if len(n) == 12 else n

    @property
    def vid(self) -> str:
        """The 16-digit Virtual ID, Verhoeff-valid like the Aadhaar itself."""
        return self.extras.get("vid", "")

    @property
    def passport_office(self) -> str:
        return self.extras.get("passport_office", "")

    @property
    def face_seed(self) -> int:
        """Which portrait this person has.

        It belongs to the *identity*, not to the render call. Otherwise one
        person's Aadhaar and PAN carry two different faces - which is a
        generator artefact that Scene 3 would show an officer as two different
        people, and that the face module would correctly flag as a mismatch.
        """
        return int(self.extras.get("face_seed", 0))

    def mrz(self) -> str:
        """The TD3 strip for this person's passport. Every check digit real."""
        return mrz.build_td3(
            doc_code="P", issuing_state="IND", surname=self.surname,
            given_names=self.given_names, document_number=self.passport_number,
            nationality=self.nationality, birth_date=self.dob,
            sex=self.sex, expiry_date=self.expiry_date,
            optional_data=self.extras.get("passport_office", ""),
        )

    def payload(self, doc_type: str) -> dict:
        """The signed-QR payload for this document. Canonical field names."""
        numbers = {"aadhaar": self.aadhaar, "pan": self.pan,
                   "voter_id": self.epic, "dl": self.dl,
                   "passport": self.passport_number,
                   "visa": self.passport_number}
        payload = {
            "doc_type": doc_type,
            "name": self.name.upper(),
            "dob": self.dob,
            "gender": self.sex,
            "id_number": numbers.get(doc_type, ""),
            "nationality": self.nationality,
        }
        if doc_type in ("passport", "visa", "dl"):
            payload["expiry_date"] = self.expiry_date
            payload["issue_date"] = self.issue_date
        if doc_type in ("aadhaar", "pan", "voter_id", "dl"):
            payload["father_name"] = self.father_name.upper()
        return payload


def _aadhaar(rng: random.Random) -> str:
    """Eleven digits not starting 0 or 1, plus the Verhoeff digit Layer A checks."""
    payload = str(rng.randint(2, 9)) + "".join(
        str(rng.randint(0, 9)) for _ in range(10))
    return payload + verhoeff_digit(payload)


def _pan(rng: random.Random, surname: str) -> str:
    """Fifth character is the surname initial. That is the rule Layer A enforces."""
    initial = (surname.strip().upper() + "X")[0]
    if not initial.isalpha():
        initial = "X"
    letters = "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(3))
    # 'P' for individual - every generated identity is a person.
    holder = "P"
    assert holder in PAN_HOLDER_TYPES
    return f"{letters}{holder}{initial}{rng.randint(1000, 9999)}" \
           f"{rng.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}"


def _epic(rng: random.Random) -> str:
    return rng.choice(EPIC_PREFIXES) + f"{rng.randint(0, 9999999):07d}"


def _dl(rng: random.Random, issue_year: int) -> tuple[str, str]:
    """Returns (licence number, state code). Both real format, no real holder."""
    # OR duplicates OD in STATE_CODES; picking it would make the state name
    # ambiguous in the evidence string for no gain.
    state = rng.choice([s for s in sorted(STATE_CODES) if s != "OR"])
    return (f"{state}{rng.randint(1, 99):02d}{issue_year}"
            f"{rng.randint(0, 9999999):07d}"), state


def _iso(d: date) -> str:
    return d.isoformat()


def build(seed: int = 0, *, today: date | None = None) -> Identity:
    """One self-consistent synthetic identity.

    Same seed, same person - so a test can regenerate the exact document it is
    asserting about, and so an Aadhaar and a PAN built from one seed agree
    with each other by construction. Making them disagree is then one edit.
    """
    from faker import Faker

    today = today or date(2026, 9, 7)
    rng = random.Random(seed)
    fake = Faker("en_IN")
    fake.seed_instance(seed)

    sex = rng.choice(["M", "F"])
    surname = fake.last_name().upper()
    given = (fake.first_name_male() if sex == "M" else fake.first_name_female()).upper()

    age = rng.randint(19, 68)
    dob = today - timedelta(days=age * 365 + rng.randint(0, 364))
    issued = today - timedelta(days=rng.randint(200, 8 * 365))
    # A ten-year Indian passport. Some are deliberately already expired, so the
    # expiry check has something true to find.
    expires = issued + timedelta(days=10 * 365)

    identity = Identity(
        surname=surname,
        given_names=given,
        dob=_iso(dob),
        sex=sex,
        address=fake.address().replace("\n", ", "),
        father_name=f"{fake.first_name_male().upper()} {surname}",
        aadhaar=_aadhaar(rng),
        pan=_pan(rng, surname),
        epic=_epic(rng),
        passport_number=f"{rng.choice('ZPMKLTVW')}{rng.randint(1000000, 9999999)}",
        issue_date=_iso(issued),
        expiry_date=_iso(expires),
        blood_group=rng.choice(["A+", "A-", "B+", "B-", "O+", "O-", "AB+", "AB-"]),
    )
    identity.dl, identity.dl_state = _dl(rng, issued.year)
    identity.extras["passport_office"] = rng.choice(PASSPORT_OFFICES)
    identity.extras["face_seed"] = seed
    vid_payload = "".join(str(rng.randint(0, 9)) for _ in range(15))
    identity.extras["vid"] = vid_payload + verhoeff_digit(vid_payload)
    # Devanagari transliteration is not attempted - a wrong transliteration on a
    # generated card would be a fact about our romanisation, not about Hindi.
    # The Hindi line carries the document's own static wording instead.
    identity.hindi_name = ""
    return identity


def demo() -> None:
    """Self-check: every number this produces passes the validator that guards it."""
    from modules.validation.checksums import (check_aadhaar, check_dl, check_epic,
                                              check_pan)

    for seed in range(25):
        who = build(seed)
        ok, detail = check_aadhaar(who.aadhaar)
        assert ok, f"seed {seed}: {detail}"
        ok, detail = check_pan(who.pan, who.surname)
        assert ok, f"seed {seed}: {detail}"
        ok, detail = check_epic(who.epic)
        assert ok, f"seed {seed}: {detail}"
        ok, detail = check_dl(who.dl)
        assert ok, f"seed {seed}: {detail}"

        parsed = mrz.parse(who.mrz())
        assert parsed.birth_date == who.dob, f"seed {seed}: MRZ dob {parsed.birth_date}"
        assert parsed.surname == who.surname, f"seed {seed}: {parsed.surname}"
        assert all(mrz.verify(v, d) for v, d in parsed.check_digits.values()), \
            f"seed {seed}: an MRZ check digit does not verify"

        assert build(seed).aadhaar == who.aadhaar, "not reproducible from its seed"

    who = build(1)
    print(f"{who.name}  {who.dob}  {who.sex}")
    print(f"  aadhaar {who.aadhaar}   pan {who.pan}   epic {who.epic}")
    print(f"  dl {who.dl} ({who.dl_state})   passport {who.passport_number}")
    print("  " + who.mrz().replace("\n", "\n  "))
    print("\n25 identities, every number valid under the checks Layer A runs")


if __name__ == "__main__":
    demo()
