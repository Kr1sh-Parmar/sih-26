"""Merge every source dataset into ONE YOLO dataset on the frozen 22-class
ontology (TECHNICAL-SPEC.md sec.5), so a single detector covers all six
document types (D17). Source class names never reach the model.

Two things this does that a naive merge does not:
  * Images are hardlinked, not copied - the merged set costs no extra disk.
  * Splits are assigned per SOURCE image, not per file. Roboflow ships many
    augmented copies of one card; splitting per file puts the same card in
    train and valid and inflates validation mAP.
"""
import re, os, shutil, hashlib
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parents[2]
OUT  = ROOT / "data" / "processed" / "fields"

ONTOLOGY = ["person_photo","ghost_photo","signature","qr_code","barcode","mrz",
            "name","father_name","dob","gender","address","nationality",
            "id_number","secondary_id","issue_date","expiry_date",
            "issuing_authority","emblem","logo","hologram","blood_group","doc_title"]
IDX = {c: i for i, c in enumerate(ONTOLOGY)}

# None = drop the box. "DOC" = document-level, belongs to the segmentation model.
# Keys are paths under the repo root. Everything under data/raw/ is pulled by
# data/tools/pull_roboflow.py. Before adding a source, run BOTH gates:
#   data/tools/audit_raw.py     - are there actually boxes?
#   data/tools/peek_images.py   - are the images the right thing?
# The second gate is not optional. fil-9zpqb/voter-01 passed the first with 477
# healthy `voter` boxes and turned out to be 146 Albion Online screenshots.
MAP = {
 "SIH/SIH/Aadhar dataset": ("aadhaar", {
   "id_number":"id_number","dob":"dob","gender":"gender","name":"name","address":"address"}),
 "SIH/SIH/PAN dataset": ("pan", {
   "dob":"dob","father":"father_name","name":"name","pan":"id_number"}),
 "SIH/SIH/VoterID dataset": ("voter_id", {
   "address":"address","age":None,"age_as_on":None,"date":None,"point":None,
   "card_voterid_1_back":"DOC","card_voterid_1_front":"DOC",
   "card_voterid_2_back":"DOC","card_voterid_2_front":"DOC",
   "date_of_issue":"issue_date","election":"issuing_authority","father":"father_name",
   "gender":"gender","name":"name","portrait":"person_photo","symbol":"emblem",
   "voter_id":"id_number"}),
 "SIH/SIH/Passport dataset/Passport Validation": ("passport", {"MRZ":"mrz"}),

 # --- Roboflow Universe, pulled 2026-09-06 -----------------------------------
 # Geometry taken from the COCO export: this project's YOLO export is CORRUPT
 # (box heights collapse to ~0.00). Closes qr_code, person_photo and logo.
 "data/raw/aadhaar/aadhaar-card-1-ebbdz": ("aadhaar", {
   "a_back":"DOC","a_front":"DOC","p_front":"DOC",
   "card_passport":"DOC","card_voter_id":"DOC",
   "a_bar":None,   # 14 boxes, and the crops are courier-label barcodes, not the card strip
   "a_emb":"emblem","p_emb":"emblem",
   "a_govt":"issuing_authority","a_uidai":"issuing_authority","p_gov":"issuing_authority",
   "a_masked":"id_number","a_num":"id_number","p_num":"id_number",
   "a_photo":"person_photo","a_qr":"qr_code","a_top":"logo","a_vid":"secondary_id"}),
 "data/raw/aadhaar/aadhaar-card-annotation": ("aadhaar", {
   "aadhaar-dob":"dob","aadhaar-name":"name","aadhaar-no":"id_number"}),
 "data/raw/aadhaar/back-aadhaar-card": ("aadhaar", {"aadhaar-father-name":"father_name"}),
 "data/raw/aadhaar/id-bdbwr": ("aadhaar", {
   "Aadhar number":"id_number","Emblem logo":"emblem","Goi logo":"issuing_authority",
   "Goi symbol":"issuing_authority","Meeseva logo":"logo",
   "Text layer":None,   # a region, not a field
   "fake":"DOC"}),      # document-level tamper label - Module 3, not the detector

 # The only Indian DL field annotations in existence. Closes blood_group.
 "data/raw/dl/my-first-project-fypmb": ("dl", {
   "address":"address","blood_group":"blood_group","dob":"dob","father_name":"father_name",
   "img":"person_photo","issue date":"issue_date","license_number":"id_number",
   "name":"name","validity":"expiry_date"}),
 "data/raw/dl/indian-driving-licence-reader-rlxel": ("dl", {
   "dl_number":"id_number","dob":"dob","name":"name"}),

 "data/raw/pan/pan-card-entity-extraction": ("pan", {
   "DOB":"dob","father-s name":"father_name","name":"name","pan number":"id_number"}),

 # Passport VIZ. Closes nationality, expiry_date and signature.
 # Dropped on purpose:
 #   country_code / Code / Country_Code - "IND" is the same fact as nationality
 #     "INDIAN" but a different-looking field; one class, two geometries.
 #   type / Type - the TD3 type code ("P"), not the printed document title.
 #   first_name2 / doc_id2 - these box the two MRZ lines SEPARATELY, while our
 #     mrz class is the whole two-line strip.
 #   place_of_birth / Place_of_Issue - no ontology class, and adding one needs
 #     discussion (CLAUDE.md).
 "data/raw/passport/passport-exe8g": ("passport", {
   "authority":"issuing_authority","country_code":None,"date_of_birth":"dob",
   "doc_id":"id_number","doc_id2":None,"expiry_date":"expiry_date",
   "first_name":"name","first_name2":None,"gender":"gender","issue_date":"issue_date",
   "last_name":"name","nationality":"nationality","place_of_birth":None,"type":None}),
 "data/raw/passport/passport-sscsb": ("passport", {
   "Authority":"issuing_authority","Code":None,"Date of Birth":"dob",
   "Date of expiration":"expiry_date","Date of issue":"issue_date","Gender":"gender",
   "Given Names":"name","Nationality":"nationality","Passport No-":"id_number",
   "Place of birth":None,"Surname":"name","Type":None,"words":None}),
 # 25 Indian passports - the only Indian passport VIZ we hold, and the only
 # source of `signature` anywhere in the corpus.
 "data/raw/passport/passport-ppwp8": ("passport", {
   "Birth_Place":None,"Country_Code":None,"DOB":"dob","DOE":"expiry_date",
   "DOI":"issue_date","Given_Name":"name","Nationality":"nationality",
   "Paasport_no":"id_number","Place_of_Issue":None,"Sex":"gender",
   "Sign":"signature","Surname":"name","Type":None}),
 "data/raw/passport/passport-page-mrz-detection": ("passport", {
   "mrz":"mrz","passport_page":"DOC"}),

 # The only visa annotations found. key*/value* are generic OCR key-value boxes.
 "data/raw/visa/visa-o0eyd": ("visa", {
   "Birthdate":"dob","Expiration Date":"expiry_date","Given Name":"name",
   "IssueDate":"issue_date","surname":"name","VisaType-Class":None,
   **{f"key{i}.0": None for i in range(1, 7)},
   **{f"value{i}.{j}": None for i in range(1, 7) for j in range(6)}}),

 # Document-level only - these feed the segmentation and routing models.
 "data/raw/doctype/identity-card-segmentation": ("doctype", {"identity_card":"DOC"}),
 "data/raw/doctype/identity-card-classifier": ("doctype", {
   "aadhar":"DOC","driver-license":"DOC","pan":"DOC","passport":"DOC","voter":"DOC"}),

 # NOT included, on purpose:
 #   data/raw/passport/bangladeshi-passport-fields - 200 images, 33 advertised
 #     classes, 27 boxes on ONE image. Keep the images as generator reference.
 #   data/raw/tamper/tampering-detection-0muly - Module 3 supervision, and its
 #     class list needs an audit first ('-', 'namenot there', a Roboflow
 #     artefact class). Not field-detector data.
}

def names_of(y):
    m = re.search(r"names:\s*\[(.*?)\]", Path(y).read_text(), re.S)
    return [x.strip().strip("'\"") for x in m.group(1).split(",")]

def link(src, dst):
    try: os.link(src, dst)
    except (OSError, NotImplementedError): shutil.copy2(src, dst)

# OneDrive keeps a handle on the directory itself, so clear contents
# rather than removing the root - rmtree(OUT) fails with WinError 32.
for _sub in ("train", "valid", "test"):
    for _kind in ("images", "labels"):
        _d = OUT/_sub/_kind
        if _d.is_dir():
            for _f in _d.iterdir():
                try: _f.unlink()
                except OSError: pass
for s in ("train", "valid", "test"):
    (OUT/s/"images").mkdir(parents=True, exist_ok=True)
    (OUT/s/"labels").mkdir(parents=True, exist_ok=True)

dropped, per_split, bad, empties = Counter(), Counter(), 0, 0
kept = Counter()
pending = []

for ds, (doctype, mp) in MAP.items():
    d = ROOT/ds
    if not (d/"data.yaml").exists():
        print(f"!! missing {ds}"); continue
    names = names_of(d/"data.yaml")
    # rglob, not the three split names - some exports ship a single export/ dir.
    for ldir in sorted(d.rglob("labels")):
        for lp in sorted(ldir.glob("*.txt")):
            ip = next((p for p in (ldir.parent/"images").glob(lp.stem + ".*")), None)
            if ip is None: continue
            out_lines = []
            for line in lp.read_text().split("\n"):
                p = line.split()
                if len(p) < 5: continue
                src_name = names[int(p[0])]
                tgt = mp.get(src_name, "UNMAPPED")
                if tgt in (None, "DOC", "UNMAPPED"):
                    dropped[f"{doctype}:{src_name}"] += 1; continue
                try: xywh = [float(v) for v in p[1:5]]
                except ValueError: bad += 1; continue
                if not all(0.0 <= v <= 1.0 for v in xywh) or xywh[2] <= 0 or xywh[3] <= 0:
                    bad += 1; continue
                out_lines.append(f"{IDX[tgt]} " + " ".join(f"{v:.6f}" for v in xywh))
            if not out_lines:
                empties += 1; continue
            # augmented copies of one card share the prefix before ".rf."
            src_key = f"{doctype}__" + re.sub(r"\.rf\..*$", "", lp.stem)
            pending.append((src_key, f"{doctype}__{lp.stem}", ip, out_lines))

groups = defaultdict(list)
for src_key, stem, ip, lines in pending:
    groups[src_key].append((stem, ip, lines))

for src_key, items in groups.items():
    h = int(hashlib.sha1(src_key.encode()).hexdigest()[:8], 16) % 100
    split = "train" if h < 70 else ("valid" if h < 90 else "test")
    for stem, ip, lines in items:
        (OUT/split/"labels"/f"{stem}.txt").write_text("\n".join(lines) + "\n")
        link(ip, OUT/split/"images"/f"{stem}{ip.suffix}")
        per_split[split] += 1
        for ln in lines:
            kept[ONTOLOGY[int(ln.split()[0])]] += 1

(OUT/"data.yaml").write_text(
    "# Generated by data/tools/build_field_dataset.py - do not hand-edit.\n"
    "train: ../train/images\nval: ../valid/images\ntest: ../test/images\n\n"
    f"nc: {len(ONTOLOGY)}\nnames: {ONTOLOGY}\n")

print(f"unique source images: {len(groups)}   files: {sum(per_split.values())}")
print(f"images per split: {dict(per_split)}")
print(f"skipped (no ontology boxes): {empties}   malformed boxes: {bad}")
print("\nkept instances by ontology class:")
for c in ONTOLOGY:
    print(f"   {IDX[c]:2d} {c:20s} {kept.get(c,0):6d}{'' if kept.get(c) else '   <-- ZERO'}")
print(f"\ntotal kept: {sum(kept.values())}   total dropped: {sum(dropped.values())}")
