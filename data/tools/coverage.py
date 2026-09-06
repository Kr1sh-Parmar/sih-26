import re, sys
from pathlib import Path
from collections import Counter

ROOT = Path("SIH/SIH")
ONTOLOGY = ["person_photo","ghost_photo","signature","qr_code","barcode","mrz",
            "name","father_name","dob","gender","address","nationality",
            "id_number","secondary_id","issue_date","expiry_date",
            "issuing_authority","emblem","logo","hologram","blood_group","doc_title"]

# per-dataset: source class name -> ontology class (or None = drop, DOC = document-level)
MAP = {
 "Aadhar dataset": {"id_number":"id_number","dob":"dob","gender":"gender",
                    "name":"name","address":"address"},
 "PAN dataset": {"dob":"dob","father":"father_name","name":"name","pan":"id_number"},
 "VoterID dataset": {"address":"address","age":None,"age_as_on":None,
   "card_voterid_1_back":"DOC","card_voterid_1_front":"DOC",
   "card_voterid_2_back":"DOC","card_voterid_2_front":"DOC",
   "date":None,"date_of_issue":"issue_date","election":"issuing_authority",
   "father":"father_name","gender":"gender","name":"name","point":None,
   "portrait":"person_photo","symbol":"emblem","voter_id":"id_number"},
 "Passport dataset/Passport Validation": {"MRZ":"mrz"},
 "Passport dataset/passport": {"passport":"DOC"},
 "Passport dataset/PassportAreaNames": {"field_name":None},
}

def names_of(yml):
    t = Path(yml).read_text()
    m = re.search(r"names:\s*\[(.*?)\]", t, re.S)
    return [x.strip().strip("'\"") for x in m.group(1).split(",")]

totals, per_ds = Counter(), {}
for ds, mp in MAP.items():
    d = ROOT/ds
    y = d/"data.yaml"
    if not y.exists(): continue
    names = names_of(y)
    cnt = Counter()
    for split in ("train","valid","test"):
        for lp in (d/split/"labels").glob("*.txt"):
            for line in lp.read_text().split("\n"):
                p = line.split()
                if len(p) >= 5: cnt[names[int(p[0])]] += 1
    res = Counter()
    for src, n in cnt.items():
        tgt = mp.get(src, "UNMAPPED")
        res[tgt if tgt else "DROP"] += n
    per_ds[ds] = (cnt, res)
    for k, v in res.items():
        if k not in ("DROP","DOC","UNMAPPED"): totals[k] += v

print("=" * 62)
print("PER-DATASET REMAP")
for ds, (cnt, res) in per_ds.items():
    print(f"\n-- {ds}")
    for src, n in cnt.most_common():
        tgt = MAP[ds].get(src, "UNMAPPED")
        print(f"   {src:24s} {n:6d}  ->  {tgt or 'DROP'}")
print("\n" + "=" * 62)
print("ONTOLOGY COVERAGE (22 classes)")
have = miss = 0
for c in ONTOLOGY:
    n = totals.get(c, 0)
    if n: have += 1
    else: miss += 1
    print(f"   {c:20s} {n:6d} {'' if n else '   <-- ZERO'}")
print(f"\n   covered {have}/22, missing {miss}")
