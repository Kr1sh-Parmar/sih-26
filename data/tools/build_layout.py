"""Build the per-document layout reference from labelled genuine cards.

    python data/tools/build_layout.py

Writes `config/layout/<doc_type>.json`: for each of the 22 ontology classes, the
median normalised centre of that field across every labelled genuine card of
that type, plus the median absolute deviation, plus how many cards it was
measured on.

This replaces a hand-drawn template. Vectorising six documents is nine days of
work the roadmap says cannot be compressed; measuring where the fields actually
sit on 8,320 already-labelled cards is one pass over files we already have, and
it is a better sentence in front of a panel: the reference is not our drawing of
what a card looks like, it is what several thousand genuine cards did.

What it cannot do: it inherits the dataset's coverage. A class with 25 instances
from a single source gets a spread that means nothing, so `modules/tamper/
physical.py` refuses to check any field measured on fewer than 50 cards.

Labels are read from the merged YOLO set, which is per-source-card split, so the
same card cannot contribute to both this reference and the held-out evaluation.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.profiles import DOC_TYPES                                 # noqa: E402

DATASET = ROOT / "data" / "processed" / "fields"
OUT = ROOT / "config" / "layout"

#: Fields measured on fewer genuine cards than this are recorded but never
#: checked. `signature` has 25 cards from one source; a position measured on 25
#: examples of one printing is not a fact about the document type.
MIN_CARDS = 50


def ontology() -> list[str]:
    import yaml
    data = yaml.safe_load((DATASET / "data.yaml").read_text(encoding="utf-8"))
    return list(data["names"])


def source_card(stem: str) -> str:
    """The source card a merged file came from, ignoring its augmentations.

    Roboflow ships many augmented copies of one card as `<card>.rf.<hash>`.
    Counting files instead of cards would inflate every `n` here by five or ten
    and quietly defeat the MIN_CARDS guard, which exists precisely so a class
    measured on a handful of real cards is not treated as measured.
    """
    return stem.split(".rf.")[0]


def doc_type_of(stem: str) -> str | None:
    for doc_type in DOC_TYPES:
        if stem.startswith(doc_type):
            return doc_type
    return None


def collect() -> dict:
    """{doc_type: {class_name: [(cx, cy), ...]}} over every labelled card."""
    names = ontology()
    found: dict = defaultdict(lambda: defaultdict(list))
    cards: dict = defaultdict(set)
    per_class_cards: dict = defaultdict(lambda: defaultdict(set))

    for split in ("train", "valid", "test"):
        labels = DATASET / split / "labels"
        if not labels.exists():
            continue
        for path in labels.glob("*.txt"):
            doc_type = doc_type_of(path.stem)
            if doc_type is None:
                continue
            card = source_card(path.stem)
            cards[doc_type].add(card)
            for line in path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) < 5:
                    continue
                index = int(parts[0])
                if not 0 <= index < len(names):
                    continue
                # YOLO labels are already normalised centre-x, centre-y.
                found[doc_type][names[index]].append(
                    (float(parts[1]), float(parts[2])))
                per_class_cards[doc_type][names[index]].add(card)
    return found, cards, per_class_cards


def summarise(points: list, cards: int) -> dict:
    array = np.array(points, dtype=np.float64)
    centre = np.median(array, axis=0)
    mad = np.median(np.abs(array - centre), axis=0) * 1.4826
    return {
        "cx": round(float(centre[0]), 4),
        "cy": round(float(centre[1]), 4),
        # A field that genuinely never moves would give a zero spread and then
        # divide every real card into an outlier. Floor it at one percent of
        # the page, which is smaller than any capture is accurate to anyway.
        "mad_x": round(max(float(mad[0]), 0.01), 4),
        "mad_y": round(max(float(mad[1]), 0.01), 4),
        # Unique source cards, not files. This is the number the checker
        # gates on, so it has to be the honest one.
        "n": cards,
        "boxes": len(points),
    }


def main() -> int:
    if not (DATASET / "data.yaml").exists():
        print(f"no dataset at {DATASET}. Run data/tools/build_field_dataset.py first.")
        return 1

    found, cards, per_class_cards = collect()
    if not found:
        print("no labels carried a recognisable document type prefix; nothing written.")
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    for doc_type in sorted(found):
        fields = {name: summarise(points, len(per_class_cards[doc_type][name]))
                  for name, points in sorted(found[doc_type].items())}
        usable = sum(1 for f in fields.values() if f["n"] >= MIN_CARDS)
        payload = {
            "doc_type": doc_type,
            "source": "data/processed/fields, labelled genuine cards",
            "cards": len(cards[doc_type]),
            "min_cards_to_check": MIN_CARDS,
            "fields": fields,
        }
        path = OUT / f"{doc_type}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"{doc_type:10s} {len(cards[doc_type]):5d} cards, "
              f"{len(fields):2d} classes, {usable:2d} with enough data to check "
              f"-> {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
