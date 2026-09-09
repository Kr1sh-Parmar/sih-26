"""Generate a labelled synthetic document set. BUILD TIME ONLY.

    python data/tools/generate_documents.py --count 200
    python data/tools/generate_documents.py --count 40 --forgeries

Writes into `data/processed/generated/` in the same YOLO layout
`data/tools/build_field_dataset.py` merges, and with the same filename
convention - `<doc_type>__gen_<seed>.png` - so the document type survives into
the merged set and `build_layout.py` keeps working.

**Splits are per identity, not per file.** One person holds six documents; if
their passport landed in train and their Aadhaar in valid, the same face and
the same name would appear on both sides of the split. That is the leak
`build_field_dataset.py` already guards against for augmented copies, and it is
the same mistake in a new place.

The four classes with zero real instances - `ghost_photo`, `barcode`,
`hologram`, `doc_title` - are the reason this exists. `data/TRAINING.md` says
the detector cannot learn them, and it could not, because nothing in the merged
set ever showed it one.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from data.generator import DOC_TYPES, build, session                # noqa: E402
from data.generator.render import ONTOLOGY                          # noqa: E402
from data.tools import mutate                                       # noqa: E402

OUT = ROOT / "data" / "processed" / "generated"

#: Same proportions as the scraped set, so merging does not skew the splits.
SPLITS = (("train", 0.72), ("valid", 0.20), ("test", 0.08))


def split_for(index: int, total: int) -> str:
    position = index / max(1, total)
    running = 0.0
    for name, share in SPLITS:
        running += share
        if position < running:
            return name
    return SPLITS[-1][0]


def write_one(doc, split: str, stem: str) -> None:
    images = OUT / split / "images"
    labels = OUT / split / "labels"
    images.mkdir(parents=True, exist_ok=True)
    labels.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(images / f"{stem}.png"), doc.image)
    (labels / f"{stem}.txt").write_text(
        "\n".join(doc.yolo_labels()) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=100,
                        help="identities; each yields one document per type")
    parser.add_argument("--types", nargs="*", default=list(DOC_TYPES))
    parser.add_argument("--forgeries", action="store_true",
                        help="also write a mutated copy of each document, with "
                             "its ground-truth mask")
    parser.add_argument("--sessions", type=int, default=0,
                        help="matched Aadhaar+PAN sets with a disagreeing date "
                             "of birth - Scene 3, as data")
    parser.add_argument("--clean", action="store_true", help="empty the output first")
    args = parser.parse_args()

    if args.clean and OUT.exists():
        shutil.rmtree(OUT)

    manifest, counts = [], {name: 0 for name in ONTOLOGY}
    for index in range(args.count):
        split = split_for(index, args.count)
        for doc_type in args.types:
            seed = index * 17 + DOC_TYPES.index(doc_type)
            # Aadhaar carries the signed payload; it is the document Layer D
            # propagates *from*, so it is the one worth signing by default.
            doc = build(doc_type, seed=seed, sign=(doc_type == "aadhaar"))
            stem = f"{doc_type}__gen_{seed:06d}"
            write_one(doc, split, stem)
            for name, *_ in doc.labels:
                counts[name] = counts.get(name, 0) + 1

            entry = {"stem": stem, "split": split, "doc_type": doc_type,
                     "seed": seed, "signed": bool(doc.envelope),
                     "identity": doc.identity.name, "dob": doc.identity.dob}

            if args.forgeries:
                family = mutate.FAMILIES[index % len(mutate.FAMILIES)]
                forged, mask = mutate.apply(family, doc.image, seed=seed)
                forged_stem = f"{stem}_forged_{family}"
                write_one(_replaced(doc, forged), split, forged_stem)
                masks = OUT / split / "masks"
                masks.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(masks / f"{forged_stem}.png"), mask)
                entry["forgery"] = {"family": family, "stem": forged_stem}

            manifest.append(entry)

        if index % 20 == 0:
            print(f"  {index}/{args.count} identities")

    for n in range(args.sessions):
        docs = session(seed=90000 + n, disagree_on="dob")
        for doc in docs:
            stem = f"{doc.doc_type}__gen_session{n:03d}"
            write_one(doc, "test", stem)
            manifest.append({"stem": stem, "split": "test",
                             "doc_type": doc.doc_type, "session": n,
                             "signed": bool(doc.envelope),
                             "identity": doc.identity.name,
                             "dob": doc.identity.dob})

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "manifest.json").write_text(json.dumps({
        "identities": args.count, "types": args.types,
        "documents": len(manifest),
        "class_instances": {k: v for k, v in sorted(counts.items()) if v},
        "entries": manifest,
    }, indent=2), encoding="utf-8")

    print(f"\n{len(manifest)} documents -> {OUT.relative_to(ROOT)}")
    print("\nclass instances:")
    for name in ONTOLOGY:
        mark = "  <- was empty in the scraped set" if name in (
            "ghost_photo", "barcode", "hologram", "doc_title") else ""
        print(f"  {name:20s} {counts.get(name, 0):6d}{mark}")

    empty = [n for n in ONTOLOGY if not counts.get(n)]
    if empty:
        print(f"\nstill no instances of: {', '.join(empty)}")
    return 0


def _replaced(doc, image):
    """The same document with different pixels - labels and values unchanged.

    A mutation moves pixels inside a field, not the field itself, so the boxes
    still describe where everything is.
    """
    from dataclasses import replace
    return replace(doc, image=image)


if __name__ == "__main__":
    sys.exit(main())
