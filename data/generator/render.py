"""Draw a document from a template spec and an identity. BUILD TIME ONLY.

The whole reason this is code rather than six vectorised specimens: **when the
renderer draws a field it knows exactly where it drew it**, so a YOLO label
falls out of the act of drawing. Nine days of vector work produces beautiful
images with no annotations, and annotations are what is actually missing -
`ghost_photo`, `barcode`, `hologram` and `doc_title` have zero training
instances (`data/TRAINING.md`), which is why the detector cannot learn them and
why `tamper.physical.ghost_missing` is blocked on a class that never appears.

The label is drawn around the **value**, not around the label text beside it.
That matches how the real datasets are annotated - `data/processed/fields`
boxes the date, not the words "Date of Birth" - so generated cards can be
merged with scraped ones without teaching the detector two different things.

Layouts are hand-written in `data/templates/*.yaml` and *checked* against the
medians measured over real cards (`config/layout/*.json`), not derived from
them: the measured spread is wide, and for some classes - passport `mrz` has a
median absolute deviation of half the page - it is too wide to place anything
by. `tests/test_generator.py` asserts the agreement where the reference is
trustworthy, which catches a template that drifts without pretending the
reference is more precise than it is.
"""
import math
import random
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.generator import guilloche as G                           # noqa: E402
from data.generator.identity import Identity                        # noqa: E402

TEMPLATES = ROOT / "data" / "templates"
FONTS = TEMPLATES / "fonts"

#: The frozen 22-class ontology. A template naming anything else is a bug, not
#: a new class - CLAUDE.md is explicit that classes are not added casually.
ONTOLOGY = (
    "person_photo", "ghost_photo", "signature", "qr_code", "barcode", "mrz",
    "name", "father_name", "dob", "gender", "address", "nationality",
    "id_number", "secondary_id", "issue_date", "expiry_date",
    "issuing_authority", "emblem", "logo", "hologram", "blood_group", "doc_title",
)

FACE_DIR = ROOT / "data" / "raw" / "face" / "sfhq"


@dataclass
class Drawn:
    """One rendered document: the image, and where everything on it went."""
    image: Image.Image
    labels: list          # [(class_name, x1, y1, x2, y2)] in pixels
    values: dict          # {class_name: the string actually printed}


class FontMissing(FileNotFoundError):
    """Fonts are build-time assets. Callers say how to get them."""


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS / name
    if not path.exists():
        raise FontMissing(
            f"{path} is missing. Run: python scripts/fetch_fonts.py")
    return ImageFont.truetype(str(path), size)


FONT_FILES = {
    "regular": "NotoSans-Regular.ttf",
    "bold": "NotoSans-Bold.ttf",
    "devanagari": "NotoSansDevanagari-Regular.ttf",
    "mono": "NotoSansMono-Regular.ttf",
}


def load_template(doc_type: str) -> dict:
    path = TEMPLATES / f"{doc_type}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no template at {path}")
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    for item in spec.get("fields", []):
        if item["class"] not in ONTOLOGY:
            raise ValueError(
                f"{path.name} names {item['class']!r}, which is not one of the "
                f"frozen 22 classes")
    return spec


def faces() -> list[Path]:
    """SFHQ, CC0, StyleGAN output - no real person (D22, data/PROVENANCE.md)."""
    return sorted(FACE_DIR.rglob("*.jpg")) + sorted(FACE_DIR.rglob("*.png"))


def _portrait(who: Identity, size) -> Image.Image:
    """The portrait belongs to the person, not to this render call.

    Keyed on `who.face_seed` so every document one identity holds shows the
    same face. Picking from the render rng instead gave a person a different
    photograph on each of their cards - invisible in a single document and
    fatal in a session, since Scene 3 puts two of them side by side.
    """
    pool = faces()
    if not pool:
        # A flat panel is still a locatable region, so the class keeps its
        # instances; it just will not exercise the face module.
        return Image.new("RGB", size, (150, 150, 158))
    chosen = pool[who.face_seed % len(pool)]
    return Image.open(chosen).convert("RGB").resize(size, Image.LANCZOS)


def _px(box, width: int, height: int):
    """Normalised [x1,y1,x2,y2] to pixels."""
    x1, y1, x2, y2 = box
    return (int(x1 * width), int(y1 * height), int(x2 * width), int(y2 * height))


def _value_for(spec: dict, who: Identity, doc_type: str) -> str:
    """The string a field prints, from the identity or from the template."""
    if "text" in spec:
        return str(spec["text"])
    source = spec.get("value")
    if source is None:
        return ""
    if source == "id_number":
        return {"aadhaar": who.aadhaar, "pan": who.pan, "voter_id": who.epic,
                "dl": who.dl, "passport": who.passport_number,
                "visa": who.passport_number}.get(doc_type, "")
    if source == "name":
        return who.name.upper()
    if source == "gender":
        return {"M": "MALE", "F": "FEMALE"}.get(who.sex, who.sex)
    if source == "dl_state":
        return who.dl_state
    return str(getattr(who, source, "") or "")


def render(doc_type: str, who: Identity, *, seed: int = 0,
           signed_qr: bytes | None = None) -> Drawn:
    """Draw one document. Returns the image and a label per ontology class drawn."""
    spec = load_template(doc_type)
    rng = random.Random(seed)
    width, height = spec["size"]

    canvas = Image.new("RGB", (width, height), tuple(spec["background"]))
    ink = tuple(spec.get("ink", (28, 30, 36)))

    if spec.get("guilloche", {}).get("enabled"):
        cfg = spec["guilloche"]
        panel = G.guilloche(width, height, tuple(cfg["colour"]), seed=seed,
                            curves=int(cfg.get("curves", 4)),
                            opacity=int(cfg.get("opacity", 70)))
        canvas.paste(panel, (0, 0), panel)

    draw = ImageDraw.Draw(canvas, "RGBA")
    labels: list = []
    values: dict = {}
    portrait_image: Image.Image | None = None

    for item in spec.get("static", []):
        _draw_static(draw, item, width, height, ink)

    for item in spec.get("fields", []):
        kind = item.get("kind", "text")
        box = _px(item["box"], width, height)
        name = item["class"]
        printed = ""

        if kind == "photo":
            portrait_image = _portrait(who, (box[2] - box[0], box[3] - box[1]))
            canvas.paste(portrait_image, (box[0], box[1]))
            draw.rectangle(box, outline=ink, width=1)
        elif kind == "ghost":
            if portrait_image is None:
                continue
            faded = G.ghost(portrait_image, (box[2] - box[0], box[3] - box[1]))
            canvas.paste(faded, (box[0], box[1]), faded)
        elif kind == "hologram":
            patch = G.hologram(box[2] - box[0], box[3] - box[1], seed=seed)
            canvas.paste(patch, (box[0], box[1]), patch)
        elif kind == "barcode":
            printed = _value_for(item, who, doc_type)
            strip = G.barcode(box[2] - box[0], box[3] - box[1], printed, ink)
            canvas.paste(strip, (box[0], box[1]), strip)
        elif kind == "qr":
            printed = _paste_qr(canvas, box, signed_qr)
        elif kind == "mrz":
            printed = _draw_mrz(draw, box, who, ink, item)
        elif kind == "signature":
            _draw_signature(draw, box, rng, ink)
        elif kind == "emblem":
            _draw_emblem(draw, box, ink)
        else:
            printed, box = _draw_text_field(draw, item, box, who, doc_type, ink,
                                            width, height)

        labels.append((name, *box))
        if printed:
            values[name] = printed

    if spec.get("microtext"):
        G.microtext(draw, _px(spec["microtext"]["box"], width, height),
                    spec["microtext"]["text"],
                    _font(FONT_FILES["regular"], 5),
                    tuple(spec["microtext"].get("colour", (110, 110, 120))))

    draw.rectangle([1, 1, width - 2, height - 2], outline=ink, width=2)
    return Drawn(image=canvas, labels=labels, values=values)


#: Devanagari occupies U+0900-U+097F. Noto Sans Devanagari covers that block and
#: **nothing else** - no Latin at all - so a bilingual label like "नाम / Name"
#: drawn entirely in it renders the English half as empty boxes. PIL has no font
#: fallback, so the run has to be split by script and each half drawn with the
#: face that has the glyphs.
def _is_devanagari(ch: str) -> bool:
    return "ऀ" <= ch <= "ॿ"


def _runs(text: str) -> list[tuple[str, bool]]:
    """Split a string into (segment, needs_devanagari) runs, in order."""
    out: list[tuple[str, bool]] = []
    for ch in str(text):
        deva = _is_devanagari(ch)
        if out and out[-1][1] == deva:
            out[-1] = (out[-1][0] + ch, deva)
        else:
            out.append((ch, deva))
    return out


def _draw_runs(draw, xy, text: str, latin_font, deva_font, fill, anchor=None):
    """Draw a possibly-bilingual string, switching face per run. Returns width."""
    segments = _runs(text)
    if not any(deva for _s, deva in segments):
        draw.text(xy, str(text), font=latin_font, fill=fill, anchor=anchor)
        return int(draw.textlength(str(text), font=latin_font))

    total = sum(draw.textlength(s, font=deva_font if d else latin_font)
                for s, d in segments)
    x, y = xy
    if anchor and anchor[0] == "m":
        x -= total / 2
    elif anchor and anchor[0] == "r":
        x -= total
    for segment, deva in segments:
        font = deva_font if deva else latin_font
        draw.text((x, y), segment, font=font, fill=fill,
                  anchor=("l" + anchor[1]) if anchor else None)
        x += draw.textlength(segment, font=font)
    return int(total)


def _draw_static(draw, item, width, height, ink) -> None:
    size = int(item.get("size", 14))
    font = _font(FONT_FILES[item.get("font", "regular")], size)
    deva = _font(FONT_FILES["devanagari"], size)
    x, y = item["at"][0] * width, item["at"][1] * height
    anchor = {"center": "ma", "left": "la", "right": "ra"}[item.get("align", "left")]
    _draw_runs(draw, (x, y), item["text"], font, deva,
               tuple(item.get("colour", ink)), anchor=anchor)


def _draw_text_field(draw, item, box, who, doc_type, ink, width, height):
    """Label beside the value; the returned box bounds the **value** only."""
    value = _value_for(item, who, doc_type)
    size = int(item.get("size", 15))
    font = _font(FONT_FILES[item.get("font", "regular")], size)

    x1, y1, x2, y2 = box
    if item.get("label"):
        label_size = max(8, int(size * 0.62))
        _draw_runs(draw, (x1, y1), item["label"],
                   _font(FONT_FILES["regular"], label_size),
                   _font(FONT_FILES["devanagari"], label_size),
                   tuple(item.get("label_colour", (95, 98, 110))))
        y1 += int(size * 0.78)

    lines = _wrap(value, font, x2 - x1) if item.get("wrap") else [value]
    top = y1
    widest = 0
    for line in lines:
        draw.text((x1, top), line, font=font, fill=ink)
        widest = max(widest, int(draw.textlength(line, font=font)))
        top += int(size * 1.25)

    return value, (x1 - 2, y1 - 2, min(x2, x1 + widest) + 3, min(height - 1, top) + 1)


def _wrap(text: str, font, max_width: int) -> list[str]:
    words, lines, current = str(text).split(), [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if font.getlength(trial) > max_width and current:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines[:3]


def _draw_mrz(draw, box, who: Identity, ink, item) -> str:
    """Two monospace lines, from `mrz.build_td3` - every check digit computed.

    Rendered in Noto Sans Mono, not OCR-B, which is licensed. Stated in
    data/templates/fonts/PROVENANCE.md rather than glossed over.
    """
    strip = who.mrz()
    x1, y1, x2, y2 = box
    lines = strip.split("\n")
    size = int(item.get("size", max(11, (y2 - y1) // (len(lines) + 1))))
    font = _font(FONT_FILES["mono"], size)

    draw.rectangle(box, fill=(252, 252, 250, 235))
    top = y1 + 2
    for line in lines:
        draw.text((x1 + 4, top), line, font=font, fill=ink)
        top += int(size * 1.35)
    return strip


def _paste_qr(canvas, box, signed_qr: bytes | None) -> str:
    import io
    if not signed_qr:
        return ""
    code = Image.open(io.BytesIO(signed_qr)).convert("RGB").resize(
        (box[2] - box[0], box[3] - box[1]), Image.NEAREST)
    canvas.paste(code, (box[0], box[1]))
    return "signed payload"


def _draw_signature(draw, box, rng: random.Random, ink) -> None:
    x1, y1, x2, y2 = box
    points, x = [], x1 + 4
    while x < x2 - 4:
        points.append((x, (y1 + y2) / 2 + rng.uniform(-1, 1) * (y2 - y1) * 0.3))
        x += max(3, (x2 - x1) // 14)
    if len(points) > 1:
        draw.line(points, fill=ink, width=2, joint="curve")


def _draw_emblem(draw, box, ink) -> None:
    """A simple mark standing in for the Ashoka lion capital.

    Deliberately not a reproduction of the State Emblem: it is protected under
    the State Emblem of India (Prohibition of Improper Use) Act, and a generated
    document carrying a real one is not something to put in a repository.
    """
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    r = min(x2 - x1, y2 - y1) / 2 - 2
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ink, width=2)
    for i in range(12):
        a = i * math.pi / 6
        draw.line([cx + r * 0.35 * math.cos(a), cy + r * 0.35 * math.sin(a),
                   cx + r * 0.85 * math.cos(a), cy + r * 0.85 * math.sin(a)],
                  fill=ink, width=1)
