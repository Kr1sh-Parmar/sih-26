"""Convert MiniFASNet to ONNX for the passive liveness check. BUILD TIME ONLY.

    .venv-train/Scripts/python scripts/convert_liveness.py

This is the one script that must run under `.venv-train`, because it is the one
that needs torch - and torch must never enter the screening process
(CLAUDE.md rule 2). Same quarantine as `data/tools/train_fields.py`: torch goes
in, ONNX comes out, and only the ONNX crosses back.

Nothing is trained here. A `.pth` is loaded and re-serialised.

Source: Silent-Face-Anti-Spoofing, minivision-ai, **Apache License 2.0** - which
permits redistribution with attribution, so the converted weights can ship in
the image. The attribution goes in the sidecar and in data/FACE.md.

Two details that are easy to get wrong and silent when wrong:

  * The checkpoint is saved from `MultiFTNet` training, so every key carries a
    `module.` prefix that has to come off before `load_state_dict`.
  * `conv6_kernel` is not a constant - upstream computes it from the input size
    as `((h + 15) // 16, (w + 15) // 16)`, which is (5, 5) at 80x80. Passing the
    default builds a net whose weights do not fit the checkpoint.

The model name encodes its own geometry: `2.7_80x80_MiniFASNetV2.pth` is scale
2.7, 80x80 input, architecture V2. `modules/face/liveness.py` already crops at
`SCALE = 2.7`, which is that number and not a coincidence.
"""
import hashlib
import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
CACHE = ROOT / "var" / "liveness-src"

REPO = "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing"
RAW = "https://raw.githubusercontent.com/minivision-ai/Silent-Face-Anti-Spoofing/master/"

CHECKPOINT = "2.7_80x80_MiniFASNetV2.pth"
CHECKPOINT_URL = (f"{REPO}/raw/master/resources/anti_spoof_models/{CHECKPOINT}")
SOURCE_URL = RAW + "src/model_lib/MiniFASNet.py"

NAME = "face_liveness"
INPUT = 80


def fetch(url: str, target: Path, tries: int = 4) -> bytes:
    """Download with retries. DNS on this network drops often enough to matter."""
    if target.exists() and target.stat().st_size > 1000:
        return target.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            if len(data) < 1000:
                raise ValueError(f"only {len(data)} bytes")
            target.write_bytes(data)
            return data
        except Exception as exc:                                # noqa: BLE001
            print(f"    attempt {attempt}/{tries}: {type(exc).__name__}")
            if attempt == tries:
                raise
            time.sleep(3)
    raise RuntimeError("unreachable")


def load_architecture(source: Path):
    """Import upstream's model definitions from the fetched file.

    Fetched rather than vendored: 300 lines of someone else's architecture
    copied into this repository would be 300 lines nobody here can maintain and
    a licence header to keep correct. The sha256 of what was actually executed
    goes in the sidecar, so the provenance is checkable.
    """
    spec = importlib.util.spec_from_file_location("minifasnet_upstream", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules["minifasnet_upstream"] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        import torch
    except ImportError:
        sys.exit("torch is missing. Run this with .venv-train/Scripts/python, "
                 "not the base interpreter - torch must never be importable "
                 "from the screening process.")

    print(f"fetching {CHECKPOINT}")
    weights_path = CACHE / CHECKPOINT
    weights_blob = fetch(CHECKPOINT_URL, weights_path)
    print(f"  {len(weights_blob) / 1e6:.2f} MB")

    print("fetching the model definition")
    source_path = CACHE / "MiniFASNet.py"
    source_blob = fetch(SOURCE_URL, source_path)
    print(f"  {len(source_blob) / 1e3:.1f} kB")

    upstream = load_architecture(source_path)

    # ((80 + 15) // 16, ...) = (5, 5). Upstream's get_kernel, inlined - it is one
    # expression and importing their utility module would drag in os/datetime
    # helpers we do not want executing.
    conv6_kernel = ((INPUT + 15) // 16, (INPUT + 15) // 16)
    model = upstream.MiniFASNetV2(conv6_kernel=conv6_kernel)

    state = torch.load(weights_path, map_location="cpu", weights_only=True)
    if next(iter(state)).startswith("module."):
        state = {key[len("module."):]: value for key, value in state.items()}
    model.load_state_dict(state)
    model.eval()

    # A deterministic ramp, NOT a black frame. Zeros are invariant under any
    # scaling, so a black-frame reference cannot catch the exact bug that bit
    # here: dividing the input by 255 when the model expects raw 0-255. The
    # reference has to vary with the input range or it checks nothing.
    ramp = (torch.arange(3 * INPUT * INPUT, dtype=torch.float32)
            .reshape(1, 3, INPUT, INPUT) % 256.0)
    with torch.no_grad():
        reference = torch.nn.functional.softmax(model(ramp), dim=1).numpy().ravel()
    print(f"  torch softmax on the reference ramp: {reference.round(4).tolist()}")


    MODELS.mkdir(parents=True, exist_ok=True)
    target = MODELS / f"{NAME}.onnx"
    torch.onnx.export(
        model, ramp, str(target),
        input_names=["input"], output_names=["logits"],
        opset_version=12, do_constant_folding=True, dynamo=False,
    )
    payload = target.read_bytes()
    print(f"exported {target.relative_to(ROOT)}  {len(payload) / 1e6:.2f} MB")

    (MODELS / f"{NAME}.json").write_text(json.dumps({
        "name": NAME,
        "task": "passive liveness, MiniFASNetV2, 3 logits {spoof-2D, live, spoof-3D}",
        "imgsz": INPUT,
        # Both of these were guessed wrong before the weights existed. Upstream's
        # ToTensor transposes and calls .float() - no channel swap, no /255.
        "colour_order": "BGR",
        "input_range": "0-255, not normalised",
        "scale": 2.7,
        "precision": "fp32",
        "sha256": hashlib.sha256(payload).hexdigest(),
        "size_mb": round(len(payload) / 1e6, 2),
        "source": f"minivision-ai/Silent-Face-Anti-Spoofing {CHECKPOINT}",
        "source_url": REPO,
        "licence": "Apache-2.0",
        "checkpoint_sha256": hashlib.sha256(weights_blob).hexdigest(),
        "architecture_sha256": hashlib.sha256(source_blob).hexdigest(),
        "reference_output_ramp": [round(float(v), 6) for v in reference],
    }, indent=2), encoding="utf-8")

    print("\nverify with the CPU runtime the screening path actually uses:")
    print("  python scripts/convert_liveness.py --verify")
    return 0


def verify() -> int:
    """Run the exported graph on onnxruntime and check it agrees with torch.

    Deliberately runs under the BASE interpreter, not `.venv-train`: the thing
    worth testing is the file as the screening process will load it.
    """
    import numpy as np
    import onnxruntime as ort

    meta = json.loads((MODELS / f"{NAME}.json").read_text(encoding="utf-8"))
    sess = ort.InferenceSession(str(MODELS / f"{NAME}.onnx"),
                                providers=["CPUExecutionProvider"])
    blob = (np.arange(3 * INPUT * INPUT, dtype=np.float32)
            .reshape(1, 3, INPUT, INPUT) % 256.0)
    logits = np.asarray(sess.run(None, {sess.get_inputs()[0].name: blob})[0]).ravel()
    shifted = logits - logits.max()
    probs = np.exp(shifted) / np.exp(shifted).sum()

    expected = np.array(meta["reference_output_ramp"], dtype=np.float64)
    drift = float(np.abs(probs - expected).max())
    print(f"onnxruntime: {probs.round(4).tolist()}")
    print(f"torch:       {expected.round(4).tolist()}")
    print(f"max drift:   {drift:.2e}")
    if probs.size != 3:
        sys.exit(f"expected 3 logits, got {probs.size}")
    if drift > 1e-4:
        sys.exit("the exported graph disagrees with torch; do not ship it")
    print("\nagrees. modules/face/liveness.py will pick it up with no other change.")
    return 0


if __name__ == "__main__":
    sys.exit(verify() if "--verify" in sys.argv else main())
