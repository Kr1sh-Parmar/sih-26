"""Load the OFAC SDN and UN Consolidated lists into the local watchlist table.

Setup-time tooling. Runs once, offline, against files already downloaded into
data/raw/reference/watchlist/. Nothing here is called at inspection time.

    python data/tools/load_watchlist.py
    python data/tools/load_watchlist.py --seed-demo

Why real lists rather than an invented table: OFAC and the UN publish free,
public data, and it comes with the problems that make watchlist matching
genuinely hard - transliteration variants, dozens of aliases per person,
year-only dates of birth (D21). An invented table would have none of those and
would prove nothing.

Only individuals are loaded. Vessels and companies do not present an identity
document at a border counter.
"""
import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.store import DEFAULT_DB, Store              # noqa: E402
from modules.extraction import normalize as N         # noqa: E402

WATCHLIST = ROOT / "data" / "raw" / "reference" / "watchlist"
NULL = "-0-"

#: OFAC sdn.csv has no header row. Columns per the OFAC file specification.
SDN_COLUMNS = ("ent_num", "name", "sdn_type", "program", "title", "call_sign",
               "vess_type", "tonnage", "grt", "vess_flag", "vess_owner", "remarks")


def clean(value: str | None) -> str:
    value = (value or "").strip()
    return "" if value in (NULL, "") else value


def load_ofac(store: Store) -> int:
    sdn = WATCHLIST / "sdn.csv"
    alt = WATCHLIST / "alt.csv"
    if not sdn.exists():
        print(f"  skipped OFAC: {sdn} not found")
        return 0

    aliases: dict[str, list[str]] = {}
    if alt.exists():
        with alt.open(encoding="utf-8", errors="replace", newline="") as fh:
            for row in csv.reader(fh):
                if len(row) >= 4 and clean(row[3]):
                    aliases.setdefault(row[0].strip(), []).append(clean(row[3]))

    loaded = 0
    with sdn.open(encoding="utf-8", errors="replace", newline="") as fh:
        for row in csv.reader(fh):
            if len(row) < len(SDN_COLUMNS):
                continue
            record = dict(zip(SDN_COLUMNS, row))
            if clean(record["sdn_type"]).lower() != "individual":
                continue

            name = clean(record["name"])
            if not name:
                continue
            remarks = clean(record["remarks"])
            store.add_watchlist_entry(
                source="OFAC", name=name, name_key=N.watchlist_key(name),
                aliases=aliases.get(record["ent_num"].strip(), []),
                dob=_ofac_dob(remarks),
                doc_numbers=_ofac_documents(remarks),
            )
            loaded += 1
    return loaded


def _ofac_dob(remarks: str) -> str | None:
    """OFAC keeps dates of birth in free text: "DOB 12 Mar 1965; ...".

    Returns ISO only when the remark carries a full, unambiguous date. A
    year-only entry is left null rather than invented as 1 January - a made-up
    day would make a namesake look like a match, or hide a real one.
    """
    import re
    match = re.search(r"DOB\s+(\d{1,2}\s+\w{3}\s+\d{4})", remarks)
    if not match:
        return None
    from datetime import datetime
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(match.group(1), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _ofac_documents(remarks: str) -> list[str]:
    import re
    found = []
    for pattern in (r"Passport\s+([A-Z0-9]{5,12})", r"National ID No\.?\s+([A-Z0-9]{5,20})"):
        found += [m.upper() for m in re.findall(pattern, remarks)]
    return sorted(set(found))


def load_un(store: Store) -> int:
    path = WATCHLIST / "un_consolidated.xml"
    if not path.exists():
        print(f"  skipped UN: {path} not found")
        return 0

    root = ET.parse(path).getroot()
    individuals = root.find("INDIVIDUALS")
    if individuals is None:
        return 0

    loaded = 0
    for person in individuals:
        parts = [clean(person.findtext(tag)) for tag in
                 ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
        name = " ".join(p for p in parts if p)
        if not name:
            continue

        aliases = [clean(a.findtext("ALIAS_NAME"))
                   for a in person.findall("INDIVIDUAL_ALIAS")]
        store.add_watchlist_entry(
            source="UN", name=name, name_key=N.watchlist_key(name),
            aliases=[a for a in aliases if a],
            dob=_un_dob(person),
            nationality=clean(person.findtext("NATIONALITY/VALUE")),
            doc_numbers=[clean(d.findtext("NUMBER"))
                         for d in person.findall("INDIVIDUAL_DOCUMENT")
                         if clean(d.findtext("NUMBER"))],
        )
        loaded += 1
    return loaded


def _un_dob(person) -> str | None:
    node = person.find("INDIVIDUAL_DATE_OF_BIRTH")
    if node is None:
        return None
    full = clean(node.findtext("DATE"))
    if full:
        try:
            from datetime import datetime
            return datetime.strptime(full, "%Y-%m-%d").date().isoformat()
        except ValueError:
            return None
    # YEAR-only and TYPE_OF_DATE="APPROXIMATELY" entries stay null. Layer E
    # treats a missing date as "cannot rule out", which is the safe direction.
    return None


#: Synthetic entries matching the demo documents, so a hit actually fires on
#: stage. These are invented people; no real listed person is used for a demo.
DEMO_ENTRIES = [
    {"source": "synthetic", "name": "RAKESH KUMAR VERMA",
     "aliases": ["R K VERMA"], "dob": "1985-04-17",
     "doc_numbers": ["E7654321", "ABLPV1234K"]},
    {"source": "synthetic", "name": "SUNITA DEVI",
     "aliases": [], "dob": "1979-11-23", "doc_numbers": ["X9999999"]},
]


def seed_demo(store: Store) -> int:
    for entry in DEMO_ENTRIES:
        store.add_watchlist_entry(name_key=N.watchlist_key(entry["name"]), **entry)
    return len(DEMO_ENTRIES)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--seed-demo", action="store_true",
                        help="add synthetic entries matching the demo documents")
    args = parser.parse_args()

    store = Store(args.db)
    before = store.watchlist_size()
    if before:
        print(f"watchlist already holds {before} entries; not reloading")
        return 0

    print(f"loading into {args.db}")
    ofac = load_ofac(store)
    print(f"  OFAC individuals: {ofac}")
    un = load_un(store)
    print(f"  UN individuals:   {un}")
    if args.seed_demo:
        print(f"  synthetic demo:   {seed_demo(store)}")
    print(f"total {store.watchlist_size()} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
