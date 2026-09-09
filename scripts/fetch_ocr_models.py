"""Fetch the Devanagari recogniser. BUILD TIME ONLY.

    python scripts/fetch_ocr_models.py

Closes half of D24. RapidOCR bundles `ch_PP-OCRv4_rec_infer.onnx`, whose
dictionary is Chinese and Latin. Fed Devanagari it returns an **empty string at
confidence 0.00** — measured, see `data/EXTRACTION.md`. That is the safe
failure, because empty becomes `inconclusive` rather than a wrong value, but it
means the `ocr_lang: [en, hi]` that `aadhaar`, `voter_id` and `dl` declare is
only half true.

Two files are needed and neither is optional: a PP-OCR recogniser is a graph
**plus** its character dictionary, and the graph alone decodes to nonsense.

---

## The conversion problem, stated plainly

PaddleOCR publishes Devanagari as a Paddle *inference* model, not ONNX. Turning
it into something `onnxruntime` can load needs `paddle2onnx`, and every version
of `paddle2onnx` on PyPI today imports `paddle` — so the conversion drags in the
full PaddlePaddle runtime. That is acceptable as a build-time dependency, the
same way CUDA torch is acceptable in `.venv-train`; it is not acceptable in
`requirements.txt`, which is the screening image.

This script therefore does one of two things and says which:

  * `paddle2onnx` importable  → download, convert, install into `models/`;
  * not importable            → download nothing, print what to install.

**On the machine this was written on the PaddlePaddle download timed out**, so
the recogniser is not deployed and `modules/extraction/ocr.py` says so in the
sentence an officer reads rather than reporting a bare "could not be read".

---

## What it buys, honestly

Less than it sounds. Every *value* on all six document types is printed in Latin
as well as Devanagari — the Hindi is a second rendering of the same field, not a
field of its own — so the Latin pass already reads every value the validators
need. This matters for one case: a card whose Latin half is damaged or absent.
`ocr.py` treats it as a fallback for exactly that reason, not as a switch.

A cross-script consistency check (Hindi name against Latin name) would be a real
tamper signal and is deliberately **not** built here: it needs transliteration,
transliteration is approximate, and an approximate comparison feeding a
`crossdoc`-style mismatch is precisely the failure mode that was just fixed in
Layers C and D.
"""
import shutil
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
NAME = "rec_devanagari"

REC_TAR = ("https://paddleocr.bj.bcebos.com/PP-OCRv3/multilingual/"
           "devanagari_PP-OCRv3_rec_infer.tar")
DICT_URL = ("https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/"
            "ppocr/utils/dict/devanagari_dict.txt")


def fetch(url: str, target: Path, tries: int = 4) -> bool:
    """Download with retries. DNS on this network drops often enough to matter."""
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            if len(data) < 200:
                raise ValueError(f"only {len(data)} bytes")
            target.write_bytes(data)
            return True
        except Exception as exc:                                # noqa: BLE001
            print(f"    attempt {attempt}/{tries}: {type(exc).__name__}")
            if attempt < tries:
                time.sleep(3)
    return False


def have_converter() -> bool:
    try:
        import paddle2onnx  # noqa: F401
        return True
    except Exception:                                           # noqa: BLE001
        return False


def convert(inference_dir: Path, out: Path) -> bool:
    """Paddle inference model to ONNX. Returns whether it worked."""
    import paddle2onnx

    try:
        paddle2onnx.export(
            model_filename=str(inference_dir / "inference.pdmodel"),
            params_filename=str(inference_dir / "inference.pdiparams"),
            save_file=str(out),
            opset_version=12,
            auto_upgrade_opset=True,
        )
        return out.exists()
    except Exception as exc:                                    # noqa: BLE001
        print(f"  conversion failed: {type(exc).__name__}: {exc}")
        return False


def main() -> int:
    MODELS.mkdir(parents=True, exist_ok=True)
    graph, keys = MODELS / f"{NAME}.onnx", MODELS / f"{NAME}.txt"

    if graph.exists() and keys.exists():
        print(f"  {NAME} already deployed ({graph.stat().st_size / 1e6:.1f} MB)")
        return 0

    print("  devanagari_dict.txt")
    if not fetch(DICT_URL, keys):
        print("\ncould not fetch the character dictionary. Nothing installed.")
        return 1
    print(f"  {'':4s}-> {keys.stat().st_size / 1e3:.0f} kB, "
          f"{len(keys.read_text(encoding='utf-8').splitlines())} characters")

    if not have_converter():
        keys.unlink(missing_ok=True)
        print(
            "\npaddle2onnx is not importable, so the recogniser cannot be\n"
            "converted. Install the build-time toolchain and re-run:\n\n"
            "    python -m pip install paddlepaddle paddle2onnx\n\n"
            "Neither belongs in requirements.txt - that file is the screening\n"
            "image, and tests/test_offline.py fails anything under api/ core/\n"
            "fusion/ modules/ that can reach the network.\n\n"
            "Until then Devanagari-only fields read as `inconclusive`, and\n"
            "modules/extraction/ocr.py says that is why."
        )
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        archive = tmp / "rec.tar"
        print("  devanagari_PP-OCRv3_rec_infer.tar")
        if not fetch(REC_TAR, archive):
            keys.unlink(missing_ok=True)
            print("\ncould not fetch the recogniser. Nothing installed.")
            return 1

        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        found = next((p.parent for p in tmp.rglob("inference.pdmodel")), None)
        if found is None:
            keys.unlink(missing_ok=True)
            print("\nthe archive held no inference.pdmodel. Nothing installed.")
            return 1

        if not convert(found, graph):
            keys.unlink(missing_ok=True)
            return 1

    print(f"  {'':4s}-> {graph.relative_to(ROOT)} "
          f"({graph.stat().st_size / 1e6:.1f} MB)")
    print("\nDevanagari deployed. Verify:\n"
          "  python -c \"from core import registry; print(registry.devanagari_rec())\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
