"""Train the 22-class field detector, then export it for the screening path.

BUILD-TIME ONLY. Runs in .venv-train, which is the only place CUDA and torch
exist. Nothing here is importable from api/, and the screening path never sees
torch - it loads the exported int8 ONNX through onnxruntime on CPU
(CLAUDE.md rule 2). Training on a GPU is fine; inferring on one is not.

    .venv-train/Scripts/python data/tools/train_fields.py --epochs 100
    .venv-train/Scripts/python data/tools/train_fields.py --export-only

One detector for six document types, not six detectors (D17). Shared classes -
name, dob, photo, signature appear on all six - generalise better from pooled
data than six small models each seeing 200 images, and it is one warm session
instead of six.

Do not point this at data/raw/*/*/train. Source datasets ship augmented copies
of one card spread across their own splits; data/processed/fields was built by
assigning splits per source card, and training on the raw splits leaks.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed" / "fields" / "data.yaml"
RUNS = ROOT / "runs" / "fields"
MODELS = ROOT / "models"

#: Ships with the image and is the thing the officer console depends on.
EXPORT_NAME = "field_detector_22cls"


def check_environment() -> None:
    try:
        import torch
    except ImportError:
        sys.exit("torch is missing. Run this with .venv-train/Scripts/python, "
                 "not the base interpreter.")
    if not torch.cuda.is_available():
        print("WARNING: CUDA is not available. Training on CPU will take days "
              "rather than hours. Continuing anyway.")
    else:
        name = torch.cuda.get_device_name(0)
        total = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"training on {name}, {total:.1f} GB")


def train(args) -> Path:
    from ultralytics import YOLO

    check_environment()
    if not DATA.exists():
        sys.exit(f"{DATA} not found. Run data/tools/build_field_dataset.py first.")

    model = YOLO(args.weights)
    model.train(
        data=str(DATA),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(RUNS.parent),
        name=RUNS.name,
        exist_ok=True,
        patience=args.patience,
        workers=args.workers,
        seed=0,
        # Documents are photographed at every angle and under every light, but
        # they are never upside down in a scanner and never mirrored. Flipping
        # left-right would teach the detector that mirrored text is normal,
        # which is exactly the thing OCR then has to un-learn.
        fliplr=0.0,
        flipud=0.0,
        degrees=7.0,
        perspective=0.0005,
        hsv_v=0.4,
        mosaic=args.mosaic,
        # Mosaic pastes four cards into one frame, which is useful early and
        # actively wrong at the end - a real capture holds exactly one document.
        close_mosaic=10,
    )
    return RUNS / "weights" / "best.pt"


def export(weights: Path, imgsz: int = 640) -> dict:
    """Export to int8 ONNX and copy into models/, which the image bakes in."""
    from ultralytics import YOLO

    if not weights.exists():
        sys.exit(f"{weights} not found. Train first, or pass --weights.")

    model = YOLO(str(weights))
    print(f"exporting {weights} to ONNX at {imgsz}px")
    onnx_path = Path(model.export(format="onnx", imgsz=imgsz, opset=12,
                                  simplify=True, dynamic=False))

    MODELS.mkdir(parents=True, exist_ok=True)
    fp32 = MODELS / f"{EXPORT_NAME}.onnx"
    shutil.copy2(onnx_path, fp32)

    int8 = MODELS / f"{EXPORT_NAME}.int8.onnx"
    quantised = _quantise(fp32, int8)

    meta = _metadata(weights, fp32, int8 if quantised else None, imgsz)
    (MODELS / f"{EXPORT_NAME}.json").write_text(json.dumps(meta, indent=2),
                                                encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return meta


def _quantise(fp32: Path, int8: Path) -> bool:
    """Dynamic int8. Static would need a calibration pass and buys little on a
    detector this small - measure before adding one."""
    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic
    except ImportError:
        print("onnxruntime.quantization unavailable; shipping fp32 only")
        return False
    try:
        quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QUInt8)
        print(f"quantised -> {int8} "
              f"({fp32.stat().st_size / 1e6:.1f} MB -> {int8.stat().st_size / 1e6:.1f} MB)")
        return True
    except Exception as exc:                                # noqa: BLE001
        print(f"quantisation failed ({exc}); shipping fp32 only")
        return False


def _metadata(weights: Path, fp32: Path, int8: Path | None, imgsz: int) -> dict:
    """What the audit log needs to answer 'which model produced this verdict'."""
    import hashlib

    import yaml
    names = yaml.safe_load(DATA.read_text(encoding="utf-8"))["names"]
    shipped = int8 or fp32

    metrics = {}
    results = RUNS / "results.csv"
    if results.exists():
        rows = [r for r in results.read_text(encoding="utf-8").splitlines() if r.strip()]
        if len(rows) > 1:
            header = [h.strip() for h in rows[0].split(",")]
            last = [v.strip() for v in rows[-1].split(",")]
            metrics = {h: v for h, v in zip(header, last)
                       if "mAP" in h or "precision" in h or "recall" in h}

    return {
        "name": EXPORT_NAME,
        "task": "field detection, 22-class ontology",
        "imgsz": imgsz,
        "classes": names,
        "shipped": shipped.name,
        "precision": "int8" if int8 else "fp32",
        "sha256": hashlib.sha256(shipped.read_bytes()).hexdigest(),
        "size_mb": round(shipped.stat().st_size / 1e6, 2),
        "trained_from": str(weights.relative_to(ROOT)) if weights.is_relative_to(ROOT) else str(weights),
        "dataset": "data/processed/fields",
        "metrics": metrics,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--weights", default="yolo11s.pt",
                   help="starting weights, or a trained .pt with --export-only")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=12,
                   help="12 fits a 6 GB card at 640px with yolo11s")
    p.add_argument("--device", default=0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--patience", type=int, default=25)
    p.add_argument("--mosaic", type=float, default=0.6)
    p.add_argument("--export-only", action="store_true")
    args = p.parse_args()

    if args.export_only:
        weights = Path(args.weights)
        if not weights.is_absolute() and not weights.exists():
            weights = RUNS / "weights" / "best.pt"
        export(weights, args.imgsz)
        return 0

    best = train(args)
    export(best, args.imgsz)
    return 0


if __name__ == "__main__":
    sys.exit(main())
