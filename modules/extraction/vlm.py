"""Florence-2 fallback reader. The last thing tried before "re-capture".

TECHNICAL-SPEC.md section 4. Fires in two situations, and the second is the one
that matters most today:

  1. OCR located a field and read it too faintly to rely on.
  2. **Nothing was located at all** - which is every document right now, because
     the field detector has no weights (`MODEL-TRAINING.md`). `<OCR_WITH_REGION>`
     reads a whole page and grounds each string in a box, so it needs no
     detector. It is the only path that can read a document before the GPU run
     comes back.

**Why Florence-2 and not a chat VLM.** Asked for JSON, a chat model invents a
passport number for an unreadable smudge, because generating plausible
structured output is exactly what it was trained to do. `<OCR_WITH_REGION>`
returns text with boxes grounded in the image: it can misread a character, but
it structurally cannot produce a field out of nothing (D4).

That is a weaker guarantee than it sounds, so **nothing here reaches validation
unratified** - `modules/extraction/ratify.py` is a mandatory gate, and this
module hands everything it reads to it.

Loaded lazily. It is the one model in the inventory not warmed at startup: the
warm footprint goes from about 450 MB to 910 MB when it loads, and 85% of
documents never need it.

Four ONNX graphs, and the feed is built from each session's *declared* inputs
rather than from a hardcoded list, because a re-export that renames or reorders
them should fail loudly here instead of quietly feeding the decoder a zeroed
cache.
"""
import re
import time

import cv2
import numpy as np

from core.profiles import load_config
from core.registry import FLORENCE, available, metadata, session
from fusion.context import ScreeningContext
from fusion.signal import Signal
from modules.extraction import ratify as ratifier

#: `<loc_0>`..`<loc_999>`: Florence-2 quantises coordinates into 1000 bins.
LOC = re.compile(r"<loc_(\d+)>")

#: A run of text followed by the location tokens that bound it. The model emits
#: them strictly in that order, so one pass of this pairs every string with its
#: own quad.
REGION = re.compile(r"([^<]*)((?:<loc_\d+>)+)")

#: ImageNet normalisation, which Florence-2's preprocessor uses.
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


class Timeout(RuntimeError):
    """The fallback ran past its deadline. Callers fall through to re-capture."""


def deployed() -> bool:
    """All four graphs and the sidecar present."""
    meta = metadata(FLORENCE)
    return bool(meta) and all(available(name) for name in meta.get("graphs", []))


def config() -> dict:
    return load_config("thresholds").get("vlm", {})


# ------------------------------------------------------------------ the model

def preprocess(image: np.ndarray, size: int) -> np.ndarray:
    """BGR uint8 to the NCHW float batch the vision encoder wants."""
    resized = cv2.resize(image, (size, size), interpolation=cv2.INTER_AREA)
    rgb = resized[:, :, ::-1].astype(np.float32) / 255.0
    return ((rgb - MEAN) / STD).transpose(2, 0, 1)[None].astype(np.float32)


def _feed(sess, available_values: dict) -> dict:
    """Build the input dict from what this graph actually declares.

    Names differ between exports - `input_ids` against `inputs_embeds`,
    `attention_mask` against `encoder_attention_mask`. Matching on the declared
    names means a re-export raises here rather than silently mis-feeding.
    """
    feed = {}
    for spec in sess.get_inputs():
        if spec.name in available_values:
            feed[spec.name] = available_values[spec.name]
    missing = [s.name for s in sess.get_inputs() if s.name not in feed]
    return feed, missing


def _empty_cache(sess, batch: int, heads: int, dim: int) -> dict:
    """Zero-length past-key-values for the first decode step."""
    cache = {}
    for spec in sess.get_inputs():
        if not spec.name.startswith("past_key_values"):
            continue
        cache[spec.name] = np.zeros((batch, heads, 0, dim), dtype=np.float32)
    return cache


def generate(image: np.ndarray, *, deadline: float, max_tokens: int = 512) -> str:
    """Run the four graphs and greedily decode. Raises `Timeout` past `deadline`.

    Greedy, not the beam search the generation config asks for. Beam search is
    three times the decode cost for a task whose output is transcription rather
    than composition - there is no fluency to optimise, and a border post has an
    8 second ceiling. ponytail: swap in beams if transcription quality measurably
    suffers; the loop below is the only thing that changes.
    """
    meta = metadata(FLORENCE)
    special = meta["special"]
    vocab = {int(k): v for k, v in meta["vocab"].items()}

    vision = session("florence2_vision")
    embed = session("florence2_embed")
    encoder = session("florence2_encoder")
    decoder = session("florence2_decoder")

    pixel_values = preprocess(image, int(meta.get("imgsz", 768)))
    image_features = vision.run(None, {vision.get_inputs()[0].name: pixel_values})[0]
    _check(deadline)

    prompt = np.array([meta["prompt_ids"]], dtype=np.int64)
    text_features = embed.run(None, {embed.get_inputs()[0].name: prompt})[0]
    _check(deadline)

    # Florence-2 concatenates the image tokens in front of the prompt tokens.
    merged = np.concatenate([image_features, text_features], axis=1).astype(np.float32)
    attention = np.ones(merged.shape[:2], dtype=np.int64)

    feed, missing = _feed(encoder, {"inputs_embeds": merged,
                                    "attention_mask": attention})
    if missing:
        raise RuntimeError(f"encoder wants inputs we do not supply: {missing}")
    encoder_hidden = encoder.run(None, feed)[0]
    _check(deadline)

    tokens = [special["decoder_start_token_id"]]
    heads, dim = _cache_shape(decoder, encoder_hidden.shape[-1])
    past = _empty_cache(decoder, 1, heads, dim)
    use_cache = False
    encoder_cache: dict = {}

    for _step in range(max_tokens):
        _check(deadline)
        step_ids = np.array([[tokens[-1]]] if use_cache else [tokens],
                            dtype=np.int64)
        step_embeds = embed.run(None, {embed.get_inputs()[0].name: step_ids})[0]

        values = {
            "inputs_embeds": step_embeds,
            "encoder_hidden_states": encoder_hidden,
            "encoder_attention_mask": attention,
            "attention_mask": attention,
            "use_cache_branch": np.array([use_cache], dtype=bool),
            **past,
        }
        feed, missing = _feed(decoder, values)
        if missing:
            raise RuntimeError(f"decoder wants inputs we do not supply: {missing}")

        outputs = decoder.run(None, feed)
        names = [o.name for o in decoder.get_outputs()]
        logits = outputs[names.index("logits")]
        next_token = int(np.argmax(logits[0, -1]))
        if next_token == special["eos_token_id"]:
            break
        tokens.append(next_token)

        fresh = {f"past_key_values{name.split('present')[1]}": value
                 for name, value in zip(names, outputs) if name.startswith("present")}
        # The cross-attention cache is computed from the encoder output, which
        # does not change, so it is captured once on the first pass and then
        # left alone. It has to be: on every later step the merged export's If
        # node returns a placeholder for the branch it did not take, and that
        # placeholder comes back with a zero batch dimension. Feeding it back
        # fails on step three with a broadcast error several layers from the
        # cause. Only the self-attention half grows.
        if not encoder_cache:
            encoder_cache = {k: v for k, v in fresh.items() if ".encoder." in k}
        past = {**{k: v for k, v in fresh.items() if ".decoder." in k},
                **encoder_cache}
        use_cache = True

    return decode(tokens[1:], vocab)


def _cache_shape(decoder, hidden: int) -> tuple[int, int]:
    """Heads and per-head dimension, from the decoder's own declared shapes."""
    for spec in decoder.get_inputs():
        if spec.name.startswith("past_key_values"):
            shape = spec.shape
            heads = shape[1] if isinstance(shape[1], int) else 12
            dim = shape[3] if isinstance(shape[3], int) else hidden // heads
            return int(heads), int(dim)
    return 12, hidden // 12


def _check(deadline: float) -> None:
    if time.perf_counter() > deadline:
        raise Timeout("the fallback reader ran past its deadline")


def decode(token_ids: list[int], vocab: dict) -> str:
    """Token ids to text, inverting GPT-2's byte-level mapping.

    Encoding lives in `scripts/fetch_vlm_model.py` and runs once at build time:
    the only string this model is ever asked to encode is a fixed prompt, so its
    ids are baked into the sidecar and the screening path never needs the merge
    loop.
    """
    raw = "".join(vocab.get(i, "") for i in token_ids)
    return _interleave(raw, _byte_decoder())


def _interleave(text: str, table: dict) -> str:
    """Decode byte-level runs while passing added tokens (`<loc_7>`) straight through."""
    out, run = [], bytearray()
    index = 0
    while index < len(text):
        if text[index] == "<":
            close = text.find(">", index)
            if close != -1:
                if run:
                    out.append(run.decode("utf-8", "replace"))
                    run = bytearray()
                out.append(text[index:close + 1])
                index = close + 1
                continue
        char = text[index]
        if char in table:
            run.append(table[char])
        index += 1
    if run:
        out.append(run.decode("utf-8", "replace"))
    return "".join(out)


def _byte_decoder() -> dict:
    printable = (list(range(ord("!"), ord("~") + 1))
                 + list(range(ord("\xa1"), ord("\xac") + 1))
                 + list(range(ord("\xae"), ord("\xff") + 1)))
    mapping, spare = list(printable), 0
    for byte in range(256):
        if byte not in printable:
            printable.append(byte)
            mapping.append(256 + spare)
            spare += 1
    return {chr(c): b for b, c in zip(printable, mapping)}


# ------------------------------------------------------------- reading regions

def parse_regions(text: str, width: int, height: int,
                  bins: int = 1000) -> list[tuple[str, tuple]]:
    """`text<loc_a><loc_b>...` to [(string, box)] in image pixels.

    Florence-2 emits a run of text followed by the quad that bounds it - eight
    location tokens, coordinates quantised into `bins`. The bounding box of that
    quad is what the console overlays and what a field box is matched against.
    """
    out = []
    for label, locs in REGION.findall(text.replace("<s>", "").replace("</s>", "")):
        label = label.strip()
        values = [int(v) for v in LOC.findall(locs)]
        if not label or len(values) < 4:
            continue
        xs, ys = values[0::2], values[1::2]
        out.append((label, (
            min(xs) / bins * width, min(ys) / bins * height,
            max(xs) / bins * width, max(ys) / bins * height)))
    return out


# ------------------------------------------------------------ text to fields

#: What an MRZ line looks like before it has been parsed: the ICAO charset and
#: nothing else, at one of the two lengths the parser handles.
MRZ_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<")

DATE_FIELDS = ("dob", "issue_date", "expiry_date")


def _looks_like_mrz(text: str) -> bool:
    stripped = text.replace(" ", "").upper()
    return (len(stripped) in (36, 44)
            and set(stripped) <= MRZ_CHARS
            and stripped.count("<") >= 3)


def _iou(a, b) -> float:
    """Local, not `fusion.findings._iou`: modules do not import one another's
    internals (CLAUDE.md), and six lines is cheaper than a boundary violation."""
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0
    inter = (ix2 - ix1) * (iy2 - iy1)
    union = ((a[2] - a[0]) * (a[3] - a[1])
             + (b[2] - b[0]) * (b[3] - b[1]) - inter)
    return inter / union if union > 0 else 0.0


def assign(reads: list[tuple[str, tuple]], doc_type: str,
           field_boxes: dict | None = None) -> dict[str, str]:
    """Decide which ontology field each read string is, or leave it unassigned.

    **Only fields whose shape can be recognised are assigned.** A number that
    validates as this document's identity number is that number; a date is a
    date; an MRZ line is an MRZ. A line of capital letters could be the name,
    the father's name or the first line of the address, and guessing would put
    a wrong value where Layer C and Layer D compare against it - which is the
    precise harm `ratify.py` exists to prevent, arrived at from the other side.
    So names and addresses are read, reported in the evidence, and not assigned.

    When the detector *is* deployed its boxes settle it properly: a read whose
    region overlaps a located field is that field, and no guessing is needed.
    """
    if field_boxes:
        return _assign_by_overlap(reads, field_boxes)

    from modules.extraction import normalize as N

    assigned: dict[str, str] = {}
    dates: list[str] = []

    for text, _box in reads:
        if "mrz" not in assigned and _looks_like_mrz(text):
            assigned["mrz"] = text.replace(" ", "").upper()
            continue

        candidate = N.id_number(text)
        if "id_number" not in assigned and candidate:
            ok, _detail = _validates_as_id(candidate, doc_type)
            if ok:
                assigned["id_number"] = candidate
                continue

        iso = N.iso_date(text)
        if iso:
            dates.append(iso)

    # ponytail: several dates on a page and no labels to tell them apart, so
    # they are ordered - birth first, then issue, then expiry. True on all six
    # types. A document issued before its holder was born would defeat it, and
    # Layer C would then report a date-order failure the officer can read, which
    # is the right way for a guess this shaky to fail.
    for name, value in zip(DATE_FIELDS, sorted(set(dates))):
        assigned[name] = value
    return assigned


def _assign_by_overlap(reads, field_boxes: dict) -> dict[str, str]:
    """Read regions to located fields by best overlap. Used when a detector ran."""
    assigned: dict[str, str] = {}
    for text, box in reads:
        best, score = None, 0.10
        for name, field_box in field_boxes.items():
            overlap = _iou(tuple(box), tuple(field_box))
            if overlap > score:
                best, score = name, overlap
        if best and best not in assigned:
            assigned[best] = text
    return assigned


def _validates_as_id(value: str, doc_type: str) -> tuple[bool, str]:
    pair = ratifier.anchor_for(doc_type)
    if pair is None or pair[1] != "id_number":
        return False, "no identity-number anchor for this type"
    return ratifier.check(pair[0], value)


# ------------------------------------------------------------------ the module

def run(ctx: ScreeningContext, *, reason: str = "nothing was located") -> list[Signal]:
    """The fallback. Reads the page, then hands everything to the ratifier.

    Never raises. A fallback that crashes the screening is worse than one that
    admits it could not read.
    """
    started = time.perf_counter()
    cfg = config()

    if not deployed():
        return [_unavailable(started)]

    budget = float(cfg.get("timeout_seconds", 8.0))
    try:
        text = generate(ctx.image, deadline=started + budget)
    except Timeout:
        return [_timed_out(budget, started)]
    except Exception as exc:                                    # noqa: BLE001
        return [_failed(exc, started)]

    height, width = ctx.image.shape[:2]
    regions = parse_regions(text, width, height)
    if not regions:
        return [_read_nothing(reason, started)]

    fields = assign(regions, ctx.profile["doc_type"], ctx.field_boxes or None)
    # The ratifier is the only producer of `extraction.vlm.*`. Reporting what
    # was read here as well would emit the same id twice, which
    # tests/test_signal_identity.py forbids and which would charge coverage
    # twice for one condition (D8).
    # `started` is this function's clock, not the ratifier's. Every failure
    # path above already reports the whole fallback; the success path - the
    # only one that actually spends the seven seconds - was losing it.
    return ratifier.ratify(ctx, fields, started=started,
                           confidence=float(cfg.get("confidence", 0.5)))


def _signal(sid, verdict, evidence, *, confidence, trust="unverified",
            started=None) -> Signal:
    return Signal(
        id=sid, module="extraction", tier=1, verdict=verdict,
        confidence=confidence, trust_class=trust, hard_fail=False,
        anchor="document", evidence=evidence,
        latency_ms=int((time.perf_counter() - started) * 1000) if started else 0)


def _unavailable(started) -> Signal:
    return _signal(
        "extraction.vlm.unratified", "inconclusive",
        "The fallback reader is not deployed, so a document the field detector "
        "cannot read could not be read another way. Run "
        "scripts/fetch_vlm_model.py to deploy it",
        confidence=0.0, started=started)


def _timed_out(budget: float, started) -> Signal:
    return _signal(
        "extraction.vlm.unratified", "inconclusive",
        f"The fallback reader ran past its {budget:.0f} second limit and was "
        f"stopped. Re-capture the document at a higher resolution",
        confidence=0.0, started=started)


def _failed(exc: Exception, started) -> Signal:
    return _signal(
        "extraction.vlm.unratified", "inconclusive",
        f"The fallback reader could not run ({type(exc).__name__}). Re-capture "
        f"the document", confidence=0.0, started=started)


def _read_nothing(reason: str, started) -> Signal:
    return _signal(
        "extraction.vlm.unratified", "inconclusive",
        f"The fallback reader found no legible text - {reason}. Re-capture the "
        f"document at a higher resolution", confidence=0.0, started=started)
