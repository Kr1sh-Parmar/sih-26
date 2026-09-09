"""Fetch Florence-2-base for the VLM fallback. BUILD TIME ONLY.

    python scripts/fetch_vlm_model.py

Nothing is downloaded at inspection time (CLAUDE.md rule 3). This is the same
boundary `scripts/fetch_face_models.py` and `data/tools/train_fields.py` sit on,
and `tests/test_offline.py` enforces it by AST: nothing under
`api/ core/ fusion/ modules/` may import a downloader.

**Four graphs, not one.** Florence-2 is an encoder-decoder VLM and its ONNX
export is split the way the runtime needs it:

    vision_encoder      image  -> image embeddings
    embed_tokens        token ids -> text embeddings
    encoder_model       [image; text] embeddings -> encoder hidden states
    decoder_model_merged  autoregressive decode, with a KV cache

Quantised throughout: 275 MB against 1.1 GB. This model is the *fallback*, it
loads lazily on the first document that needs it, and it is the one place where
a slower, smaller graph is unambiguously the right trade.

**The prompt is tokenised here, not at runtime.** `<OCR_WITH_REGION>` expands to
one fixed English sentence, so its token ids never change. Encoding it at build
time and baking the ids into the sidecar means the screening path needs only a
*decoder* - id to string - and never the byte-level BPE merge loop. That is
about sixty lines and a whole class of bug that simply never runs at a border
post.
"""
import functools
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
BASE = "https://huggingface.co/onnx-community/Florence-2-base/resolve/main/"

NAME = "florence2"

#: logical name -> file in the repo. Quantised: 275 MB against 1.1 GB fp32.
GRAPHS = {
    "florence2_vision": "onnx/vision_encoder_quantized.onnx",
    "florence2_embed": "onnx/embed_tokens_quantized.onnx",
    "florence2_encoder": "onnx/encoder_model_quantized.onnx",
    "florence2_decoder": "onnx/decoder_model_merged_quantized.onnx",
}

#: What `<OCR_WITH_REGION>` actually sends the model. Florence-2 replaces the
#: task token with this sentence; the task token is never itself embedded.
OCR_WITH_REGION_PROMPT = "What is the text in the image, with regions?"

#: Florence-2 pins these. Fetched anyway and asserted, so a re-export that
#: changes them fails loudly here rather than producing garbled text later.
EXPECTED = {"eos_token_id": 2, "bos_token_id": 0, "pad_token_id": 1,
            "decoder_start_token_id": 2}


def fetch(path: str, tries: int = 5) -> bytes | None:
    """Download with retries. DNS on this network drops often enough to matter."""
    for attempt in range(1, tries + 1):
        try:
            with urllib.request.urlopen(BASE + path, timeout=600) as response:
                return response.read()
        except Exception as exc:                                # noqa: BLE001
            print(f"    attempt {attempt}/{tries}: {type(exc).__name__}")
            if attempt < tries:
                time.sleep(4)
    return None


# --------------------------------------------------------- byte-level BPE

@functools.lru_cache(maxsize=1)
def byte_encoder() -> dict[int, str]:
    """GPT-2's reversible byte-to-unicode map, which BART inherits.

    Bytes that are not printable get mapped into a private-use range so the
    vocabulary is pure text. The decoder in `modules/extraction/vlm.py` inverts
    exactly this.
    """
    printable = (list(range(ord("!"), ord("~") + 1))
                 + list(range(ord("\xa1"), ord("\xac") + 1))
                 + list(range(ord("\xae"), ord("\xff") + 1)))
    mapping, spare = list(printable), 0
    for byte in range(256):
        if byte not in printable:
            printable.append(byte)
            mapping.append(256 + spare)
            spare += 1
    return {b: chr(c) for b, c in zip(printable, mapping)}


def _pairs(word: tuple) -> set:
    return {(word[i], word[i + 1]) for i in range(len(word) - 1)}


def bpe(token: str, ranks: dict) -> list[str]:
    """Greedy byte-pair merge, lowest rank first. The standard algorithm."""
    word = tuple(token)
    if len(word) < 2:
        return list(word)
    while True:
        candidates = _pairs(word)
        best = min(candidates, key=lambda p: ranks.get(p, float("inf")))
        if best not in ranks:
            break
        first, second = best
        merged, i = [], 0
        while i < len(word):
            if (i < len(word) - 1 and word[i] == first
                    and word[i + 1] == second):
                merged.append(first + second)
                i += 2
            else:
                merged.append(word[i])
                i += 1
        word = tuple(merged)
        if len(word) == 1:
            break
    return list(word)


def encode(text: str, vocab: dict, ranks: dict) -> list[int]:
    """Text to token ids. Build time only - the runtime never encodes."""
    import re
    pattern = re.compile(
        r"'s|'t|'re|'ve|'m|'ll|'d| ?[A-Za-z]+| ?\d+| ?[^\sA-Za-z\d]+|\s+(?!\S)|\s+")
    table = byte_encoder()
    ids = []
    for chunk in pattern.findall(text):
        mapped = "".join(table[b] for b in chunk.encode("utf-8"))
        for piece in bpe(mapped, ranks):
            if piece not in vocab:
                raise ValueError(f"token {piece!r} is not in the vocabulary")
            ids.append(vocab[piece])
    return ids


def main() -> int:
    MODELS.mkdir(parents=True, exist_ok=True)

    if all((MODELS / f"{n}.onnx").exists() for n in GRAPHS) \
            and (MODELS / f"{NAME}.json").exists():
        print("models/ already holds Florence-2; delete them to re-fetch")
        return 0

    for logical, remote in GRAPHS.items():
        target = MODELS / f"{logical}.onnx"
        if target.exists():
            print(f"  {logical:20s} already here "
                  f"({target.stat().st_size / 1e6:.0f} MB)")
            continue
        print(f"  {logical:20s} fetching {remote}")
        blob = fetch(remote)
        if blob is None:
            print(f"\ncould not fetch {remote}. Re-run when the network is back.")
            return 1
        target.write_bytes(blob)
        print(f"  {'':20s} -> {target.stat().st_size / 1e6:.0f} MB")

    print("  tokeniser and config")
    raw_tokenizer = fetch("tokenizer.json")
    raw_config = fetch("generation_config.json")
    if raw_tokenizer is None or raw_config is None:
        print("could not fetch the tokeniser; the graphs alone are unusable")
        return 1

    tokenizer = json.loads(raw_tokenizer)
    generation = json.loads(raw_config)
    for key, expected in EXPECTED.items():
        got = generation.get(key)
        if got != expected:
            print(f"  WARNING: {key} is {got}, expected {expected}. The export "
                  f"has changed; check vlm.py before trusting its output.")

    vocab = dict(tokenizer["model"]["vocab"])
    ranks = {tuple(m.split(" ") if isinstance(m, str) else m): i
             for i, m in enumerate(tokenizer["model"]["merges"])}
    added = {entry["content"]: entry["id"]
             for entry in tokenizer.get("added_tokens", [])}

    prompt_ids = encode(OCR_WITH_REGION_PROMPT, vocab, ranks)
    # BART wraps the prompt in <s> ... </s>.
    prompt_ids = [generation["bos_token_id"], *prompt_ids,
                  generation["eos_token_id"]]

    # id -> token string, for the runtime decoder. Added tokens included, so
    # <loc_0>..<loc_999> come back as themselves and the region parser can see
    # them.
    id_to_token = {index: token for token, index in vocab.items()}
    id_to_token.update({index: token for token, index in added.items()})

    meta = {
        "name": NAME,
        "task": "OCR with region, Florence-2-base",
        "source": "onnx-community/Florence-2-base, quantised",
        "prompt": OCR_WITH_REGION_PROMPT,
        "prompt_ids": prompt_ids,
        "special": {k: generation[k] for k in EXPECTED},
        "imgsz": 768,
        "loc_bins": sum(1 for t in added if t.startswith("<loc_")),
        "vocab": id_to_token,
        "graphs": list(GRAPHS),
        "size_mb": round(sum((MODELS / f"{n}.onnx").stat().st_size
                             for n in GRAPHS) / 1e6, 1),
    }
    (MODELS / f"{NAME}.json").write_text(json.dumps(meta), encoding="utf-8")

    print(f"\n  prompt {OCR_WITH_REGION_PROMPT!r}")
    print(f"  -> {len(prompt_ids)} tokens, {meta['loc_bins']} location bins")
    print(f"  {meta['size_mb']} MB of graphs in {MODELS.relative_to(ROOT)}")
    print("\nnothing else fetches at runtime. Florence-2 loads lazily, on the")
    print("first document that actually needs it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
