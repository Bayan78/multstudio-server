"""Render subtitle blocks as transparent RGBA images with Pillow.

We render captions ourselves (not moviepy TextClip) so we do NOT depend on
ImageMagick, which is the most common moviepy deployment headache.
"""
import os
from PIL import Image, ImageDraw, ImageFont

_FONT_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "assets", "fonts", "caption.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "DejaVuSans-Bold.ttf",
]


def _load_font(size: int):
    for p in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _wrap(draw, words, font, max_w):
    lines, cur = [], []
    for w in words:
        test = " ".join(cur + [w])
        if draw.textlength(test, font=font) > max_w and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def render_caption(text: str, width: int, height: int,
                   position: str = "bottom", size: str = "m",
                   fill=(255, 255, 255), accent=(49, 231, 219),
                   revealed=None):
    """Return an RGBA PIL image with the caption drawn.

    revealed=None  -> all words shown (static caption).
    revealed=k     -> karaoke: words[:k] shown, word[k-1] highlighted (accent),
                      remaining words dimmed.
    """
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if not text:
        return img
    draw = ImageDraw.Draw(img)
    frac = {"s": 0.052, "m": 0.066, "l": 0.082}.get(size, 0.066)
    fs = max(18, int(width * frac))
    font = _load_font(fs)
    max_w = int(width * 0.86)
    words = text.split()
    lines = _wrap(draw, words, font, max_w)
    line_h = int(fs * 1.22)
    block_h = line_h * len(lines)

    if position == "top":
        y = int(height * 0.14)
    elif position == "center":
        y = (height - block_h) // 2
    else:
        y = int(height * 0.80) - block_h

    outline = max(2, int(fs * 0.10))
    space_w = draw.textlength(" ", font=font)
    wi = 0  # global word index across lines
    for li, line in enumerate(lines):
        line_words = line.split()
        lw = draw.textlength(line, font=font)
        x = (width - lw) // 2
        ly = y + li * line_h
        for word in line_words:
            if revealed is None:
                color = fill + (255,)
            elif wi < revealed - 1:
                color = fill + (255,)                 # already spoken
            elif wi == revealed - 1:
                color = accent + (255,)               # current word
            else:
                color = (255, 255, 255, 70)           # not yet
            # outline
            for dx in range(-outline, outline + 1, 2):
                for dy in range(-outline, outline + 1, 2):
                    if dx or dy:
                        draw.text((x + dx, ly + dy), word, font=font, fill=(0, 0, 0, 235))
            draw.text((x, ly), word, font=font, fill=color)
            x += draw.textlength(word, font=font) + space_w
            wi += 1
    return img
