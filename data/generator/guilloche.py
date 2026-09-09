"""Security features, drawn procedurally. BUILD TIME ONLY.

Guilloche is not a texture and not a stock image - it is a family of curves. A
real one is cut by a rose engine tracing a hypotrochoid: a point on a circle
rolling inside another circle. Drawing it the way it is actually made costs
about thirty lines and gives the physical tampering track something true to
check, because the line-work is continuous by construction. A pasted patch
breaks it, and the break is real rather than staged.

The other four features here exist for a narrower reason. `ghost_photo`,
`barcode`, `hologram` and `doc_title` have **zero instances** in the training
set (`data/TRAINING.md`), so the field detector cannot learn them and
`tamper.physical.ghost_missing` is blocked on a class that never appears. They
are drawn here so that stops being true.
"""
import math

from PIL import Image, ImageDraw, ImageFilter


def hypotrochoid(width: int, height: int, *, R: float, r: float, d: float,
                 turns: int = 40, steps: int = 2400):
    """Points of one rose-engine curve, scaled into a width x height box.

    R is the fixed circle, r the rolling one, d the pen offset. Their ratio
    decides how many petals close the figure, which is why a guilloche looks
    designed rather than random.
    """
    points = []
    for i in range(steps):
        t = (i / steps) * turns * math.pi
        k = (R - r) / r
        x = (R - r) * math.cos(t) + d * math.cos(k * t)
        y = (R - r) * math.sin(t) - d * math.sin(k * t)
        points.append((x, y))

    span = max(max(abs(x) for x, _ in points), max(abs(y) for _, y in points)) or 1
    cx, cy = width / 2, height / 2
    scale = min(width, height) / (2 * span)
    return [(cx + x * scale, cy + y * scale) for x, y in points]


def guilloche(width: int, height: int, colour, *, seed: int = 0,
              curves: int = 4, opacity: int = 70) -> Image.Image:
    """A guilloche *field* - the pattern tiled across the page, not one rosette.

    A real security background repeats a small figure over the whole surface;
    a single large one is a logo. Tiling matters for more than looks: the
    physical track checks line-work *continuity*, and a pattern that only
    covers the middle of the page leaves most of it with nothing to break.

    Kept faint. This sits underneath printed text that OCR has to read, and a
    background competing with the glyphs would be a self-inflicted wound.
    """
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    rgba = tuple(colour) + (opacity,)

    tile = max(90, min(width, height) // 4)
    for row in range(0, height + tile, tile):
        for col in range(0, width + tile, tile):
            n = (row // tile + col // tile + seed) % curves
            points = hypotrochoid(
                tile, tile,
                R=95 + 21 * ((seed + n) % 5),
                r=19 + 7 * ((seed + 2 * n) % 6),
                d=38 + 13 * ((seed + n) % 4),
                turns=14 + 3 * n, steps=700,
            )
            draw.line([(x + col - tile / 2, y + row - tile / 2) for x, y in points],
                      fill=rgba, width=1)

    return layer


def ghost(photo: Image.Image, size, opacity: int = 110) -> Image.Image:
    """The second, faded portrait. Present on every real passport and Aadhaar.

    Greyscale and translucent, as the printed one is: it is a watermark, not a
    second photograph, and a forger who replaces the main photo and forgets
    this one leaves two different faces on the page.
    """
    small = photo.convert("L").resize(size, Image.LANCZOS).convert("RGBA")
    alpha = small.split()[-1].point(lambda _v: opacity)
    small.putalpha(alpha)
    return small


def hologram(width: int, height: int, *, seed: int = 0) -> Image.Image:
    """A translucent iridescent patch - an OVD, in the trade.

    Approximated as a soft angular colour sweep. It exists so the class has
    instances and so a capture carries something whose appearance changes with
    the light, which is what makes holograms hard to photocopy and hard for us
    to check.
    """
    patch = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(patch)
    bands = 22
    for i in range(bands):
        hue = (i / bands + seed * 0.11) % 1.0
        colour = _hue_to_rgb(hue)
        x0 = int(width * i / bands)
        draw.polygon(
            [(x0, 0), (x0 + width / bands, 0),
             (x0 + width / bands - width * 0.18, height), (x0 - width * 0.18, height)],
            fill=colour + (60,))
    return patch.filter(ImageFilter.GaussianBlur(1.2))


def _hue_to_rgb(hue: float):
    i = int(hue * 6) % 6
    f = hue * 6 - int(hue * 6)
    q, t = int(255 * (1 - f)), int(255 * f)
    return [(255, t, 0), (q, 255, 0), (0, 255, t),
            (0, q, 255), (t, 0, 255), (255, 0, q)][i]


def microtext(draw: ImageDraw.ImageDraw, box, text: str, font, colour) -> None:
    """A line of text too small to read at capture resolution.

    Genuine documents carry it because a photocopier cannot reproduce it. Ours
    carries it so a capture has fine detail that survives or does not, which is
    what the print-consistency measurement reads.
    """
    x1, y1, x2, y2 = box
    repeated = (text + " ") * 40
    draw.text((x1, y1), repeated[:int((x2 - x1) / 3)], font=font, fill=colour)


def barcode(width: int, height: int, value: str, colour=(20, 20, 20)) -> Image.Image:
    """Vertical bars derived from the value. Visual only - nothing decodes it.

    An honest limitation: this is not Code 39 and does not claim to be. The
    class needs instances so the detector can learn to *locate* a barcode; a
    real symbology would matter only if something read it, and nothing does.
    """
    strip = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(strip)
    x = 2
    for i, ch in enumerate(value or "0"):
        thick = 3 if (ord(ch) + i) % 3 == 0 else 1
        if x + thick >= width:
            break
        draw.rectangle([x, 0, x + thick, height], fill=colour + (255,))
        x += thick + (2 if (ord(ch) + i) % 2 else 3)
    return strip
