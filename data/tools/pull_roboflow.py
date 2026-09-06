"""Pull Universe datasets into data/raw/<bucket>/<project>/ as YOLO.

Needs a PRIVATE key in .env (ROBOFLOW_API_KEY=). The publishable rf_<id> key is
rejected by the export API. Build-time only - nothing here runs at inference.

Always exports COCO and converts locally. Roboflow's own YOLO writer produced
CORRUPT boxes for monika-ztd2k/aadhaar-card-1-ebbdz (heights collapsed to
~0.00, centres shifted) while COCO for the same version was pixel-correct, so
we do not trust it. Verify geometry after every pull:
    python data/tools/draw_boxes.py <dataset dir> <out.png>

Re-runnable: a project directory that already has data.yaml is skipped.
Pass --force to re-pull anyway, or names/buckets to filter.
"""
import sys, time, zipfile, requests
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEY = next((l.split("=", 1)[1].strip() for l in (ROOT / ".env").read_text().splitlines()
            if l.startswith("ROBOFLOW_API_KEY=")), "")
assert KEY and not KEY.startswith("rf_"), "put a PRIVATE ROBOFLOW_API_KEY in .env"
API = "https://api.roboflow.com"

TARGETS = [
    ("dl",       "university-of-greenwich-xo9z4", "driving-licence-text-detection"),
    ("dl",       "jaspreetsingh",                 "indian-driving-licence-reader-rlxel"),
    ("dl",       "license-plate-detection-ov9nk", "my-first-project-fypmb"),
    ("aadhaar",  "monika-ztd2k",                  "aadhaar-card-1-ebbdz"),
    ("aadhaar",  "mitesh-workspace",              "aadhaar-card-annotation"),
    ("aadhaar",  "mitesh-workspace",              "back-aadhaar-card"),
    ("aadhaar",  "project-epimx",                 "id-bdbwr"),
    ("tamper",   "tampering-detection",           "tampering-detection-0muly"),
    ("pan",      "cardamage-fvhwg",               "pan-card-entity-extraction"),
    ("doctype",  "mahrprojects",                  "identity-card-classifier"),
    ("doctype",  "ip2-kbjz5",                     "identity-card-segmentation"),
    ("visa",     "omkar-padave-vjltn",            "visa-o0eyd"),
    ("passport", "at-in",                         "bangladeshi-passport-fields"),
    ("passport", "phiphi-20ww6",                  "passport-page-mrz-detection"),
    ("passport", "misha-88lag",                   "passport-exe8g"),
    ("passport", "bms-ur6hn",                     "passport-sscsb"),
    ("passport", "arvind-kumar-wjygd",            "passport-ppwp8"),
]


def coco_to_yolo(out):
    """Rewrite every _annotations.coco.json in place as YOLO labels + data.yaml."""
    import json
    names, ids = [], {}
    jsons = sorted(out.rglob("_annotations.coco.json"))
    for jp in jsons:                                   # one pass to fix the class order
        for c in json.load(open(jp))["categories"]:
            if c["name"] not in ids and c["supercategory"] != "none":
                ids[c["name"]] = len(names); names.append(c["name"])
    for jp in jsons:
        j = json.load(open(jp))
        cat = {c["id"]: c["name"] for c in j["categories"]}
        img = {i["id"]: i for i in j["images"]}
        split = jp.parent
        (split / "images").mkdir(exist_ok=True)
        (split / "labels").mkdir(exist_ok=True)
        lines = {}
        for a in j["annotations"]:
            nm = cat[a["category_id"]]
            if nm not in ids:
                continue
            i = img[a["image_id"]]
            W, H, (x, y, w, h) = i["width"], i["height"], a["bbox"]
            lines.setdefault(i["file_name"], []).append(
                f"{ids[nm]} {(x+w/2)/W:.6f} {(y+h/2)/H:.6f} {w/W:.6f} {h/H:.6f}")
        for i in j["images"]:
            fn = i["file_name"]
            src = split / fn
            if src.exists():
                src.rename(split / "images" / fn)
            (split / "labels" / (Path(fn).stem + ".txt")).write_text(
                "\n".join(lines.get(fn, [])))
        jp.unlink()
    (out / "data.yaml").write_text(
        "train: train/images\nval: valid/images\ntest: test/images\n"
        f"nc: {len(names)}\nnames: {names!r}\n")
    return names


def pull(bucket, ws, proj, force=False):
    out = ROOT / "data" / "raw" / bucket / proj
    if (out / "data.yaml").exists() and not force:
        return "skip (already on disk)"

    meta = requests.get(f"{API}/{ws}/{proj}?api_key={KEY}", timeout=60).json()
    if "error" in meta:
        return f"FAIL project: {meta['error'].get('message', '')[:90]}"
    # Only versions that actually offer an export, closest to the project's RAW
    # image count - the bigger versions are augmented copies, which is the
    # train/test leakage this project already got bitten by once.
    raw = meta["project"]["images"]
    vers = [v for v in (meta.get("versions") or []) if v.get("exports")]
    if not vers:
        return f"FAIL: no generated version with an export - {raw} imgs"
    v = min(vers, key=lambda x: (abs((x.get("images") or 0) - raw),
                                 -int(x["id"].rsplit("/", 1)[1])))
    vnum = v["id"].rsplit("/", 1)[1]

    for fmt in [f for f in ("coco", "yolov11", "yolov8") if f in v["exports"]]:
        link = None
        for _ in range(2):   # the first call can only trigger generation
            d = requests.get(f"{API}/{ws}/{proj}/{vnum}/{fmt}?api_key={KEY}", timeout=180).json()
            link = (d.get("export") or {}).get("link")
            if link:
                break
        if not link:
            continue
        tmp = ROOT / "data" / "raw" / f".{proj}.zip"
        with requests.get(link, stream=True, timeout=900) as z:
            if z.status_code != 200:
                continue
            with open(tmp, "wb") as fh:
                for chunk in z.iter_content(1 << 20):
                    fh.write(chunk)
        out.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(tmp).extractall(out)
        mb = tmp.stat().st_size / 1e6
        tmp.unlink()
        extra = ""
        if fmt == "coco":
            extra = f" -> {len(coco_to_yolo(out))} classes"
        n = sum(1 for _ in out.rglob("*") if _.is_file())
        return f"ok  v{vnum} {fmt}{extra} {v.get('images')} imgs, {n} files, {mb:.0f} MB"
    return "FAIL: no downloadable export format"


args = sys.argv[1:]
force = "--force" in args
only = [a for a in args if not a.startswith("--")]
for bucket, ws, proj in TARGETS:
    if only and not any(o in proj or o == bucket for o in only):
        continue
    print(f"{bucket:9} {ws}/{proj}", flush=True)
    for attempt in range(3):        # home wifi drops mid-pull; just try again
        try:
            print(f"          {pull(bucket, ws, proj, force)}", flush=True)
            break
        except Exception as e:
            print(f"          retry {attempt+1}/3 after {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(10)
